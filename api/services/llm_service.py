"""
LLM Service module for handling LLM-based question answering with context.

This module provides functionality to answer questions using a lightweight LLM
with context retrieval and processing via LangChain.
"""

from typing import Dict, List, Any, Optional, Union, Type
import os
import logging
import requests
import time
import re
import json
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.schema import Document

# Import the LLMRunner abstraction
from api.utils.llm_runners import LLMRunner, OllamaRunner

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMService:
    """
    Service for LLM-based question answering with context retrieval.
    
    Uses an LLMRunner for model interaction and LangChain for context
    processing and retrieval.
    """
    
    def __init__(
        self,
        llm_runner: Optional[LLMRunner] = None,
        ollama_base_url: str = "http://ollama:11434",
        model_name: str = "gemma3:4b",
        temperature: float = 0.1,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        max_retries: int = 3,
        retry_delay: int = 5,
    ):
        """
        Initialize the LLM Service.
        
        Args:
            llm_runner: LLMRunner instance to use for LLM operations
            ollama_base_url: Base URL for the Ollama API (used only if llm_runner not provided)
            model_name: Name of the model to use (used only if llm_runner not provided)
            temperature: Temperature parameter for LLM generation (used only if llm_runner not provided)
            embedding_model: HuggingFace model name for embeddings
            chunk_size: Size of text chunks for splitting documents
            chunk_overlap: Overlap between text chunks
            max_retries: Maximum number of retries (used only if llm_runner not provided)
            retry_delay: Delay between retries in seconds (used only if llm_runner not provided)
            
        Returns:
            None
            
        Raises:
            ConnectionError: If unable to connect to LLM service
        """
        self.embedding_model_name = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Initialize the LLM runner (use provided one or create OllamaRunner)
        if llm_runner is not None:
            self.llm_runner = llm_runner
        else:
            logger.info(f"No LLM runner provided, creating OllamaRunner with model: {model_name}")
            self.llm_runner = OllamaRunner(
                base_url=ollama_base_url,
                model_name=model_name,
                temperature=temperature,
                max_retries=max_retries,
                retry_delay=retry_delay
            )
        
        # Initialize other components
        self._init_embeddings()
        self._init_text_splitter()
        
        logger.info(f"LLMService initialized with runner type: {type(self.llm_runner).__name__}")
    
    def _init_embeddings(self) -> None:
        """
        Initialize the embedding model.
        
        Args:
            None
            
        Returns:
            None
            
        Raises:
            ImportError: If required dependencies are missing
        """
        try:
            self.embeddings = HuggingFaceEmbeddings(
                model_name=self.embedding_model_name,
                model_kwargs={"device": "cuda"},
            )
            logger.info(f"Initialized embeddings with model: {self.embedding_model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {str(e)}")
            raise ImportError(f"Could not load embedding model: {str(e)}")
    
    def _init_text_splitter(self) -> None:
        """
        Initialize the text splitter for document chunking.
        
        Args:
            None
            
        Returns:
            None
        """
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
        )
        logger.info(f"Initialized text splitter with chunk size: {self.chunk_size}, overlap: {self.chunk_overlap}")
    
    def create_vector_store(self, documents: List[Union[str, Document]]) -> FAISS:
        """
        Create a vector store from documents for retrieval.
        
        Args:
            documents: List of documents or text strings to index
            
        Returns:
            FAISS: Vector store for document retrieval
            
        Raises:
            ValueError: If documents list is empty
        """
        if not documents:
            raise ValueError("Documents list cannot be empty")
        
        # Convert string documents to Document objects if needed
        doc_objects = []
        for doc in documents:
            if isinstance(doc, str):
                doc_objects.append(Document(page_content=doc))
            elif isinstance(doc, Document):
                doc_objects.append(doc)
            else:
                raise TypeError(f"Unsupported document type: {type(doc)}")
        
        # Check if this is structured model information
        is_model_info = any(
            isinstance(doc, Document) and 
            doc.page_content.startswith("Model Name:") and
            "== Model Properties ==" in doc.page_content
            for doc in doc_objects
        )
        
        if is_model_info:
            # Use specialized splitting for model information
            splits = self._split_model_information(doc_objects)
            logger.info(f"Split model information into {len(splits)} semantic chunks")
        else:
            # Use standard text splitting
            splits = self.text_splitter.split_documents(doc_objects)
            logger.info(f"Split {len(doc_objects)} documents into {len(splits)} chunks")
        
        # Create vector store
        vector_store = FAISS.from_documents(splits, self.embeddings)
        logger.info("Created FAISS vector store from documents")
        
        return vector_store
    
    def _split_model_information(self, documents: List[Document]) -> List[Document]:
        """
        Split model information documents in a semantically meaningful way.
        
        This method preserves the structure of model information by splitting
        at section boundaries and keeping related information together.
        
        Args:
            documents: List of Document objects containing model information
            
        Returns:
            List[Document]: Semantically split documents
        """
        result_chunks = []
        
        for doc in documents:
            content = doc.page_content
            
            # Define section patterns
            section_patterns = [
                r"Model Name:",
                r"== Model Properties ==",
                # r"== Performance Metrics ==",
                # r"== Version History =="
            ]
            
            # Find all section boundaries
            section_boundaries = []
            for pattern in section_patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    section_boundaries.append(match.start())
            
            # Sort boundaries and add end of document
            section_boundaries.sort()
            section_boundaries.append(len(content))
            
            # If no sections found or only one section, use regular text splitter
            if len(section_boundaries) <= 1:
                chunks = self.text_splitter.split_text(content)
                for chunk in chunks:
                    result_chunks.append(Document(page_content=chunk, metadata=doc.metadata))
                continue
            
            # Split by sections, then by size if needed
            prev_boundary = 0
            for boundary in section_boundaries:
                if boundary == prev_boundary:
                    continue
                    
                section_text = content[prev_boundary:boundary].strip()
                
                # If section is too large, split it further
                if len(section_text) > self.chunk_size * 1.5:
                    sub_chunks = self.text_splitter.split_text(section_text)
                    for chunk in sub_chunks:
                        result_chunks.append(Document(page_content=chunk, metadata=doc.metadata))
                else:
                    result_chunks.append(Document(page_content=section_text, metadata=doc.metadata))
                
                prev_boundary = boundary
        
        return result_chunks
    
    def create_qa_chain(
        self, 
        vector_store: FAISS,
        chain_type: str = "stuff",
        prompt_template: Optional[str] = None,
    ) -> RetrievalQA:
        """
        Create a question-answering chain with the given vector store.
        
        Args:
            vector_store: Vector store for document retrieval
            chain_type: Type of chain to use (stuff, map_reduce, refine)
            prompt_template: Custom prompt template string
            
        Returns:
            RetrievalQA: Question-answering chain
        """
        # Create retriever
        retriever = vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 3}
        )
        
        # Create custom prompt if provided
        if prompt_template:
            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "question"]
            )
            chain_type_kwargs = {"prompt": prompt}
        else:
            chain_type_kwargs = {}
        
        # Get langchain LLM from the runner
        llm = self.llm_runner.get_langchain_llm()
        
        # Create QA chain
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type=chain_type,
            retriever=retriever,
            return_source_documents=True,
            chain_type_kwargs=chain_type_kwargs,
        )
        
        logger.info(f"Created QA chain with chain type: {chain_type}")
        return qa_chain
    
    def answer_question(
        self, 
        qa_chain: RetrievalQA, 
        question: str
    ) -> Dict[str, Any]:
        """
        Answer a question using the provided QA chain.
        
        Args:
            qa_chain: Question-answering chain
            question: Question to answer
            
        Returns:
            Dict[str, Any]: Answer, source documents, and raw LLM output string.
            
        Raises:
            ValueError: If question is empty
        """
        if not question.strip():
            raise ValueError("Question cannot be empty")
        
        logger.info(f"Answering question: {question}")
        raw_llm_output = ""
        try:
            # Invoke the chain
            result = qa_chain.invoke({"query": question})
            
            # The raw answer from the LLM is typically in result['result']
            raw_llm_output = result.get("result", "")
            
            # Format the response
            response = {
                "answer": raw_llm_output, # The 'answer' now contains the raw LLM text
                "source_documents": [
                    {
                        "content": doc.page_content,
                        "metadata": doc.metadata
                    }
                    for doc in result.get("source_documents", [])
                ],
                "raw_llm_output": raw_llm_output # Explicitly add raw output field
            }
            
            return response
        except Exception as e:
            logger.error(f"Error answering question: {str(e)}")
            raise RuntimeError(f"Failed to answer question: {str(e)}")
    
    def process_and_answer(
        self, 
        question: str, 
        context_documents: List[Union[str, Document]],
        prompt_template: Optional[str] = None,
        expect_json_output: bool = False # Added flag (though not strictly used internally here)
    ) -> Dict[str, Any]:
        """
        Process documents and answer a question in one step.
        
        Args:
            question: Question to answer
            context_documents: List of documents or text strings for context
            prompt_template: Optional custom prompt template
            
        Returns:
            Dict[str, Any]: Answer, source documents, and raw LLM output.
            
        Raises:
            ValueError: If question or context_documents are empty
        """
        if not question.strip():
            raise ValueError("Question cannot be empty")
        
        if not context_documents:
            raise ValueError("Context documents cannot be empty")
        
        # Create vector store from documents
        vector_store = self.create_vector_store(context_documents)
        
        # Create QA chain
        qa_chain = self.create_qa_chain(
            vector_store=vector_store,
            prompt_template=prompt_template
        )
        
        # Answer question
        return self.answer_question(qa_chain, question)

    def process_free_response(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        extended: bool = False,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Processes a single turn in a conversational search interaction.
        To answer a free response from the user.
        """
        
        if not user_message.strip():
            raise ValueError("User message cannot be empty")

        logger.info(f"Processing conversation turn. Latest message: {user_message}")

        # Construct the prompt
        prompt_template = """
        You are an expert AI assistant helping users search for ML models/datasets in MLentory.
        Your goal is to understand intent, refine queries, and expand the understanding of the user.
        CONTEXT:
        - Conversation history:
        {history}

        - Latest user message:
        {user_message}

        INSTRUCTIONS:
        1. Answer the user's question with the intent to help them understand complex ML concepts.
           - For broad queries: suggest specific ML tasks, model types, or use cases
           - For specific queries: validate and enhance with relevant technical terms
           - For unclear queries: ask ONE focused clarifying question
           - Offer explanations for specific terms or concepts
           - When explaining technical terms, provide context and examples
        
        2. Query refinement rules:
           - NEVER return the exact input query unless it's already optimal
           - Add relevant ML-specific terms (e.g., "transformer" → "vision transformer", "bert" → "bert-base-uncased")
           - Remove unnecessary words while preserving intent
           - If query seems complete, focus on filter suggestions instead

        3. Suggested questions for unclear terms:
           - If the user mentions technical terms that might be confusing (e.g., "transformer", "BERT", "fine-tuning", "embeddings")
           - Provide 2-3 specific follow-up questions to help clarify their intent
           - Questions should be practical and help narrow down their search
           - Examples: "Are you looking for vision transformers or language transformers?", "Do you need pre-trained models or training scripts?"

        4. Response format:
           - Keep responses concise but informative
           - Explain your refinements briefly
           - For clarifying questions, explain why you need the information

        Return ONLY a JSON object with these exact keys (no other text):
        {{
          "response": "Your concise response or question with explanations",
          "refined_query": "Your improved search query (or empty string if asking for clarification)",
          "state": "needs_clarification" / "ready_to_search" / "has_answer",
          "suggested_questions": ["Question 1 about the term/concept", "Question 2 for clarification", "Question 3 for specifics"]
        }}
        """

        history_lines = []
        for msg in conversation_history[-3:]:  # Only include last 3 messages for context
            role = "User" if msg['role'] == "user" else "Assistant"
            content = msg['content'].replace('\n', ' ').strip()
            history_lines.append(f"{role}: {content}")
        history_str = "\n".join(history_lines) if history_lines else "No previous conversation."
        
        formatted_prompt = prompt_template.format(
            history=history_str, 
            user_message=user_message
        )
        
        logger.debug(f"Formatted prompt for LLM:\n{formatted_prompt}")

        raw_llm_output = "" # Initialize
        try:
            # Use the LLM runner to generate the response
            raw_llm_output = self.llm_runner.invoke(formatted_prompt)
            logger.info(f"Raw LLM Output: {raw_llm_output}")
            
            parsed_output = self._parse_llm_json_output(raw_llm_output)
            logger.info(f"Parsed output: {parsed_output}")
            # Ensure raw output is included even on successful parse
            parsed_output["raw_llm_output"] = raw_llm_output 
            # parsed_output["suggested_filters"] = {}
            return parsed_output

        except Exception as e:
            logger.error(f"Error processing conversation turn with LLM: {str(e)}")
            # Fallback response, include raw output if available
            return {
                "response": "I encountered an issue trying to process that. Could you please rephrase or try again?",
                "suggested_filters": {},
                "refined_query": "",
                "state": "error",
                "suggested_questions": [],
                "raw_llm_output": raw_llm_output # Include raw output in error case too
            }
    
    def process_search_conversation_turn(
        self, 
        user_message: str, 
        conversation_history: List[Dict[str, str]],
        available_filters: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, Any]:
        """
        Processes a single turn in a conversational search interaction.

        Analyzes the user message in the context of the conversation history
        to refine the search query, suggest filters, and ask clarifying questions.

        Args:
            user_message (str): The latest message from the user.
            conversation_history (List[Dict[str, str]]): The history of the conversation,
                where each dict has "role" (e.g., "user", "assistant") and "content".
            available_filters (Optional[Dict[str, List[str]]]): Dictionary of 
                available filter properties and their potential values, if known.

        Returns:
            Dict[str, Any]: A dictionary containing:
                - "response": The LLM's textual response to the user.
                - "suggested_filters": Dictionary of suggested filters {property: [values]}.
                - "refined_query": The refined search query string, if generated.
                - "state": Indication of the conversation state:
                    - "needs_clarification": More information needed from user
                    - "ready_to_search": Query is ready to be executed 
                    - "has_answer": Response contains direct answer to user's question
                    - "error"/"parsing_failed": System error states
                - "raw_llm_output": The raw output from the LLM.

        Raises:
            ValueError: If user_message is empty.
            RuntimeError: If the LLM fails to generate a response.
        """
        if not user_message.strip():
            raise ValueError("User message cannot be empty")

        logger.info(f"Processing conversation turn. Latest message: {user_message}")

        # Construct the prompt
        prompt_template = """
        You are an expert AI assistant helping users search for ML models/datasets in MLentory.
        Your goal is to understand intent, refine queries, and suggest relevant filters.

        CONTEXT:
        - Conversation history:
        {history}

        - Available filter properties and examples:
        {filters_info}

        - Latest user message:
        {user_message}

        INSTRUCTIONS:
        1. ALWAYS analyze and refine the user's search intent:
           - For broad queries: suggest specific ML tasks, model types, or use cases
           - For specific queries: validate and enhance with relevant technical terms
           - For unclear queries: ask ONE focused clarifying question
        
        2. Query refinement rules:
           - NEVER return the exact input query unless it's already optimal
           - Add relevant ML-specific terms (e.g., "transformer" → "vision transformer", "bert" → "bert-base-uncased")
           - Remove unnecessary words while preserving intent
           - If query seems complete, focus on filter suggestions instead
        
        3. Filter suggestions:
           - Only use filters from the Available filter properties
           - Suggest 1-2 most relevant filters based on the query
           - Prefer values from the examples when possible
           - Keep suggestions focused and specific to the query

        4. Response format:
           - Keep responses concise (<= 50 words)
           - Explain your refinements briefly
           - For clarifying questions, explain why you need the information

        Return ONLY a JSON object with these exact keys (no other text):
        {{
          "response": "Your concise response or question",
          "suggested_filters": {{ "property": ["value1", "value2"] }},
          "refined_query": "Your improved search query (or empty string if asking for clarification)",
          "state": "needs_clarification" / "ready_to_search" / "has_answer" 
        }}
        """

        # Format conversation history compactly
        history_lines = []
        for msg in conversation_history[-3:]:  # Only include last 3 messages for context
            role = "User" if msg['role'] == "user" else "Assistant"
            content = msg['content'].replace('\n', ' ').strip()
            history_lines.append(f"{role}: {content}")
        history_str = "\n".join(history_lines) if history_lines else "No previous conversation."
        
        # Format available filters compactly
        filters_str = "Not available."
        if available_filters:
            filter_lines = []
            for prop, vals in available_filters.items():
                if not vals:
                    continue
                # Take first 5 values as examples, ensure they're clean and lowercase
                examples = [str(v).lower().strip().replace('_', ' ') for v in vals[:5] if v]
                if examples:
                    total = len(vals)
                    preview = ", ".join(examples)
                    filter_lines.append(f"- {prop} ({total} total): {preview}")
            filters_str = "\n".join(filter_lines) if filter_lines else "No filter examples available."
            
        formatted_prompt = prompt_template.format(
            history=history_str, 
            filters_info=filters_str,
            user_message=user_message
        )
        
        logger.debug(f"Formatted prompt for LLM:\n{formatted_prompt}")

        raw_llm_output = "" # Initialize
        try:
            # Use the LLM runner to generate the response
            raw_llm_output = self.llm_runner.invoke(formatted_prompt)
            logger.info(f"Raw LLM Output: {raw_llm_output}")
            
            parsed_output = self._parse_llm_json_output(raw_llm_output)
            # Ensure raw output is included even on successful parse
            parsed_output["raw_llm_output"] = raw_llm_output 
            return parsed_output

        except Exception as e:
            logger.error(f"Error processing conversation turn with LLM: {str(e)}")
            # Fallback response, include raw output if available
            return {
                "response": "I encountered an issue trying to process that. Could you please rephrase or try again?",
                "suggested_filters": {},
                "refined_query": "",
                "state": "error",
                "raw_llm_output": raw_llm_output # Include raw output in error case too
            }

    def _parse_llm_json_output(self, raw_output: str) -> Dict[str, Any]:
        """
        Attempts to parse the expected JSON structure from the LLM's raw text output.

        Args:
            raw_output (str): The raw string output from the LLM.

        Returns:
            Dict[str, Any]: The parsed dictionary, or a default error structure.
        """
        try:
            # Clean up the raw output by removing markdown code blocks
            cleaned_output = raw_output.strip()
            
            # Remove ```json and ``` markers if present
            if cleaned_output.startswith('```json'):
                cleaned_output = cleaned_output[7:]  # Remove ```json
            if cleaned_output.startswith('```'):
                cleaned_output = cleaned_output[3:]   # Remove ```
            if cleaned_output.endswith('```'):
                cleaned_output = cleaned_output[:-3]  # Remove closing ```
            
            cleaned_output = cleaned_output.strip()
            
            # Find the JSON block within the cleaned output
            json_match = re.search(r'\{.*\}', cleaned_output, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                parsed = json.loads(json_str)
                
                # Validate expected keys
                expected_keys = {"response", "refined_query", "state"}
                if expected_keys.issubset(parsed.keys()):
                    # Basic type validation (can be expanded)
                    if not isinstance(parsed["response"], str): raise TypeError("response is not str")
                    # if not isinstance(parsed["suggested_filters"], dict): raise TypeError("suggested_filters is not dict")
                    if not isinstance(parsed["refined_query"], str): raise TypeError("refined_query is not str")
                    if parsed["state"] not in ["needs_clarification", "ready_to_search", "has_answer"]: raise ValueError("Invalid state value")
                    
                    # Validate suggested_questions if present
                    if "suggested_questions" in parsed:
                        if not isinstance(parsed["suggested_questions"], list): 
                            raise TypeError("suggested_questions is not list")
                        # Ensure all items are strings
                        if not all(isinstance(q, str) for q in parsed["suggested_questions"]):
                            raise TypeError("suggested_questions contains non-string items")
                    else:
                        # Add empty list if not provided
                        parsed["suggested_questions"] = []
                    
                    logger.info("Successfully parsed JSON output from LLM.")
                    return parsed
                else:
                    logger.warning("Parsed JSON missing expected keys.")
            else:
                logger.warning("No JSON block found in LLM output.")

        except Exception as e:
            logger.error(f"Failed to parse JSON from LLM output: {str(e)}. Raw output: {raw_output}")

        # Fallback if parsing fails - raw output added by caller
        return {
            "response": raw_output, 
            "suggested_filters": {},
            "refined_query": "",
            "state": "parsing_failed", 
            "suggested_questions": [] # Add empty list for fallback
        } 
    
    def refine_query_and_suggest_filters(
        self, 
        current_query: str,
        current_filters: Dict[str, List[str]],
        available_filters: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, Any]:
        """
        Analyzes a current query and filters to suggest refinements.

        Focuses on asking clarifying questions, suggesting new/modified filters,
        and proposing a refined query text, without determining a search readiness state.

        Args:
            current_query (str): The user's current search query text.
            current_filters (Dict[str, List[str]]): Filters currently applied by the user.
            available_filters (Optional[Dict[str, List[str]]]): Dictionary of 
                available filter properties and their potential values, if known.

        Returns:
            Dict[str, Any]: A dictionary containing:
                - "response": Textual response/questions for the user.
                - "suggested_filters": Dictionary of *new* or *modified* filters {property: [values]}.
                - "refined_query": The refined search query string, if one is proposed.

        Raises:
            RuntimeError: If the LLM fails to generate a response.
        """
        logger.info(f"Refining query: '{current_query}' with filters: {current_filters}")

        # Construct the prompt (compact and token-aware)
        prompt_template = """You are an expert assistant helping refine a search for ML models.

IMPORTANT: Return ONLY a JSON object. No other text, no explanations, no analysis.

CONTEXT:
- Allowed filter properties (use EXACT names, do not invent new ones): {allowed_props}
- Available filter examples:
{filters_info}

CURRENT:
- query: {query}
- filters: {applied_filters}

INSTRUCTIONS:
1. Keep "response" concise (<= 80 words). Ask at most 1 clarifying question if intent is unclear.
2. Only suggest properties from Allowed filter properties.
3. Prefer values that appear in Available filter examples. If none match, propose generic but realistic values.
4. Suggest at most 2 properties and up to 3 values per property.
5. Do not duplicate values already present in filters. Prefer canonical, lowercase values.
6. If no strong refinement is evident, leave "refined_query" as an empty string.

REQUIRED FORMAT (return exactly this JSON structure with no other text):
{{
  "response": "Your concise response or question here",
  "suggested_filters": {{ "property": ["value1", "value2"] }},
  "refined_query": "refined query text or empty string"
}}"""

        filters_str = "Not available."
        allowed_props_str = "mlTask, keywords, license"
        if available_filters:
            try:
                allowed_props_str = ", ".join(sorted(list(available_filters.keys())))
                lines = []
                for prop, vals in available_filters.items():
                    if not vals:
                        continue
                    seen = set()
                    unique_vals = []
                    for v in vals:
                        s = str(v)
                        if s not in seen:
                            seen.add(s)
                            unique_vals.append(s)
                    total = len(unique_vals)
                    preview = unique_vals[:8]
                    lines.append(f"- {prop} ({total}): " + ", ".join(preview))
                filters_str = "\n".join(lines) if lines else "None."
            except Exception:
                pass
        
        # Compact applied filters
        applied_filters_str = "None"
        if current_filters:
            try:
                compact_filters = {}
                for k, v in current_filters.items():
                    if isinstance(v, list):
                        compact_filters[k] = v[:5]
                    else:
                        compact_filters[k] = v
                applied_filters_str = json.dumps(compact_filters, separators=(",", ":"))
            except Exception:
                applied_filters_str = json.dumps(current_filters, separators=(",", ":"))
            
        formatted_prompt = prompt_template.format(
            allowed_props=allowed_props_str,
            filters_info=filters_str,
            query=current_query if current_query else "(No query text provided)",
            applied_filters=applied_filters_str if applied_filters_str else "None"
        )
        
        # Debugging: keep log concise by not dumping full prompt content
        logger.debug("Formatted prompt for LLM refinement prepared (compact mode)")

        raw_llm_output = "" # Initialize
        try:
            # Use the LLM runner to generate the response
            raw_llm_output = self.llm_runner.invoke(formatted_prompt)
            logger.info(f"Raw LLM Output for refinement: {raw_llm_output}")
            
            parsed_output = self._parse_llm_refinement_output(raw_llm_output)
            # Ensure raw output is included even on successful parse
            parsed_output["raw_llm_output"] = raw_llm_output
            return parsed_output

        except Exception as e:
            logger.error(f"Error processing query refinement with LLM: {str(e)}")
            # Fallback response
            return {
                "response": "I encountered an issue trying to refine the query. Please try again.",
                "suggested_filters": {},
                "refined_query": current_query,
                "raw_llm_output": raw_llm_output # Include raw output in error case too
            }

    def _parse_llm_refinement_output(self, raw_output: str) -> Dict[str, Any]:
        """
        Attempts to parse the JSON structure for refinement output from the LLM.
        """
        try:
            # Clean up the raw output by removing markdown code blocks
            cleaned_output = raw_output.strip()
            
            # Remove ```json and ``` markers if present
            if cleaned_output.startswith('```json'):
                cleaned_output = cleaned_output[7:]  # Remove ```json
            if cleaned_output.startswith('```'):
                cleaned_output = cleaned_output[3:]   # Remove ```
            if cleaned_output.endswith('```'):
                cleaned_output = cleaned_output[:-3]  # Remove closing ```
            
            cleaned_output = cleaned_output.strip()
            
            # Find the JSON block within the cleaned output
            json_match = re.search(r'\{.*\}', cleaned_output, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                parsed = json.loads(json_str)
                
                expected_keys = {"response", "suggested_filters", "refined_query"}
                if expected_keys.issubset(parsed.keys()):
                    if not isinstance(parsed["response"], str): raise TypeError("response is not str")
                    if not isinstance(parsed["suggested_filters"], dict): raise TypeError("suggested_filters is not dict")
                    if not isinstance(parsed["refined_query"], str): raise TypeError("refined_query is not str")
                    
                    logger.info("Successfully parsed JSON refinement output from LLM.")
                    return parsed
                else:
                    logger.warning("Parsed refinement JSON missing expected keys.")
            else:
                logger.warning("No JSON block found in LLM refinement output.")

        except Exception as e:
            logger.error(f"Failed to parse refinement JSON from LLM output: {str(e)}. Raw output: {raw_output}")

        # Fallback if parsing fails
        return {
            "response": raw_output, 
            "suggested_filters": {},
            "refined_query": "", 
            # raw_llm_output field added by the calling method
        }

    def improve_query_only(
        self,
        current_query: str,
        search_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyzes and improves only the search query text, asking useful guiding questions.

        This method focuses exclusively on query improvement without suggesting filters.
        It provides clarifying questions to help users refine their search intent and
        suggests improved query formulations.

        Args:
            current_query (str): The user's current search query text.
            search_context (Optional[str]): Optional context about what the user is looking for.

        Returns:
            Dict[str, Any]: A dictionary containing:
                - "response": Textual response with questions and guidance for the user.
                - "improved_query": An improved version of the search query, if one can be suggested.
                - "clarifying_questions": A list of specific questions to help refine the search.
                - "query_suggestions": Alternative query formulations to consider.
                - "raw_llm_output": The raw output from the LLM.

        Raises:
            RuntimeError: If the LLM fails to generate a response.
        """
        logger.info(f"Improving query only: '{current_query}'")

        # Construct a focused prompt for query improvement
        prompt_template = """You are an expert ML search assistant helping users improve their search queries for finding machine learning models and datasets.

IMPORTANT: Return ONLY a JSON object. No other text, explanations, or analysis outside the JSON.

CURRENT QUERY: "{query}"
SEARCH CONTEXT: {context}

YOUR TASK:
1. Analyze the current query for clarity, specificity, and searchability
2. Suggest an improved version that uses better ML terminology and is more specific
3. Ask 2-3 clarifying questions to help the user refine their intent
4. Provide 2-3 alternative query formulations

GUIDELINES:
- Focus ONLY on query text improvement, not filters
- Use proper ML terminology (e.g., "transformer" instead of "text model", "computer vision" instead of "image AI")
- Make queries more specific and searchable
- Ask questions that help narrow down: task type, domain, model architecture, use case
- Keep responses concise and actionable
- If the query is already good, suggest minor refinements or ask about specific requirements

REQUIRED FORMAT (return exactly this JSON structure):
{{
  "response": "Brief helpful response with guidance (max 100 words)",
  "improved_query": "Your improved version of the query or empty string if no improvement needed",
  "clarifying_questions": ["Question 1?", "Question 2?", "Question 3?"],
  "query_suggestions": ["Alternative query 1", "Alternative query 2", "Alternative query 3"],
  "search_tips": "One practical tip for better search results"
}}"""

        # Format the context
        context_str = search_context if search_context else "General ML model/dataset search"
        
        formatted_prompt = prompt_template.format(
            query=current_query if current_query else "(No query provided)",
            context=context_str
        )
        
        logger.debug("Formatted prompt for query improvement prepared")

        raw_llm_output = ""
        try:
            # Use the LLM runner to generate the response
            raw_llm_output = self.llm_runner.invoke(formatted_prompt)
            logger.info(f"Raw LLM Output for query improvement: {raw_llm_output}")
            
            parsed_output = self._parse_query_improvement_output(raw_llm_output)
            # Ensure raw output is included
            parsed_output["raw_llm_output"] = raw_llm_output
            return parsed_output

        except Exception as e:
            logger.error(f"Error processing query improvement with LLM: {str(e)}")
            # Fallback response
            return {
                "response": "I encountered an issue trying to improve the query. Please try again.",
                "improved_query": current_query,
                "clarifying_questions": [],
                "query_suggestions": [],
                "search_tips": "Try using more specific ML terminology in your search.",
                "raw_llm_output": raw_llm_output
            }

    def _parse_query_improvement_output(self, raw_output: str) -> Dict[str, Any]:
        """
        Attempts to parse the JSON structure for query improvement output from the LLM.

        Args:
            raw_output (str): The raw string output from the LLM.

        Returns:
            Dict[str, Any]: The parsed dictionary, or a default structure.
        """
        try:
            # Find content within ```json ... ```
            match = re.search(r'```json\s*(\{.*?\})\s*```', raw_output, re.DOTALL)
            json_str = None
            if match:
                json_str = match.group(1)
            else:
                # Fallback: find content within ``` ... ```
                match = re.search(r'```\s*(\{.*?\})\s*```', raw_output, re.DOTALL)
                if match:
                    json_str = match.group(1)
                else:
                    # Fallback: find any json blob, assuming it's the last one
                    match = re.search(r'(\{.*\})', raw_output, re.DOTALL)
                    if match:
                        json_str = match.group(1)
            
            if json_str:
                parsed = json.loads(json_str)
                
                expected_keys = {"response", "improved_query", "clarifying_questions", "query_suggestions", "search_tips"}
                if expected_keys.issubset(parsed.keys()):
                    # Basic type validation
                    if not isinstance(parsed["response"], str): raise TypeError("response is not str")
                    if not isinstance(parsed["improved_query"], str): raise TypeError("improved_query is not str")
                    if not isinstance(parsed["clarifying_questions"], list): raise TypeError("clarifying_questions is not list")
                    if not isinstance(parsed["query_suggestions"], list): raise TypeError("query_suggestions is not list")
                    if not isinstance(parsed["search_tips"], str): raise TypeError("search_tips is not str")
                    
                    logger.info("Successfully parsed JSON query improvement output from LLM.")
                    return parsed
                else:
                    logger.warning("Parsed query improvement JSON missing expected keys.")
            else:
                logger.warning("No JSON block found in LLM query improvement output.")

        except Exception as e:
            logger.error(f"Failed to parse query improvement JSON from LLM output: {str(e)}. Raw output: {raw_output}")

        # Fallback if parsing fails
        return {
            "response": raw_output, 
            "improved_query": "",
            "clarifying_questions": [],
            "query_suggestions": [],
            "search_tips": "Try using more specific ML terminology.",
        } 