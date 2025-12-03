FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and install dependencies
COPY ./pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root --only main

# Install fastmcp
RUN pip install --no-cache-dir fastmcp

# Copy application code
# Copy shared modules that MCP API depends on
COPY ./etl_loaders/ ./etl_loaders/
COPY ./schemas/ ./schemas/
COPY ./api/ ./api/

# Copy MCP API code
COPY ./mcp_api/ ./mcp_api/

# Health check (optional - MCP typically uses stdio, not HTTP)
# This checks if Python can import the module successfully
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import mcp_api; import api.services.elasticsearch_service" || exit 1

# Default command - run the MCP server
# CMD ["python", "-m", "mcp_api.server"]

