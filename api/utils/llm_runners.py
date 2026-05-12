"""
Abstraction for interacting with different Large Language Model (LLM) providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import requests
import time
import logging
import json
from langchain_community.llms import Ollama
from langchain_core.callbacks.manager import CallbackManager
from langchain_core.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

logger = logging.getLogger(__name__)

class LLMRunner(ABC):
    """
    Abstract base class for LLM runners.

    Defines the interface for interacting with different LLM providers.
    """

    @abstractmethod
    def invoke(self, prompt: str) -> str:
        """
        Invoke the LLM with a given prompt and return the response.

        Args:
            prompt (str): The input prompt for the LLM.

        Returns:
            str: The LLM's generated response.

        Raises:
            NotImplementedError: If the method is not implemented by the subclass.
            ConnectionError: If there's an issue connecting to the LLM service.
            RuntimeError: For other LLM invocation errors.
        """
        raise NotImplementedError

    @abstractmethod
    def get_langchain_llm(self) -> Any:
        """
        Return an instance of the LangChain compatible LLM object.

        This is needed for integration with LangChain's RetrievalQA chains.

        Returns:
            Any: A LangChain LLM compatible object (e.g., langchain_community.llms.Ollama).

        Raises:
            NotImplementedError: If the method is not implemented by the subclass.
        """
        raise NotImplementedError

    @abstractmethod
    def ensure_model_available(self) -> None:
        """
        Ensure the configured model is available for the provider.
        This might involve pulling the model, checking API keys, etc.

        Args:
            None

        Returns:
            None

        Raises:
            NotImplementedError: If the method is not implemented by the subclass.
            ConnectionError: If connection fails during check/setup.
            RuntimeError: If the model cannot be made available.
        """
        raise NotImplementedError


class OllamaRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using Ollama.
    """

    def __init__(
        self,
        base_url: str,
        model_name: str,
        temperature: float = 0.1,
        max_retries: int = 3,
        retry_delay: int = 5,
    ):
        """
        Initialize the OllamaRunner.

        Args:
            base_url (str): Base URL for the Ollama API.
            model_name (str): Name of the model to use in Ollama.
            temperature (float): Temperature parameter for LLM generation.
            max_retries (int): Maximum retries for model pulling.
            retry_delay (int): Delay between retries in seconds.

        Returns:
            None
        """
        self.base_url = base_url
        self.model_name = model_name
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._langchain_llm = None # Lazy initialization
        self.ensure_model_available()
        self._initialize_langchain_llm() # Initialize after ensuring model exists

    def ensure_model_available(self) -> None:
        """
        Ensure the requested model is available in Ollama, pulling it if needed.

        Args:
            None

        Returns:
            None

        Raises:
            ConnectionError: If unable to connect to Ollama service.
            RuntimeError: If model cannot be pulled after maximum retries.
        """
        logger.info(f"Checking availability of Ollama model: {self.model_name} at {self.base_url}")
        try:
            # Check if model exists
            response = requests.get(f"{self.base_url}/api/tags")
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            available_models = [model["name"] for model in response.json().get("models", [])]
            if self.model_name in available_models:
                logger.info(f"Model {self.model_name} is already available in Ollama.")
                return

            # Model not found, pull it
            logger.info(f"Ollama model {self.model_name} not found, attempting to pull...")

            for attempt in range(1, self.max_retries + 1):
                logger.info(f"Pulling attempt {attempt}/{self.max_retries}...")
                try:
                    # Use streaming=True to get progress updates if needed
                    pull_response = requests.post(
                        f"{self.base_url}/api/pull",
                        json={"name": self.model_name},
                        stream=True # Allows reading response line-by-line
                    )
                    pull_response.raise_for_status()

                    # Process the streaming response to confirm success
                    # Ollama streams status updates. We need to wait for completion.
                    pull_complete = False
                    for line in pull_response.iter_lines():
                        if line:
                            try:
                                status = json.loads(line.decode('utf-8'))
                                logger.debug(f"Ollama pull status: {status.get('status')}")
                                if "error" in status:
                                    logger.error(f"Error pulling Ollama model: {status['error']}")
                                    raise RuntimeError(f"Ollama error: {status['error']}")
                                if status.get('status') == 'success':
                                    pull_complete = True
                                    logger.info(f"Successfully pulled Ollama model {self.model_name}.")
                                    break # Exit inner loop once success confirmed
                            except json.JSONDecodeError:
                                logger.warning(f"Could not decode Ollama status line: {line}")
                    
                    if pull_complete:
                        return # Exit outer loop and method

                    logger.warning(f"Ollama model pull stream ended without explicit success message on attempt {attempt}.")

                except requests.RequestException as e:
                    logger.warning(f"Network error during Ollama model pull attempt {attempt}/{self.max_retries}: {e}")
                except RuntimeError as e:
                     logger.warning(f"Error during Ollama model pull attempt {attempt}/{self.max_retries}: {e}")
                except Exception as e:
                    logger.warning(f"Unexpected error during pull attempt {attempt}/{self.max_retries}: {e}")

                if attempt < self.max_retries:
                    logger.info(f"Retrying Ollama pull in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)

            raise RuntimeError(f"Failed to pull Ollama model {self.model_name} after {self.max_retries} attempts.")

        except requests.RequestException as e:
            logger.error(f"Failed to connect to Ollama service at {self.base_url}: {e}")
            raise ConnectionError(f"Could not connect to Ollama service at {self.base_url}: {e}")

    def _initialize_langchain_llm(self) -> None:
        """Initialize the LangChain compatible Ollama object."""
        try:
            # Initialize with streaming capability if needed for LangChain
            callback_manager = CallbackManager([StreamingStdOutCallbackHandler()])
            self._langchain_llm = Ollama(
                base_url=self.base_url,
                model=self.model_name,
                temperature=self.temperature,
                callback_manager=callback_manager,
            )
            logger.info(f"Initialized LangChain Ollama wrapper for model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize LangChain Ollama wrapper: {e}")
            # Decide if this should be a critical error or allow proceeding
            # raise ConnectionError(f"Could not initialize LangChain Ollama: {e}")
            self._langchain_llm = None # Ensure it's None if initialization fails

    def invoke(self, prompt: str) -> str:
        """
        Invoke the Ollama LLM with a given prompt.

        Args:
            prompt (str): The input prompt for the LLM.

        Returns:
            str: The LLM's generated response.

        Raises:
            ConnectionError: If there's an issue connecting to the Ollama service.
            RuntimeError: For other LLM invocation errors.
        """
        if self._langchain_llm is None:
             self._initialize_langchain_llm() # Attempt re-initialization
             if self._langchain_llm is None:
                 raise RuntimeError("Ollama LLM (LangChain wrapper) is not initialized.")

        logger.debug(f"Invoking Ollama model '{self.model_name}' with prompt: {prompt[:100]}...")
        try:
            # Use the LangChain wrapper's invoke method
            response = self._langchain_llm.invoke(prompt)
            logger.debug("Ollama invocation successful.")
            return response
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error during Ollama invocation: {e}")
            raise ConnectionError(f"Failed to connect to Ollama at {self.base_url}: {e}")
        except Exception as e:
            logger.error(f"Error invoking Ollama model: {e}")
            # Consider more specific error handling based on Ollama/LangChain exceptions
            raise RuntimeError(f"Error during Ollama invocation: {e}")

    def get_langchain_llm(self) -> Any:
        """
        Return an instance of the LangChain compatible Ollama object.

        Returns:
            langchain_community.llms.Ollama: The initialized LangChain Ollama wrapper.

        Raises:
            RuntimeError: If the LangChain wrapper is not initialized.
        """
        if self._langchain_llm is None:
             self._initialize_langchain_llm() # Attempt re-initialization
             if self._langchain_llm is None:
                 raise RuntimeError("Ollama LLM (LangChain wrapper) is not initialized.")
        return self._langchain_llm


class VLLMRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using vLLM with OpenAI-compatible API.
    """

    def __init__(
        self,
        base_url: str,
        model_name: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        max_retries: int = 3,
        retry_delay: int = 5,
    ):
        """
        Initialize the VLLMRunner.

        Args:
            base_url (str): Base URL for the vLLM API (e.g., "http://vllm:8001").
            model_name (str): Name of the model to use in vLLM.
            temperature (float): Temperature parameter for LLM generation.
            max_tokens (int): Maximum number of tokens to generate.
            max_retries (int): Maximum retries for API calls.
            retry_delay (int): Delay between retries in seconds.

        Returns:
            None
        """
        self.base_url = base_url.rstrip('/')  # Remove trailing slash
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._langchain_llm = None  # Lazy initialization
        self.ensure_model_available()
        self._initialize_langchain_llm()

    def ensure_model_available(self) -> None:
        """
        Ensure the vLLM service is available and the model is loaded.

        vLLM loads models at startup, so we just need to verify the service
        is running and the model is accessible.

        Args:
            None

        Returns:
            None

        Raises:
            ConnectionError: If unable to connect to vLLM service.
            RuntimeError: If model is not available in vLLM.
        """
        logger.info(f"Checking availability of vLLM model: {self.model_name} at {self.base_url}")
        logger.info(f"vLLM might take several minutes to download and load the model, please be patient...")
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Attempt {attempt}/{self.max_retries} - Connecting to vLLM service...")
                # Check if vLLM service is running by querying the models endpoint
                base_url = f"{self.base_url}/v1/models"
                print(f"Asking response from vLLM base_url: {base_url}")
                response = requests.get(base_url, timeout=10)
                
                response.raise_for_status()
                
                models_data = response.json()
                available_models = [model["id"] for model in models_data.get("data", [])]
                
                if self.model_name in available_models:
                    logger.info(f"✅ Model {self.model_name} is available in vLLM.")
                    return
                else:
                    logger.warning(f"Model {self.model_name} not found in vLLM. Available models: {available_models}")
                    # For vLLM, we'll still proceed as the model might be loaded but not listed
                    # or it might be the exact model path
                    logger.info(f"✅ Proceeding with model {self.model_name} (may be model path)")
                    return
                    
            except requests.RequestException as e:
                if attempt < self.max_retries:
                    logger.warning(f"⏳ Attempt {attempt}/{self.max_retries} - vLLM not ready yet: {e}")
                    logger.info(f"   Waiting {self.retry_delay} seconds before next attempt...")
                    logger.info(f"   (vLLM may still be downloading/loading the model)")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"❌ Failed to connect to vLLM service after {self.max_retries} attempts")
                    raise ConnectionError(f"Could not connect to vLLM service at {self.base_url} after {self.max_retries} attempts: {e}")
            except Exception as e:
                logger.error(f"Unexpected error checking vLLM service: {e}")
                raise RuntimeError(f"Unexpected error during vLLM service check: {e}")

    def _initialize_langchain_llm(self) -> None:
        """Initialize the LangChain compatible OpenAI object for vLLM."""
        try:
            from langchain_openai import OpenAI
            
            # vLLM provides OpenAI-compatible API, so we use OpenAI LangChain wrapper
            self._langchain_llm = OpenAI(
                base_url=f"{self.base_url}/v1",
                api_key="dummy-key",  # vLLM doesn't require real API key
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            logger.info(f"Initialized LangChain OpenAI wrapper for vLLM model: {self.model_name}")
        except ImportError as e:
            logger.error(f"Failed to import langchain_openai: {e}")
            logger.info("Falling back to direct API calls")
            self._langchain_llm = None
        except Exception as e:
            logger.error(f"Failed to initialize LangChain OpenAI wrapper for vLLM: {e}")
            self._langchain_llm = None

    def invoke(self, prompt: str) -> str:
        """
        Invoke the vLLM model with a given prompt using OpenAI-compatible API.

        Args:
            prompt (str): The input prompt for the LLM.

        Returns:
            str: The LLM's generated response.

        Raises:
            ConnectionError: If there's an issue connecting to the vLLM service.
            RuntimeError: For other LLM invocation errors.
        """
        logger.debug(f"Invoking vLLM model '{self.model_name}' with prompt: {prompt[:100]}...")
        
        # If LangChain wrapper is available, use it
        if self._langchain_llm is not None:
            try:
                response = self._langchain_llm.invoke(prompt)
                logger.debug("vLLM invocation via LangChain successful.")
                return response
            except Exception as e:
                logger.warning(f"LangChain invocation failed, falling back to direct API: {e}")
        
        # Fallback to direct API call
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "stream": False
            }
            
            response = requests.post(
                f"{self.base_url}/v1/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                generated_text = result["choices"][0]["text"]
                logger.debug("vLLM invocation via direct API successful.")
                return generated_text
            else:
                raise RuntimeError(f"Unexpected response format from vLLM: {result}")
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error during vLLM invocation: {e}")
            raise ConnectionError(f"Failed to connect to vLLM at {self.base_url}: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout during vLLM invocation: {e}")
            raise RuntimeError(f"Timeout during vLLM invocation: {e}")
        except Exception as e:
            logger.error(f"Error invoking vLLM model: {e}")
            raise RuntimeError(f"Error during vLLM invocation: {e}")

    def get_langchain_llm(self) -> Any:
        """
        Return an instance of the LangChain compatible OpenAI object for vLLM.

        Returns:
            langchain_openai.OpenAI: The initialized LangChain OpenAI wrapper.

        Raises:
            RuntimeError: If the LangChain wrapper is not initialized.
        """
        if self._langchain_llm is None:
            self._initialize_langchain_llm()
            if self._langchain_llm is None:
                raise RuntimeError("vLLM LLM (LangChain wrapper) is not initialized. Install langchain_openai package.")
        return self._langchain_llm


# Placeholder for future OpenAI implementation
class OpenAIRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using OpenAI API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other OpenAI specific parameters as needed
    ):
        raise NotImplementedError("OpenAIRunner is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("OpenAIRunner model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking OpenAI API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid OpenAI API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("OpenAIRunner LangChain init not implemented.")
        # from langchain_openai import OpenAI
        # try:
        #     self._langchain_llm = OpenAI(
        #         openai_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain OpenAI wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain OpenAI wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("OpenAIRunner invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("OpenAI LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking OpenAI model: {e}")
        #     # Handle specific OpenAI errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during OpenAI invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("OpenAIRunner get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("OpenAI LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Google implementation
class GoogleRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using Google API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Google specific parameters as needed
    ):
        raise NotImplementedError("GoogleRunner is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("GoogleRunner model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Google API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Google API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("GoogleRunner LangChain init not implemented.")
        # from langchain_google import Google
        # try:
        #     self._langchain_llm = Google(
        #         google_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Google wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Google wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("GoogleRunner invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Google LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Google model: {e}")
        #     # Handle specific Google errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Google invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("GoogleRunner get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Google LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Hugging Face implementation
class HuggingFaceRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using Hugging Face API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Hugging Face specific parameters as needed
    ):
        raise NotImplementedError("HuggingFaceRunner is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("HuggingFaceRunner model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Hugging Face API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Hugging Face API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("HuggingFaceRunner LangChain init not implemented.")
        # from langchain_huggingface import HuggingFace
        # try:
        #     self._langchain_llm = HuggingFace(
        #         huggingface_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Hugging Face wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Hugging Face wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("HuggingFaceRunner invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Hugging Face LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Hugging Face model: {e}")
        #     # Handle specific Hugging Face errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Hugging Face invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("HuggingFaceRunner get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Hugging Face LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Azure implementation
class AzureRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using Azure API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Azure specific parameters as needed
    ):
        raise NotImplementedError("AzureRunner is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("AzureRunner model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Azure API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Azure API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("AzureRunner LangChain init not implemented.")
        # from langchain_azure import Azure
        # try:
        #     self._langchain_llm = Azure(
        #         azure_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Azure wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Azure wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("AzureRunner invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Azure LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Azure model: {e}")
        #     # Handle specific Azure errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Azure invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("AzureRunner get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Azure LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future AWS implementation
class AWSRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using AWS API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other AWS specific parameters as needed
    ):
        raise NotImplementedError("AWSRunner is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("AWSRunner model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking AWS API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid AWS API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("AWSRunner LangChain init not implemented.")
        # from langchain_aws import AWS
        # try:
        #     self._langchain_llm = AWS(
        #         aws_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain AWS wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain AWS wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("AWSRunner invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("AWS LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking AWS model: {e}")
        #     # Handle specific AWS errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during AWS invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("AWSRunner get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("AWS LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future DeepSeek implementation
class DeepSeekRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using DeepSeek API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other DeepSeek specific parameters as needed
    ):
        raise NotImplementedError("DeepSeekRunner is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("DeepSeekRunner model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking DeepSeek API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid DeepSeek API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("DeepSeekRunner LangChain init not implemented.")
        # from langchain_deepseek import DeepSeek
        # try:
        #     self._langchain_llm = DeepSeek(
        #         deepseek_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain DeepSeek wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain DeepSeek wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("DeepSeekRunner invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSeek LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking DeepSeek model: {e}")
        #     # Handle specific DeepSeek errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during DeepSeek invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("DeepSeekRunner get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSeek LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Qwen implementation
class QwenRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using Qwen API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Qwen specific parameters as needed
    ):
        raise NotImplementedError("QwenRunner is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("QwenRunner model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Qwen API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Qwen API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("QwenRunner LangChain init not implemented.")
        # from langchain_qwen import Qwen
        # try:
        #     self._langchain_llm = Qwen(
        #         qwen_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Qwen wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Qwen wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("QwenRunner invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Qwen LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Qwen model: {e}")
        #     # Handle specific Qwen errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Qwen invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("QwenRunner get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Qwen LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Baichuan implementation
class BaichuanRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using Baichuan API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Baichuan specific parameters as needed
    ):
        raise NotImplementedError("BaichuanRunner is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("BaichuanRunner model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Baichuan API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Baichuan API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("BaichuanRunner LangChain init not implemented.")
        # from langchain_baichuan import Baichuan
        # try:
        #     self._langchain_llm = Baichuan(
        #         baichuan_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Baichuan wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Baichuan wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("BaichuanRunner invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Baichuan LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Baichuan model: {e}")
        #     # Handle specific Baichuan errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Baichuan invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("BaichuanRunner get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Baichuan LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future LLaMA implementation
class LLaMARunner(LLMRunner):
    """
    Concrete implementation for running LLMs using LLaMA API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other LLaMA specific parameters as needed
    ):
        raise NotImplementedError("LLaMARunner is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("LLaMARunner model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking LLaMA API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid LLaMA API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("LLaMARunner LangChain init not implemented.")
        # from langchain_llama import LLaMA
        # try:
        #     self._langchain_llm = LLaMA(
        #         llama_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain LLaMA wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain LLaMA wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("LLaMARunner invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("LLaMA LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking LLaMA model: {e}")
        #     # Handle specific LLaMA errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during LLaMA invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("LLaMARunner get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("LLaMA LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future DeepSpeed implementation
class DeepSpeedRunner(LLMRunner):
    """
    Concrete implementation for running LLMs using DeepSpeed API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other DeepSpeed specific parameters as needed
    ):
        raise NotImplementedError("DeepSpeedRunner is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("DeepSpeedRunner model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking DeepSpeed API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid DeepSpeed API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("DeepSpeedRunner LangChain init not implemented.")
        # from langchain_deepspeed import DeepSpeed
        # try:
        #     self._langchain_llm = DeepSpeed(
        #         deepspeed_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain DeepSpeed wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain DeepSpeed wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("DeepSpeedRunner invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSpeed LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking DeepSpeed model: {e}")
        #     # Handle specific DeepSpeed errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during DeepSpeed invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("DeepSpeedRunner get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSpeed LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Hugging Face implementation
class HuggingFaceImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using Hugging Face API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Hugging Face specific parameters as needed
    ):
        raise NotImplementedError("HuggingFaceImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("HuggingFaceImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Hugging Face API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Hugging Face API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("HuggingFaceImplementation LangChain init not implemented.")
        # from langchain_huggingface import HuggingFace
        # try:
        #     self._langchain_llm = HuggingFace(
        #         huggingface_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Hugging Face wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Hugging Face wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("HuggingFaceImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Hugging Face LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Hugging Face model: {e}")
        #     # Handle specific Hugging Face errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Hugging Face invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("HuggingFaceImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Hugging Face LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Azure implementation
class AzureImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using Azure API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Azure specific parameters as needed
    ):
        raise NotImplementedError("AzureImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("AzureImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Azure API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Azure API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("AzureImplementation LangChain init not implemented.")
        # from langchain_azure import Azure
        # try:
        #     self._langchain_llm = Azure(
        #         azure_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Azure wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Azure wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("AzureImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Azure LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Azure model: {e}")
        #     # Handle specific Azure errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Azure invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("AzureImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Azure LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future AWS implementation
class AWSImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using AWS API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other AWS specific parameters as needed
    ):
        raise NotImplementedError("AWSImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("AWSImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking AWS API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid AWS API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("AWSImplementation LangChain init not implemented.")
        # from langchain_aws import AWS
        # try:
        #     self._langchain_llm = AWS(
        #         aws_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain AWS wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain AWS wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("AWSImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("AWS LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking AWS model: {e}")
        #     # Handle specific AWS errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during AWS invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("AWSImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("AWS LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future DeepSeek implementation
class DeepSeekImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using DeepSeek API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other DeepSeek specific parameters as needed
    ):
        raise NotImplementedError("DeepSeekImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("DeepSeekImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking DeepSeek API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid DeepSeek API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("DeepSeekImplementation LangChain init not implemented.")
        # from langchain_deepseek import DeepSeek
        # try:
        #     self._langchain_llm = DeepSeek(
        #         deepseek_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain DeepSeek wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain DeepSeek wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("DeepSeekImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSeek LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking DeepSeek model: {e}")
        #     # Handle specific DeepSeek errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during DeepSeek invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("DeepSeekImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSeek LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Qwen implementation
class QwenImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using Qwen API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Qwen specific parameters as needed
    ):
        raise NotImplementedError("QwenImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("QwenImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Qwen API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Qwen API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("QwenImplementation LangChain init not implemented.")
        # from langchain_qwen import Qwen
        # try:
        #     self._langchain_llm = Qwen(
        #         qwen_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Qwen wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Qwen wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("QwenImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Qwen LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Qwen model: {e}")
        #     # Handle specific Qwen errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Qwen invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("QwenImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Qwen LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Baichuan implementation
class BaichuanImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using Baichuan API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Baichuan specific parameters as needed
    ):
        raise NotImplementedError("BaichuanImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("BaichuanImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Baichuan API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Baichuan API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("BaichuanImplementation LangChain init not implemented.")
        # from langchain_baichuan import Baichuan
        # try:
        #     self._langchain_llm = Baichuan(
        #         baichuan_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Baichuan wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Baichuan wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("BaichuanImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Baichuan LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Baichuan model: {e}")
        #     # Handle specific Baichuan errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Baichuan invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("BaichuanImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Baichuan LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future LLaMA implementation
class LLaMAImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using LLaMA API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other LLaMA specific parameters as needed
    ):
        raise NotImplementedError("LLaMAImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("LLaMAImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking LLaMA API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid LLaMA API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("LLaMAImplementation LangChain init not implemented.")
        # from langchain_llama import LLaMA
        # try:
        #     self._langchain_llm = LLaMA(
        #         llama_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain LLaMA wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain LLaMA wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("LLaMAImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("LLaMA LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking LLaMA model: {e}")
        #     # Handle specific LLaMA errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during LLaMA invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("LLaMAImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("LLaMA LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future DeepSpeed implementation
class DeepSpeedImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using DeepSpeed API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other DeepSpeed specific parameters as needed
    ):
        raise NotImplementedError("DeepSpeedImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("DeepSpeedImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking DeepSpeed API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid DeepSpeed API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("DeepSpeedImplementation LangChain init not implemented.")
        # from langchain_deepspeed import DeepSpeed
        # try:
        #     self._langchain_llm = DeepSpeed(
        #         deepspeed_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain DeepSpeed wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain DeepSpeed wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("DeepSpeedImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSpeed LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking DeepSpeed model: {e}")
        #     # Handle specific DeepSpeed errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during DeepSpeed invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("DeepSpeedImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSpeed LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Hugging Face implementation
class HuggingFaceImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using Hugging Face API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Hugging Face specific parameters as needed
    ):
        raise NotImplementedError("HuggingFaceImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("HuggingFaceImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Hugging Face API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Hugging Face API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("HuggingFaceImplementation LangChain init not implemented.")
        # from langchain_huggingface import HuggingFace
        # try:
        #     self._langchain_llm = HuggingFace(
        #         huggingface_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Hugging Face wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Hugging Face wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("HuggingFaceImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Hugging Face LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Hugging Face model: {e}")
        #     # Handle specific Hugging Face errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Hugging Face invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("HuggingFaceImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Hugging Face LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Azure implementation
class AzureImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using Azure API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Azure specific parameters as needed
    ):
        raise NotImplementedError("AzureImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("AzureImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Azure API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Azure API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("AzureImplementation LangChain init not implemented.")
        # from langchain_azure import Azure
        # try:
        #     self._langchain_llm = Azure(
        #         azure_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Azure wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Azure wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("AzureImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Azure LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Azure model: {e}")
        #     # Handle specific Azure errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Azure invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("AzureImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Azure LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future AWS implementation
class AWSImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using AWS API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other AWS specific parameters as needed
    ):
        raise NotImplementedError("AWSImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("AWSImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking AWS API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid AWS API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("AWSImplementation LangChain init not implemented.")
        # from langchain_aws import AWS
        # try:
        #     self._langchain_llm = AWS(
        #         aws_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain AWS wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain AWS wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("AWSImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("AWS LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking AWS model: {e}")
        #     # Handle specific AWS errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during AWS invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("AWSImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("AWS LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future DeepSeek implementation
class DeepSeekImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using DeepSeek API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other DeepSeek specific parameters as needed
    ):
        raise NotImplementedError("DeepSeekImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("DeepSeekImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking DeepSeek API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid DeepSeek API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("DeepSeekImplementation LangChain init not implemented.")
        # from langchain_deepseek import DeepSeek
        # try:
        #     self._langchain_llm = DeepSeek(
        #         deepseek_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain DeepSeek wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain DeepSeek wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("DeepSeekImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSeek LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking DeepSeek model: {e}")
        #     # Handle specific DeepSeek errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during DeepSeek invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("DeepSeekImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSeek LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Qwen implementation
class QwenImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using Qwen API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Qwen specific parameters as needed
    ):
        raise NotImplementedError("QwenImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("QwenImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Qwen API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Qwen API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("QwenImplementation LangChain init not implemented.")
        # from langchain_qwen import Qwen
        # try:
        #     self._langchain_llm = Qwen(
        #         qwen_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Qwen wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Qwen wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("QwenImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Qwen LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Qwen model: {e}")
        #     # Handle specific Qwen errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Qwen invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("QwenImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Qwen LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future Baichuan implementation
class BaichuanImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using Baichuan API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other Baichuan specific parameters as needed
    ):
        raise NotImplementedError("BaichuanImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("BaichuanImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking Baichuan API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid Baichuan API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("BaichuanImplementation LangChain init not implemented.")
        # from langchain_baichuan import Baichuan
        # try:
        #     self._langchain_llm = Baichuan(
        #         baichuan_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain Baichuan wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain Baichuan wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("BaichuanImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Baichuan LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking Baichuan model: {e}")
        #     # Handle specific Baichuan errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during Baichuan invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("BaichuanImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("Baichuan LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future LLaMA implementation
class LLaMAImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using LLaMA API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other LLaMA specific parameters as needed
    ):
        raise NotImplementedError("LLaMAImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("LLaMAImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking LLaMA API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid LLaMA API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("LLaMAImplementation LangChain init not implemented.")
        # from langchain_llama import LLaMA
        # try:
        #     self._langchain_llm = LLaMA(
        #         llama_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain LLaMA wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain LLaMA wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("LLaMAImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("LLaMA LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking LLaMA model: {e}")
        #     # Handle specific LLaMA errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during LLaMA invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("LLaMAImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("LLaMA LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm


# Placeholder for future DeepSpeed implementation
class DeepSpeedImplementation(LLMRunner):
    """
    Concrete implementation for running LLMs using DeepSpeed API. (Placeholder)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        # Add other DeepSpeed specific parameters as needed
    ):
        raise NotImplementedError("DeepSpeedImplementation is not yet implemented.")
        # self.api_key = api_key
        # self.model_name = model_name
        # self.temperature = temperature
        # self._langchain_llm = None
        # self.ensure_model_available() # Check API key validity maybe?
        # self._initialize_langchain_llm()


    def ensure_model_available(self) -> None:
         raise NotImplementedError("DeepSpeedImplementation model check not implemented.")
         # Potentially check API key validity here
         # logger.info("Checking DeepSpeed API key validity...")
         # try:
         #     # Make a simple, cheap API call to test the key
         #     pass
         # except Exception as e:
         #     raise ConnectionError(f"Invalid DeepSpeed API Key or connection error: {e}")

    def _initialize_langchain_llm(self) -> None:
        raise NotImplementedError("DeepSpeedImplementation LangChain init not implemented.")
        # from langchain_deepspeed import DeepSpeed
        # try:
        #     self._langchain_llm = DeepSpeed(
        #         deepspeed_api_key=self.api_key,
        #         model_name=self.model_name,
        #         temperature=self.temperature
        #     )
        #     logger.info(f"Initialized LangChain DeepSpeed wrapper for model: {self.model_name}")
        # except Exception as e:
        #     logger.error(f"Failed to initialize LangChain DeepSpeed wrapper: {e}")
        #     self._langchain_llm = None


    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("DeepSpeedImplementation invoke is not yet implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSpeed LLM (LangChain wrapper) is not initialized.")
        # try:
        #     response = self._langchain_llm.invoke(prompt)
        #     return response
        # except Exception as e:
        #     logger.error(f"Error invoking DeepSpeed model: {e}")
        #     # Handle specific DeepSpeed errors (rate limits, auth, etc.)
        #     raise RuntimeError(f"Error during DeepSpeed invocation: {e}")

    def get_langchain_llm(self) -> Any:
         raise NotImplementedError("DeepSpeedImplementation get_langchain_llm not implemented.")
        # if self._langchain_llm is None:
        #      raise RuntimeError("DeepSpeed LLM (LangChain wrapper) is not initialized.")
        # return self._langchain_llm 