"""
Router for LLM-related endpoints.
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import traceback
import json # Added for parsing potential JSON from LLM
import re # Added for regular expression operations

# Import controllers
from api.controllers.LLMController import LLMController
from api.controllers.ModelContextProcessor import ModelContextProcessor
from api.controllers.PlatformDocsController import PlatformDocsController
from api.controllers.SearchController import SearchController
from api.controllers.EntityController import EntityController

# Create router with prefix and tags
router = APIRouter(prefix="/llm", tags=["LLM"])

# Default model ID for examples
default_model_id = "<https://w3id.org/mlentory/mlentory_graph/3939aa6b6b70406f21c21b35514e79ea6603b996a3d733486f66e91adbd06f98>"

# --- Define Known Filterable Fields --- 
# List of fields that are actually filterable in the SearchController.search_models_with_filters method
# (Based on the fields used in the query building logic there)
KNOWN_FILTERABLE_FIELDS = {
    "mlTask", 
    "keywords", 
    "license", 
    "sharedBy", 
    "baseModels", 
    "relatedDatasets"
    # Add any other fields you intend to allow filtering on
}

# Controller dependencies
def get_llm_controller():
    from main import llmController
    return llmController

def get_model_context_processor():
    from main import modelContextProcessor
    return modelContextProcessor

def get_platform_docs_controller():
    from main import platformDocsController
    return platformDocsController

def get_search_controller():
    from main import searchController
    return searchController

def get_entity_controller():
    from main import entityController
    return entityController

# Define Pydantic models for request and response
class QuestionRequest(BaseModel):
    """
    Request model for question answering.
    """
    question: str
    context_documents: List[str]
    model_name: Optional[str] = "llama3.2:1b"
    prompt_template: Optional[str] = None

class AnswerResponse(BaseModel):
    """
    Response model for question answering.
    """
    answer: str
    source_documents: List[Dict[str, Any]]

# --- Pydantic Models for Conversational Search ---

class ConversationMessage(BaseModel):
    role: str = Field(..., description="Role of the message sender (e.g., 'user', 'assistant')")
    content: str = Field(..., description="Content of the message")

class ConversationRequest(BaseModel):
    user_message: str = Field(..., description="The latest message from the user")
    conversation_history: List[ConversationMessage] = Field(..., description="History of the conversation")
    extended: Optional[bool] = Field(default=False, description="Whether to retrieve extended details for search results")
    limit: Optional[int] = Field(default=50, description="Maximum number of search results if a search is performed")

class SearchResultItem(BaseModel): # Define structure for items in search_results
    score: float
    name: str
    mlTask: List[str]
    sharedBy: List[str]
    db_identifier: str
    keywords: List[str]
    baseModels: List[str]
    relatedDatasets: List[str]
    license: List[str]
    # Add other fields that might be present, especially if extended=True
    class Config:
        extra = 'allow' # Allow extra fields if extended=True

class ConversationResponse(BaseModel):
    llm_response: str = Field(..., description="The AI assistant's textual response to the user.")
    suggested_filters: Dict[str, List[str]] = Field(..., description="Suggested filters based on the conversation.")
    refined_query: str = Field(..., description="The query refined by the LLM based on the conversation.")
    conversation_state: str = Field(..., description="Current state of the conversation (e.g., 'needs_clarification', 'ready_to_search').")
    search_results: List[SearchResultItem] = Field(..., description="List of search results, if any were triggered and found.")
    suggested_questions: List[str] = Field(default_factory=list, description="List of suggested follow-up questions for unclear terms.")
    raw_llm_output: Optional[str] = Field(None, description="The raw text output from the LLM call.")

# --- Pydantic Models for Query Refinement ---

class RefineQueryRequest(BaseModel):
    current_query: str = Field("", description="The current search query text entered by the user.")
    current_filters: Dict[str, List[str]] = Field(default_factory=dict, description="Filters currently selected by the user.")

class RefineQueryResponse(BaseModel):
    response: str = Field(..., description="Textual response/questions from the LLM for the user.")
    suggested_filters: Dict[str, List[str]] = Field(..., description="Dictionary of NEW or MODIFIED filters suggested by the LLM.")
    refined_query: str = Field(..., description="An optional refined query text proposed by the LLM.")
    raw_llm_output: Optional[str] = Field(None, description="The raw text output from the LLM call.")

# --- Pydantic Models for Query Improvement (Query-Only) ---

class ImproveQueryRequest(BaseModel):
    current_query: str = Field(..., description="The current search query text to improve.")
    search_context: Optional[str] = Field(None, description="Optional context about what the user is looking for.")

class ImproveQueryResponse(BaseModel):
    response: str = Field(..., description="Helpful response with guidance from the LLM.")
    improved_query: str = Field(..., description="An improved version of the search query.")
    clarifying_questions: List[str] = Field(..., description="List of questions to help refine the search intent.")
    query_suggestions: List[str] = Field(..., description="Alternative query formulations to consider.")
    search_tips: str = Field(..., description="Practical tip for better search results.")
    raw_llm_output: Optional[str] = Field(None, description="The raw text output from the LLM call.")

# --- Pydantic Models for Model Summarization ---

class SummarizeModelsRequest(BaseModel):
    model_ids: List[str] = Field(..., description="List of model URIs/IDs to summarize.")
    include_raw_json: bool = Field(default=False, description="Whether to include raw JSON in context for LLM.")

class SummarizeModelsResponse(BaseModel):
    summary: str = Field(..., description="The LLM-generated summary of the models.")
    source_documents: List[Dict[str, Any]] = Field(..., description="Source documents used for the summary (formatted model details).")
    raw_llm_output: Optional[str] = Field(None, description="The raw text output from the LLM call.")

class AnswerWithModelAndPlatformDocsResponse(BaseModel):
    """
    Response model for answering questions with model and platform context,
    including suggested follow-up questions.
    """
    answer: str = Field(..., description="The LLM-generated answer to the question.")
    source_documents: List[Dict[str, Any]] = Field(..., description="List of source documents used for context.")
    suggested_follow_up_questions: List[str] = Field(..., description="Suggested follow-up questions based on the context and original question.")
    raw_llm_output: Optional[str] = Field(None, description="The raw text output from the LLM call, potentially containing the structured JSON.")

@router.post("/answer", response_model=AnswerResponse)
def answer_question(
    request: QuestionRequest,
    llm_controller: LLMController = Depends(get_llm_controller)
):
    """
    Answer a question using the LLM with provided context documents.
    
    Args:
        request: Question request containing question, context documents, and optional parameters
        llm_controller: Injected LLM controller
        
    Returns:
        Dict containing the answer and source documents
        
    Raises:
        HTTPException: If there's an error during question answering
    """
    try:
                
        # Process and answer the question
        result = llm_controller.process_and_answer(
            question=request.question,
            context_documents=request.context_documents,
            prompt_template=request.prompt_template
        )
        
        return result
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Question answering error: {str(e)}")

@router.get("/ollama_models")
def list_available_models():
    """
    List available models from Ollama.
    
    Returns:
        Dict containing a list of available models
        
    Raises:
        HTTPException: If there's an error listing models
    """
    try:
        # This is a placeholder - in a real implementation, you would query Ollama for available models
        # For now, we'll return a static list of commonly available lightweight models
        models = [
            {"name": "llama2", "description": "Meta's Llama 2 model"},
            {"name": "mistral", "description": "Mistral 7B model"},
            {"name": "phi", "description": "Microsoft's Phi model"},
            {"name": "gemma", "description": "Google's Gemma model"},
            {"name": "orca-mini", "description": "Orca Mini model"}
        ]
        
        return {"models": models}
    
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error listing models: {str(e)}")

@router.post("/answer_with_model_context")
def answer_with_model_context(
    question: str = Query(..., description="Question to answer"),
    model_id: str = Query(default=default_model_id, description="Model ID to use as context"),
    include_raw_json: bool = Query(default=False, description="Whether to include raw JSON in context"),
    llm_controller: LLMController = Depends(get_llm_controller),
    model_context_processor: ModelContextProcessor = Depends(get_model_context_processor),
    search_controller: SearchController = Depends(get_search_controller)
):
    """
    Answer a question using the LLM with context from a specific model's details.
    
    Args:
        question: Question to answer about the model
        model_id: ID of the model to use as context
        include_raw_json: Whether to include the raw JSON in the context
        llm_controller: Injected LLM controller
        model_context_processor: Injected model context processor
        search_controller: Injected search controller
        
    Returns:
        Dict containing the answer and source documents
        
    Raises:
        HTTPException: If model not found or LLM service unavailable
    """
    try:
        # Get model details to use as context
        model_details = search_controller.search_model_by_id(model_id, extended=False)
        
        if not model_details:
            raise HTTPException(status_code=404, detail=f"Model with ID {model_id} not found")
        
        # Use the first model if a list is returned
        if isinstance(model_details, list):
            model_details = model_details[0]
        
        # Format model details using the ModelContextProcessor
        structured_context = model_context_processor.format_model_details(model_details, include_raw_json)
        
        # Get prompt template from ModelContextProcessor
        prompt_template = model_context_processor.create_single_model_prompt()
        
        # Process and answer the question
        result = llm_controller.process_and_answer(
            question=question,
            context_documents=[structured_context],
            prompt_template=prompt_template
        )
        
        return result
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Question answering error: {str(e)}")

@router.post("/answer_with_model_and_platform_docs", response_model=AnswerWithModelAndPlatformDocsResponse)
def answer_with_model_and_platform_docs(
    question: str = Query(..., description="Question to answer about the model"),
    model_id: str = Query(default=default_model_id, description="Model ID to use as context"),
    platform_name: str = Query(default="huggingface", description="Platform to use for documentation context"),
    include_raw_json: bool = Query(default=False, description="Whether to include raw JSON in model context"),
    llm_controller: LLMController = Depends(get_llm_controller),
    model_context_processor: ModelContextProcessor = Depends(get_model_context_processor),
    platform_docs_controller: PlatformDocsController = Depends(get_platform_docs_controller),
    search_controller: SearchController = Depends(get_search_controller)
):
    """
    Answer a question using the LLM with context from both model details and platform documentation.
    
    Args:
        question: Question to answer about the model
        model_id: ID of the model to use as context
        platform_name: Platform to use for documentation context
        include_raw_json: Whether to include raw JSON in model context
        llm_controller: Injected LLM controller
        model_context_processor: Injected model context processor
        platform_docs_controller: Injected platform docs controller
        search_controller: Injected search controller
        
    Returns:
        Dict containing the answer and source documents
        
    Raises:
        HTTPException: If model or platform not found or LLM service unavailable
    """
    try:
        # Get model details to use as context
        model_details = search_controller.search_model_by_id(model_id, extended=True)
        
        if not model_details or len(model_details) == 0:
            raise HTTPException(status_code=404, detail=f"Model with ID {model_id} not found")
            
        # Use the first model if a list is returned
        if isinstance(model_details, list):
            model_details = model_details[0]
        
        # Format model details using the ModelContextProcessor
        model_context = model_context_processor.format_model_details(model_details, include_raw_json)
        
        # Get relevant documentation context
        platform_context = platform_docs_controller.get_context_for_llm(platform_name, question, max_tokens=3000)
        
        # Combine contexts
        combined_context = f"MODEL INFORMATION:\n{model_context}\n\nPLATFORM DOCUMENTATION:\n{platform_context}"
        
        # Create a simplified prompt template with clear separator markers that avoid JSON examples
        # which can confuse LangChain's template processor
        prompt_template = f"""You are an expert on machine learning models and the {platform_name} platform.
Answer the following question based on both the model information and platform documentation provided.
If you cannot answer the question based on the provided information, say so clearly.

After providing your answer, add "FOLLOW-UP QUESTIONS:" on a new line, and then list 3 relevant follow-up questions
the user might want to ask next. Number each question.

Context:
{{context}}

Question: {{question}}

Answer:"""
        
        # Process and answer the question
        result = llm_controller.process_and_answer(
            question=question,
            context_documents=[combined_context],
            prompt_template=prompt_template
        )
        
        # Parse the answer and follow-up questions using string processing instead of JSON
        raw_output = result.get("answer", "")
        
        # Handle parsing with pattern matching instead of JSON
        follow_up_questions = []
        if "FOLLOW-UP QUESTIONS:" in raw_output:
            parts = raw_output.split("FOLLOW-UP QUESTIONS:")
            parsed_answer = parts[0].strip()
            
            # Extract numbered questions from the second part
            if len(parts) > 1:
                question_text = parts[1].strip()
                # Find numbered questions (1. 2. 3. or 1) 2) 3) format)
                question_matches = re.findall(r'(?:\d[\.\)]\s*)([^\d\.\)][^\n]+)', question_text)
                if question_matches:
                    follow_up_questions = [q.strip() for q in question_matches if q.strip()]
                
                # If numbering isn't found, try to split by lines
                if not follow_up_questions:
                    lines = [line.strip() for line in question_text.split('\n') if line.strip()]
                    follow_up_questions = lines[:3]  # Take up to 3 lines
        else:
            parsed_answer = raw_output
        
        # Return structured response
        return AnswerWithModelAndPlatformDocsResponse(
            answer=parsed_answer,
            source_documents=result.get("source_documents", []),
            suggested_follow_up_questions=follow_up_questions,
            raw_llm_output=raw_output
        )
    
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Model summarization error: {str(e)}")

@router.post("/compare_models")
def compare_models(
    question: str = Query(..., description="Question to answer about the models"),
    model_ids: List[str] = Query(..., description="List of model IDs to compare"),
    include_raw_json: bool = Query(default=False, description="Whether to include raw JSON in context"),
    llm_controller: LLMController = Depends(get_llm_controller),
    model_context_processor: ModelContextProcessor = Depends(get_model_context_processor),
    search_controller: SearchController = Depends(get_search_controller)
):
    """
    Compare multiple models by answering a question about them.
    
    Args:
        question: Question to answer about the models
        model_ids: List of model IDs to compare
        include_raw_json: Whether to include raw JSON in context
        llm_controller: Injected LLM controller
        model_context_processor: Injected model context processor
        search_controller: Injected search controller
        
    Returns:
        Dict containing the answer and source documents
        
    Raises:
        HTTPException: If models not found or LLM service unavailable
    """
    try:
        if not model_ids or len(model_ids) < 2:
            raise HTTPException(status_code=400, detail="At least two model IDs are required for comparison")
            
        # Get details for all models
        model_details_list = []
        model_names = []
        
        for model_id in model_ids:
            model_details = search_controller.search_model_by_id(model_id, extended=True)
            if not model_details:
                raise HTTPException(status_code=404, detail=f"Model with ID {model_id} not found")
                
            # Use the first model if a list is returned
            if isinstance(model_details, list):
                model_details = model_details[0]
                
            model_details_list.append(model_details)
            if "name" in model_details:
                model_names.append(model_details["name"])
            else:
                model_names.append(f"Model {model_id}")
        
        # Format models for comparison using ModelContextProcessor
        combined_context = model_context_processor.format_models_for_comparison(
            model_details_list, 
            model_names,
            include_raw_json
        )
        
        # Get comparison prompt template from ModelContextProcessor
        prompt_template = model_context_processor.create_model_comparison_prompt(len(model_ids))
        
        # Process and answer the question
        result = llm_controller.process_and_answer(
            question=question,
            context_documents=[combined_context],
            prompt_template=prompt_template
        )
        
        return result
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Model comparison error: {str(e)}")

@router.post("/model_aspect_query")
def query_model_aspect(
    question: str = Query(..., description="Question to answer about the model"),
    model_id: str = Query(default=default_model_id, description="Model ID to use as context"),
    aspect: str = Query(..., description="Specific aspect to focus on (e.g., 'performance', 'architecture', 'licensing', 'training')"),
    include_raw_json: bool = Query(default=False, description="Whether to include raw JSON in context"),
    llm_controller: LLMController = Depends(get_llm_controller),
    model_context_processor: ModelContextProcessor = Depends(get_model_context_processor),
    search_controller: SearchController = Depends(get_search_controller)
):
    """
    Answer a question about a specific aspect of a machine learning model.
    
    Args:
        question: Question to answer about the model
        model_id: ID of the model to use as context
        aspect: Specific aspect to focus on (e.g., 'performance', 'architecture')
        include_raw_json: Whether to include raw JSON in context
        llm_controller: Injected LLM controller
        model_context_processor: Injected model context processor
        search_controller: Injected search controller
        
    Returns:
        Dict containing the answer and source documents
        
    Raises:
        HTTPException: If model not found or LLM service unavailable
    """
    try:
        # Get model details to use as context
        model_details = search_controller.search_model_by_id(model_id, extended=True)
        
        if not model_details or len(model_details) == 0:
            raise HTTPException(status_code=404, detail=f"Model with ID {model_id} not found")
            
        # Use the first model if a list is returned
        if isinstance(model_details, list):
            model_details = model_details[0]
        
        # Format model details using the ModelContextProcessor
        structured_context = model_context_processor.format_model_details(model_details, include_raw_json)
        
        # Get aspect-specific prompt template from ModelContextProcessor
        prompt_template = model_context_processor.create_model_aspect_prompt(aspect)
        
        # Process and answer the question
        result = llm_controller.process_and_answer(
            question=question,
            context_documents=[structured_context],
            prompt_template=prompt_template
        )
        
        return result
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Question answering error: {str(e)}")


@router.get("/available_aspects")
def list_available_aspects(
    model_context_processor: ModelContextProcessor = Depends(get_model_context_processor)
):
    """
    List available model aspects that can be queried.
    
    Args:
        model_context_processor: Injected model context processor
        
    Returns:
        Dict containing available aspects and their descriptions
    """
    return {"available_aspects": model_context_processor.get_available_aspects()}


@router.post("/answer_with_platform_docs")
def answer_with_platform_docs(
    question: str = Query(..., description="Question to answer"),
    platform_name: str = Query(..., description="Platform to use for documentation"),
    query: str = Query(None, description="Optional search query to find relevant docs (defaults to the question)"),
    max_tokens: int = Query(default=4000, description="Maximum number of tokens to include in context"),
    llm_controller: LLMController = Depends(get_llm_controller),
    platform_docs_controller: PlatformDocsController = Depends(get_platform_docs_controller)
):
    """
    Answer a question using the LLM with context from platform documentation.
    
    Args:
        question: Question to answer
        platform_name: Platform to use for documentation
        query: Optional search query (defaults to the question)
        max_tokens: Maximum number of tokens to include in context
        llm_controller: Injected LLM controller
        platform_docs_controller: Injected platform docs controller
        
    Returns:
        Dict containing the answer and source documents
        
    Raises:
        HTTPException: If platform not found or LLM service unavailable
    """
    try:
        # Use question as query if not provided
        search_query = query if query else question
        
        # Get context from platform documentation
        context = platform_docs_controller.get_context_for_llm(platform_name, search_query, max_tokens)
        
        if not context:
            raise HTTPException(status_code=404, detail=f"No relevant documentation found for query: {search_query}")
        
        # Create a prompt template that includes platform name
        prompt_template = f"""You are an expert on {platform_name} technology and documentation.
        
Answer the following question based on the provided documentation:

Question: {question}

Relevant Documentation:
{context}

Answer:"""
        
        # Process and answer the question
        result = llm_controller.process_and_answer(
            question=question,
            context_documents=[context],
            prompt_template=prompt_template
        )
        
        return result
    
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Question answering error: {str(e)}")


@router.post("/answer_with_multi_platform_docs")
def answer_with_multi_platform_docs(
    question: str = Query(..., description="Question to answer"),
    platforms: List[str] = Query(..., description="List of platforms to use for documentation"),
    query: str = Query(None, description="Optional search query to find relevant docs (defaults to the question)"),
    max_tokens: int = Query(default=6000, description="Maximum number of tokens to include in context"),
    llm_controller: LLMController = Depends(get_llm_controller),
    platform_docs_controller: PlatformDocsController = Depends(get_platform_docs_controller)
):
    """
    Answer a question using the LLM with context from multiple platform documentations.
    
    Args:
        question: Question to answer
        platforms: List of platforms to use for documentation
        query: Optional search query (defaults to the question)
        max_tokens: Maximum number of tokens to include in context
        llm_controller: Injected LLM controller
        platform_docs_controller: Injected platform docs controller
        
    Returns:
        Dict containing the answer and source documents
        
    Raises:
        HTTPException: If platforms not found or LLM service unavailable
    """
    try:
        # Use question as query if not provided
        search_query = query if query else question
        
        # Get context from multiple platform documentations
        context = platform_docs_controller.get_multi_platform_context(platforms, search_query, max_tokens)
        
        if not context:
            raise HTTPException(status_code=404, detail=f"No relevant documentation found for query: {search_query}")
        
        # Create a prompt template that includes platform names
        platforms_str = ", ".join(platforms)
        prompt_template = f"""You are an expert on {platforms_str} technologies and documentation.
        
Answer the following question based on the provided documentation from multiple platforms:

Question: {question}

Relevant Documentation:
{context}

Answer:"""
        
        # Process and answer the question
        result = llm_controller.process_and_answer(
            question=question,
            context_documents=[context],
            prompt_template=prompt_template
        )
        
        return result
    
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Question answering error: {str(e)}")

# --- New Conversational Search Endpoint ---

@router.post("/search/conversation", response_model=ConversationResponse)
def handle_search_conversation_endpoint(
    request: ConversationRequest,
    search_controller: SearchController = Depends(get_search_controller),
    llm_controller: LLMController = Depends(get_llm_controller)
):
    """
    Handle a turn in the conversational search interaction.

    Receives the user's latest message and the conversation history,
    uses the LLM to process the turn, potentially refines the query,
    suggests filters, asks clarifying questions, and optionally triggers
    a search.
    """
    try:
        # Convert Pydantic models back to simple dicts for the controller if needed
        history_list = [msg.dict() for msg in request.conversation_history]
        # history_list = history_list[:3]
        # print(f"Conversation history: {history_list}")
        
        # --- Fetch available filter VALUES for LLM context --- 
        available_filters_values_dict = {}
        # Fetch values only for key properties to give LLM examples
        # filter_properties_to_fetch_values = ["mlTask", "keywords", "license"]
        
        # for prop in filter_properties_to_fetch_values:
        #     try:
        #         details = entity_controller.get_distinct_property_values_with_entity_details(prop)
        #         available_filters_values_dict[prop] = [d.get("name", v).lower().replace("_", " ") for v, d in details.items()]
        #     except Exception as e:
        #         print(f"Warning: Could not fetch distinct values for filter '{prop}': {e}")
                
        result = llm_controller.process_free_response(
            user_message=request.user_message,
            conversation_history=history_list,
            extended=request.extended,
            limit=request.limit,
            # available_filters_values_dict=available_filters_values_dict
        )
        
        # Transform the result to match ConversationResponse structure
        conversation_response = {
            "llm_response": result.get("response", ""),
            "suggested_filters": result.get("suggested_filters", {}),
            "refined_query": result.get("refined_query", ""),
            "conversation_state": result.get("state", ""),
            "search_results": [],  # For now, we're not triggering search in this endpoint
            "suggested_questions": result.get("suggested_questions", []),
            "raw_llm_output": result.get("raw_llm_output", None)
        }
        
        return ConversationResponse(**conversation_response)
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        # Assuming ConnectionError might be raised by LLMController if it fails
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except Exception as e:
        print(f"Error in /search/conversation: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Conversational search error: {str(e)}")


@router.post("/refine-query", response_model=RefineQueryResponse)
def refine_query_endpoint(
    request: RefineQueryRequest,
    llm_controller: LLMController = Depends(get_llm_controller),
    search_controller: SearchController = Depends(get_search_controller)
):
    """
    Refine the user's current query and filters using the LLM.
    
    Analyzes the current query and filters to suggest improvements,
    ask clarifying questions, and propose valid filter suggestions.
    Does NOT perform a search.
    """
    try:
        # --- Fetch available filter VALUES using SearchController's faceted search infrastructure --- 
        available_filters_values_dict = {}
        
        # Get facets configuration to know which facets are available
        facets_config = search_controller.get_facets_config()
        
        # Fetch values only for key properties to give LLM examples
        # Focus on most important facets and limit total data to avoid token limit
        # Prioritize mlTask first, then license, then keywords
        filter_properties_to_fetch_values = []
        for facet_name in ["mlTask", "license", "keywords"]:  # Order by priority
            if facet_name in facets_config and facets_config[facet_name].get("pinned", False):
                filter_properties_to_fetch_values.append(facet_name)
        
        # Limit to maximum 2 properties to reduce context size
        filter_properties_to_fetch_values = filter_properties_to_fetch_values[:2]
        
        total_values_collected = 0
        max_total_values = 30  # Global limit across all properties
        
        for prop in filter_properties_to_fetch_values:
            if total_values_collected >= max_total_values:
                break
                
            try:
                # Use SearchController's fetch_facet_values method
                # Reduced limit to avoid context length issues
                remaining_quota = max_total_values - total_values_collected
                prop_limit = min(15, remaining_quota)  # Don't exceed remaining quota
                
                facet_data = search_controller.fetch_facet_values(
                    field=prop,
                    limit=prop_limit,  # Dynamic limit based on remaining quota
                    current_filters={}  # No filters for getting all available values
                )
                
                # Extract and format the values
                formatted_values = []
                for value_info in facet_data.get("values", []):
                    value = value_info.get("value", "")
                    if value and len(formatted_values) < prop_limit:
                        # Format similar to old approach: lowercase and replace underscores
                        formatted_value = str(value).lower().replace("_", " ")
                        formatted_values.append(formatted_value)
                
                if formatted_values:
                    available_filters_values_dict[prop] = formatted_values
                    total_values_collected += len(formatted_values)
                    print(f"Fetched {len(formatted_values)} values for {prop} using SearchController")
                
            except Exception as e:
                print(f"ERROR!!! : Could not fetch facet values for '{prop}' using SearchController: {e}")
                # Continue without example values for this property
        # --- End Fetch available filter values --- 
        
        print(f"Total facet values collected for LLM: {total_values_collected} across {len(available_filters_values_dict)} properties")
        print(f"Available filters summary: {[(k, len(v)) for k, v in available_filters_values_dict.items()]}")

        # Call the LLM controller method for refinement
        llm_analysis = llm_controller.refine_query_and_suggest_filters(
            current_query=request.current_query,
            current_filters=request.current_filters,
            available_filters=available_filters_values_dict
        )
        
        # --- Validate suggested filter KEYS against known fields --- 
        validated_suggested_filters = {}
        if llm_analysis.get("suggested_filters"):
            for key, values in llm_analysis["suggested_filters"].items():
                # Check if the suggested property name is in our allowed list
                if key in KNOWN_FILTERABLE_FIELDS:
                    validated_suggested_filters[key] = values
                else:
                    print(f"Warning: LLM suggested filter key '{key}' which is not in KNOWN_FILTERABLE_FIELDS, discarding.")
        # --- End Validation --- 

        return RefineQueryResponse(
            response=llm_analysis.get("response", "Failed to get refinement suggestion."),
            suggested_filters=validated_suggested_filters, # Return validated suggestions
            refined_query=llm_analysis.get("refined_query", ""),
            raw_llm_output=llm_analysis.get("raw_llm_output")
        )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except Exception as e:
        print(f"Error in /refine-query: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Query refinement error: {str(e)}")


@router.post("/improve-query", response_model=ImproveQueryResponse)
def improve_query_endpoint(
    request: ImproveQueryRequest,
    llm_controller: LLMController = Depends(get_llm_controller)
):
    """
    Improve the user's search query text and provide guiding questions.
    
    This endpoint focuses exclusively on query text improvement without suggesting filters.
    It analyzes the current query for clarity and specificity, suggests improvements,
    asks clarifying questions, and provides alternative formulations.
    
    Args:
        request: Request containing the current query and optional search context
        llm_controller: Injected LLM controller
        
    Returns:
        ImproveQueryResponse: Contains improved query, clarifying questions, and guidance
        
    Raises:
        HTTPException: If query improvement fails or LLM service unavailable
    """
    try:
        # Call the LLM controller method for query improvement
        improvement_result = llm_controller.improve_query_only(
            current_query=request.current_query,
            search_context=request.search_context
        )
        
        return ImproveQueryResponse(
            response=improvement_result.get("response", "Failed to improve query."),
            improved_query=improvement_result.get("improved_query", ""),
            clarifying_questions=improvement_result.get("clarifying_questions", []),
            query_suggestions=improvement_result.get("query_suggestions", []),
            search_tips=improvement_result.get("search_tips", "Try using more specific ML terminology."),
            raw_llm_output=improvement_result.get("raw_llm_output")
        )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except Exception as e:
        print(f"Error in /improve-query: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Query improvement error: {str(e)}")

# --- New Model Summarization Endpoint ---

@router.post("/summarize-models", response_model=SummarizeModelsResponse)
def summarize_models_endpoint(
    request: SummarizeModelsRequest,
    llm_controller: LLMController = Depends(get_llm_controller),
    model_context_processor: ModelContextProcessor = Depends(get_model_context_processor),
    search_controller: SearchController = Depends(get_search_controller)
):
    """
    Generates a summary for a list of specified models, highlighting common themes.

    Args:
        request: Request containing the list of model IDs.
        llm_controller: Injected LLM controller.
        model_context_processor: Injected model context processor.
        search_controller: Injected search controller.

    Returns:
        SummarizeModelsResponse: Containing the summary and source context.

    Raises:
        HTTPException: If input is invalid, models not found, or LLM fails.
    """
    try:
        if not request.model_ids:
            raise HTTPException(status_code=400, detail="Model IDs list cannot be empty.")

        # Fetch details for all models
        model_details_list = []
        model_names = []
        not_found_ids = []

        for model_id in request.model_ids:
            model_details = search_controller.search_model_by_id(model_id, extended=True)
            if not model_details:
                not_found_ids.append(model_id)
                continue # Skip if model not found

            # Use the first result if search_model_by_id returns a list
            current_details = model_details[0] if isinstance(model_details, list) else model_details
            model_details_list.append(current_details)
            model_names.append(current_details.get("name", f"Model {model_id}")[0])

        if not_found_ids:
            raise HTTPException(status_code=404, detail=f"Models not found: {', '.join(not_found_ids)}")

        if not model_details_list:
             raise HTTPException(status_code=404, detail="No valid models found for summarization.")

        # Format models context using ModelContextProcessor
        # Using format_models_for_comparison as it structures multiple models well
        combined_context = model_context_processor.format_models_for_comparison(
            model_details_list,
            model_names,
            request.include_raw_json
        )

        # Define the summarization prompt
        summarization_prompt_template = """
        You are an AI assistant specializing in summarizing information about Machine Learning models.
        Based on the provided details for the following models: 
        {model_names_str}

        Please generate a concise summary that covers:
        1.  A brief overview of all the models.
        2.  Any notable commonalities (e.g., shared tasks, base models, licenses).
        3.  Any significant differences or unique features.

        Use the following context:
        {context}

        Summary not in markdown format:
        """
        model_names_str = ", ".join(model_names)
        
        formatted_prompt = summarization_prompt_template.format(
            model_names_str=model_names_str,
            context="{context}",  # Keep context placeholder for process_and_answer
            question="{question}" # Keep question placeholder for process_and_answer
        )
        
        # Define the question for the process_and_answer method
        question_for_llm = f"Summarize the model information, commonalities, and differences for models: {', '.join(model_names)}"

        # Use LLMController to generate the summary
        # We use process_and_answer to leverage its context handling and vectorization
        # even though we are primarily generating text based on the full context.
        result = llm_controller.process_and_answer(
            question=question_for_llm, # The conceptual task for the LLM
            context_documents=[combined_context], # Provide all model details as one document
            prompt_template=formatted_prompt
        )

        # We might want to adapt the response structure if needed
        return SummarizeModelsResponse(
            summary=result.get("answer", "Failed to generate summary."),
            source_documents=result.get("source_documents", []),
            # raw_llm_output=result.get("raw_llm_output") # Assuming process_and_answer returns raw output
        )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(ce)}")
    except HTTPException as he:
        raise he # Re-raise specific HTTP exceptions
    except Exception as e:
        print(f"Error in /summarize-models: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Model summarization error: {str(e)}") 