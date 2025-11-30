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
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_es_client, get_neo4j_config
from api.routers.graph import router as graph_router
from api.routers.models import router as models_router
from api.routers.stats import router as stats_router
from api.schemas.responses import HealthResponse

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
    graph_router,
    prefix="/api/v1",
    tags=["graph"],
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
