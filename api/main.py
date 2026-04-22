"""
MLentory API - Main Application.

FastAPI application that provides REST endpoints for querying ML model metadata
from the MLentory knowledge graph (Elasticsearch + Neo4j).

Application Structure:
    - FastAPI app with automatic OpenAPI documentation
    - CORS middleware for cross-origin requests
    - Lifespan context manager for startup/shutdown logic
    - Router-based endpoint organization
    - Health check endpoint for monitoring

Architecture Overview:
    
    Client Request
         |
         v
    FastAPI Router (routers/models.py)
         |
         +---> Elasticsearch Service (services/elasticsearch_service.py)
         |          |
         |          v
         |     Elasticsearch (indexed model data)
         |
         +---> Graph Service (services/graph_service.py)
                    |
                    v
               Neo4j (graph relationships)

Key Features:
    - RESTful API design with standard HTTP methods
    - Automatic OpenAPI/Swagger documentation
    - Pydantic validation for all requests/responses
    - CORS support for web applications
    - Health checks for monitoring
    - Reuses ETL configurations for consistency


Configuration:
    All configuration is loaded from environment variables via the
    api.config module, which reuses ETL loader configurations:
    
    - Elasticsearch: ELASTIC_HOST, ELASTIC_PORT, etc.
    - Neo4j: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

Running:
    # Development
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    
    # Production (Docker)
    docker-compose up api

Example:
    >>> import httpx
    >>> 
    >>> # List models
    >>> response = httpx.get("http://localhost:8000/api/v1/models")
    >>> print(response.json())
    >>> 
    >>> # Check health
    >>> health = httpx.get("http://localhost:8000/health")
    >>> print(health.json()["status"])
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_es_client, get_neo4j_config
from api.routers.graph import router as graph_router
from api.routers.llm import router as llm_router
from api.routers.models import router as models_router
from api.routers.stella import router as stella_router
from api.routers.stats import router as stats_router
from api.schemas.responses import HealthResponse

#Import controllers
from api.dbHandler.SQLHandler import SQLHandler
from api.dbHandler.IndexHandler import IndexHandler
from api.controllers.EntityController import EntityController
from api.controllers.SearchController import SearchController
from api.controllers.LLMController import LLMController
from api.controllers.ModelContextProcessor import ModelContextProcessor
from api.controllers.PlatformDocsController import PlatformDocsController

# Import LLMRunner implementations
from api.utils.llm_runners import LLMRunner, OllamaRunner, VLLMRunner, OpenAIRunner

# Global controller instances
sqlHandler = None
indexHandler = None
searchController = None
entityController = None
llmController = None
modelContextProcessor = None
platformDocsController = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    logger.info("Starting MLentory API")
    if os.environ.get("USE_STELLA", "true").lower() == "true":
        logger.info("STELLA integration enabled (USE_STELLA=true)")
    else:
        logger.info("STELLA integration disabled (USE_STELLA!=true)")

    global searchController, entityController, llmController, modelContextProcessor, platformDocsController, sqlHandler, indexHandler

    # Get database configuration from environment variables
    # postgres_host = os.environ.get("POSTGRES_HOST", "postgres_db")
    # postgres_user = os.environ.get("POSTGRES_USER", "user")
    # postgres_password = os.environ.get("POSTGRES_PASSWORD", "password")
    # postgres_db = os.environ.get("POSTGRES_DB", "history_DB")

    # elasticsearch_host = os.environ.get("ELASTIC_HOST", "elastic_db")
    # elasticsearch_port = int(os.environ.get("ELASTIC_PORT", "9200"))
    
    # sqlHandler = SQLHandler(
    #     host=postgres_host,
    #     user=postgres_user,
    #     password=postgres_password,
    #     database=postgres_db,
    # )
    # sqlHandler.connect()

    # indexHandler = IndexHandler(
    #     es_host=elasticsearch_host,
    #     es_port=elasticsearch_port,
    # )
    # entityController = EntityController(sqlHandler)
    # searchController = SearchController(indexHandler, entityController, llmController)

    # Initialize LLM Runner based on environment configuration
    llm_provider = os.environ.get("LLM_PROVIDER", "vllm").lower()
    # llm_model = os.environ.get("LLM_MODEL", "Qwen/Qwen3-4B-Thinking-2507-FP8")
    llm_model = os.environ.get("LLM_MODEL", "google/gemma-3-4b-it")
    # llm_model = os.environ.get("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    # llm_model = os.environ.get("LLM_MODEL", "google/gemma-3-1b-it")
    llm_temperature = float(os.environ.get("LLM_TEMPERATURE", "0.1"))
    
    llm_runner = None
    if llm_provider == "ollama":
        ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
        llm_runner = OllamaRunner(
            base_url=ollama_base_url,
            model_name=llm_model,
            temperature=llm_temperature,
            max_retries=3,
            retry_delay=5
        )
    elif llm_provider == "vllm":
        vllm_base_url = os.environ.get("VLLM_BASE_URL", "http://vllm:8000")
        # vllm_base_url = os.environ.get("VLLM_BASE_URL", "http://193.196.29.16:8003")
        llm_runner = VLLMRunner(
            base_url=vllm_base_url,
            model_name=llm_model,
            temperature=llm_temperature,
            max_retries=20,  # Increased for model loading time
            retry_delay=20   # Longer delay between retries
        )
    elif llm_provider == "openai":
        # Placeholder for future OpenAI implementation
        # Will need to implement OpenAIRunner first
        # api_key = os.environ.get("OPENAI_API_KEY")
        # if not api_key:
        #     raise ValueError("OPENAI_API_KEY environment variable is required when LLM_PROVIDER is 'openai'")
        # llm_runner = OpenAIRunner(
        #     api_key=api_key,
        #     model_name=llm_model,
        #     temperature=llm_temperature
        # )
        print("OpenAI provider selected but not yet implemented. Falling back to Ollama.")
        ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
        llm_runner = OllamaRunner(
            base_url=ollama_base_url,
            model_name=llm_model,
            temperature=llm_temperature
        )
    else:
        print(f"Unknown LLM provider '{llm_provider}'. Falling back to Ollama.")
        ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
        llm_runner = OllamaRunner(
            base_url=ollama_base_url,
            model_name=llm_model,
            temperature=llm_temperature
        )
    
    # Initialize LLMController with the configured runner
    llmController = LLMController(
        llm_runner=llm_runner
    )
    
    # Initialize ModelContextProcessor
    modelContextProcessor = ModelContextProcessor()

     # Initialize PlatformDocsController
    # platformDocsController = PlatformDocsController(docs_base_path="../data/platform_docs")

    yield
    logger.info("Shutting down MLentory API")


# Create FastAPI application
app = FastAPI(
    title="MLentory API",
    description="API for querying ML model metadata from FAIR4ML knowledge graph",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed for production
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Include routers
app.include_router(
    models_router,
    prefix="/api/v1",
    tags=["models"],
)

app.include_router(
    stella_router,
    prefix="/api/v1",
    tags=["stella"],
)

app.include_router(
    graph_router,
    prefix="/api/v1",
    tags=["graph"],
)

app.include_router(
    llm_router,
    prefix="/api/v1",
    tags=["llm"],
)

app.include_router(
    stats_router,
    prefix="/api/v1",
    tags=["statistics"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns the status of database connections and overall service health.
    """
    try:
        # Check Elasticsearch connection
        es_healthy = False
        try:
            es_client = get_es_client()
            es_client.info()  # Simple ping
            es_healthy = True
        except Exception as e:
            logger.warning(f"Elasticsearch health check failed: {e}")

        # Check Neo4j connection
        neo4j_healthy = False
        try:
            neo4j_config = get_neo4j_config()
            # Simple Cypher query to test connection
            from etl_loaders.rdf_store import _run_cypher
            result = _run_cypher("RETURN 1 as test", cfg=neo4j_config)
            neo4j_healthy = len(result) > 0
        except Exception as e:
            logger.warning(f"Neo4j health check failed: {e}")

        status = "healthy" if (es_healthy and neo4j_healthy) else "degraded"

        return HealthResponse(
            status=status,
            version="1.0.0",
            elasticsearch=es_healthy,
            neo4j=neo4j_healthy,
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Health check failed")


@app.get("/")
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "name": "MLentory API",
        "version": "1.0.0",
        "description": "API for querying ML model metadata from FAIR4ML knowledge graph",
        "docs": "/docs",
        "health": "/health",
    }
