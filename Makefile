.PHONY: help up down restart logs clean test format typecheck extract transform load etl-run etl-check etl-both build hf-etl ai4life-etl hf-extract hf-transform hf-load hf-index hf-vector ai4life-extract ai4life-transform ai4life-load ai4life-index ai4life-vector run-by-tag init ensure-env stella-init stella-up stella-down wait-stella wait-vllm check-vllm-env

# Default target
.DEFAULT_GOAL := help

# Color output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

##@ Help

help: ## Display this help message
	@echo "$(BLUE)MLentory ETL Backend - Makefile Commands$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make $(GREEN)<target>$(NC)\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Docker Operations

ensure-env: ## Ensure .env exists (copy from .env.example if missing)
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(GREEN).env created from .env.example$(NC)"; \
	else \
		echo "$(GREEN).env already exists$(NC)"; \
	fi

check-vllm-env: ## Verify HuggingFace token is set when using gated models
	@VLLM_MODEL=$$(grep -E '^VLLM_MODEL=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d ' "' || echo google/gemma-3-4b-it); \
	HF_TOKEN_LEN=$$(awk -F= '/^HUGGINGFACE_API_TOKEN=/{print length($$2)}' .env 2>/dev/null || echo 0); \
	if [ "$$HF_TOKEN_LEN" -eq 0 ]; then \
		echo "$(YELLOW)WARNING: HUGGINGFACE_API_TOKEN is empty in .env$(NC)"; \
		echo "  The default model ($$VLLM_MODEL) is gated on HuggingFace."; \
		echo "  Set HUGGINGFACE_API_TOKEN in .env (with model access), or set VLLM_MODEL to an open model."; \
		exit 1; \
	fi

wait-vllm: ## Wait for vLLM to serve /v1/models (model load can take several minutes)
	@echo "$(BLUE)Waiting for vLLM to be ready (google/gemma-3-4b-it — load may take several minutes)...$(NC)"
	@for i in $$(seq 1 90); do \
		if curl -sf http://localhost:8003/v1/models >/dev/null 2>&1; then \
			echo "$(GREEN)vLLM is ready$(NC)"; \
			exit 0; \
		fi; \
		LOGS=$$(sudo docker logs vllm 2>&1 | tail -30); \
		echo "$$LOGS" | grep -q "gated repo" && { \
			echo "$(YELLOW)vLLM failed: gated HuggingFace model — set HUGGINGFACE_API_TOKEN in .env$(NC)"; exit 1; }; \
		echo "$$LOGS" | grep -q "no kernel image is available" && { \
			echo "$(YELLOW)vLLM failed: GPU/kernel incompatible — use pinned vllm v0.8.5 image (see docker-compose.yml)$(NC)"; \
			echo "$$LOGS" | tail -5; exit 1; }; \
		echo "$$LOGS" | grep -q "Engine core initialization failed" && [ $$i -gt 15 ] && { \
			echo "$(YELLOW)vLLM engine failed to start — last logs:$(NC)"; \
			echo "$$LOGS" | tail -8; exit 1; }; \
		echo "  attempt $$i/90 (waiting 20s)..."; \
		sleep 20; \
	done; \
	echo "$(YELLOW)vLLM did not become ready in time — check: docker logs vllm$(NC)"; \
	sudo docker logs vllm 2>&1 | tail -15; \
	exit 1

wait-stella: ## Wait for STELLA containers to be running
	@echo "$(BLUE)Waiting for STELLA containers to be ready...$(NC)"
	@for i in $$(seq 1 60); do \
		if sudo docker inspect -f '{{.State.Running}}' stella-app 2>/dev/null | grep -q true && \
		   sudo docker inspect -f '{{.State.Running}}' stella-server 2>/dev/null | grep -q true; then \
			echo "$(GREEN)STELLA containers are running$(NC)"; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "$(YELLOW)STELLA containers did not become ready in time$(NC)"; \
	exit 1

up: ensure-env ## Start all services (vLLM first, STELLA when USE_STELLA=true in .env)
	@echo "$(BLUE)Starting MLentory ETL services...$(NC)"
	@set -e; \
	USE_STELLA=$$(grep -E '^USE_STELLA=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d ' "' | tr '[:upper:]' '[:lower:]' || echo true); \
	[ -n "$$USE_STELLA" ] || USE_STELLA=true; \
	echo "USE_STELLA=$$USE_STELLA"; \
	sudo chown -R 1000:1000 ./config; \
	sudo chmod -R 775 ./config; \
		$(MAKE) check-vllm-env; \
		echo "$(BLUE)Step 1/3: Starting vLLM (LLM inference — may take several minutes on first run)...$(NC)"; \
		sudo docker compose up -d vllm; \
		$(MAKE) wait-vllm; \
	if [ "$$USE_STELLA" = "true" ]; then \
		echo "$(BLUE)Step 2/3: Starting complete + STELLA profiles...$(NC)"; \
		sudo docker compose --profile=complete --profile=stella up -d; \
	else \
		echo "$(BLUE)Step 2/3: Starting complete profile (STELLA disabled)...$(NC)"; \
		sudo docker compose --profile=complete up -d; \
	fi; \
	if [ "$$USE_STELLA" = "true" ]; then \
		echo "$(BLUE)Step 3/3: Initializing STELLA...$(NC)"; \
		$(MAKE) wait-stella; \
		$(MAKE) stella-init; \
	fi
	@echo "$(GREEN)Services started!$(NC)"
	@echo "Dagster UI: http://localhost:3000"
	@echo "Neo4j Browser: http://localhost:7474"
	@echo "Elasticsearch: http://localhost:9200"
	@echo "vLLM: http://localhost:8003"
	@echo "API: http://localhost:8008"
	@if grep -E '^USE_STELLA=' .env 2>/dev/null | tail -1 | grep -qi 'true'; then \
		echo "STELLA App: http://localhost:8080"; \
		echo "STELLA Server: http://localhost:8004"; \
	fi

down: ## Stop all services (including STELLA when running)
	@echo "$(BLUE)Stopping MLentory ETL services...$(NC)"
	sudo docker compose --profile=complete --profile=stella --profile=mcp down
	@echo "$(GREEN)Services stopped!$(NC)"

mcp-up: ## Start MCP API service only
	@echo "$(BLUE)Starting MCP API service...$(NC)"
	sudo docker compose --profile=mcp up -d
	@echo "$(GREEN)MCP API service started!$(NC)"
	@echo "MCP API: http://localhost:8009"
	@echo "Neo4j Browser: http://localhost:7474"
	@echo "Elasticsearch: http://localhost:9200"

mcp-down: ## Stop MCP services
	@echo "$(BLUE)Stopping MCP API services...$(NC)"
	sudo docker compose --profile=mcp down 
	@echo "$(GREEN)Services stopped!$(NC)"

stella-up: ensure-env ## Start STELLA services and initialize when USE_STELLA=true
	@USE_STELLA=$$(grep -E '^USE_STELLA=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d ' "' | tr '[:upper:]' '[:lower:]' || echo true); \
	if [ "$$USE_STELLA" != "true" ]; then \
		echo "$(YELLOW)USE_STELLA is not true in .env — skipping STELLA startup$(NC)"; \
		exit 0; \
	fi; \
	echo "$(BLUE)Starting STELLA services...$(NC)"; \
	sudo docker compose --profile=stella up -d; \
	$(MAKE) wait-stella; \
	$(MAKE) stella-init; \
	echo "$(GREEN)STELLA services started!$(NC)"; \
	echo "STELLA App: http://localhost:8080"; \
	echo "STELLA Server: http://localhost:8004"

stella-init: ## Initialize STELLA databases (idempotent)
	@echo "$(BLUE)Initializing STELLA services...$(NC)"
	@sudo docker exec stella-app flask init-db || true
	@sudo docker exec stella-app flask seed-db || true
	@sudo docker exec stella-server flask init-db || true
	@sudo docker exec stella-server flask seed-db || true
	@echo "$(GREEN)STELLA services initialized!$(NC)"

stella-down: ## Stop STELLA services
	@echo "$(BLUE)Stopping STELLA services...$(NC)"
	sudo docker compose --profile=stella down
	@echo "$(GREEN)STELLA services stopped!$(NC)"

restart: down up ## Restart all services

logs: ## View logs from all services
	docker compose logs -f

logs-dagster: ## View Dagster logs
	docker compose logs -f dagster-webserver dagster-daemon

logs-neo4j: ## View Neo4j logs
	docker compose logs -f neo4j

logs-elasticsearch: ## View Elasticsearch logs
	docker compose logs -f elasticsearch

build: ## Build Docker images
	@echo "$(BLUE)Building Docker images...$(NC)"
	docker compose --profile=complete build
	@echo "$(GREEN)Build complete!$(NC)"

rebuild: ## Rebuild Docker images without cache
	@echo "$(BLUE)Rebuilding Docker images...$(NC)"
	docker compose --profile=complete build --no-cache
	@echo "$(GREEN)Rebuild complete!$(NC)"

##@ Data & Cleanup

clean: ## Stop services and remove volumes (WARNING: deletes all data)
	@echo "$(YELLOW)WARNING: This will delete all data!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker compose down -v; \
		rm -rf data/raw/* data/normalized/* data/rdf/* data/cache/*; \
		echo "$(GREEN)Cleanup complete!$(NC)"; \
	else \
		echo "Cancelled."; \
	fi

clean-data: ## Remove local data files only (keeps database volumes)
	@echo "$(BLUE)Cleaning local data files...$(NC)"
	rm -rf data/raw/* data/normalized/* data/rdf/* data/cache/*
	@echo "$(GREEN)Data files cleaned!$(NC)"

##@ Development

shell-dagster: ## Open a shell in the Dagster container
	docker compose exec dagster-webserver /bin/bash

shell-neo4j: ## Open Neo4j Cypher shell
	docker compose exec neo4j cypher-shell -u $(NEO4J_USER) -p $(NEO4J_PASSWORD)

##@ Testing & Quality

test: ## Run all tests
	@echo "$(BLUE)Running tests...$(NC)"
	pytest tests/ -v
	@echo "$(GREEN)Tests complete!$(NC)"

test-unit: ## Run unit tests only
	@echo "$(BLUE)Running unit tests...$(NC)"
	pytest tests/unit/ -v

test-integration: ## Run integration tests (requires running services)
	@echo "$(BLUE)Running integration tests...$(NC)"
	pytest tests/integration/ -v

test-coverage: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	pytest tests/ --cov=. --cov-report=html --cov-report=term
	@echo "$(GREEN)Coverage report generated in htmlcov/index.html$(NC)"

format: ## Format code with black
	@echo "$(BLUE)Formatting code...$(NC)"
	black .
	@echo "$(GREEN)Formatting complete!$(NC)"

format-check: ## Check code formatting without changes
	@echo "$(BLUE)Checking code format...$(NC)"
	black --check .

typecheck: ## Run mypy type checking
	@echo "$(BLUE)Running type checks...$(NC)"
	mypy .
	@echo "$(GREEN)Type checking complete!$(NC)"

lint: format typecheck ## Run all linting and formatting

##@ ETL Operations

DAGSTER_ETL := docker exec mlentory-dagster-webserver dagster asset materialize -f ./etl/repository.py

etl-check: ## Verify Dagster container is running
	@docker inspect -f '{{.State.Running}}' mlentory-dagster-webserver 2>/dev/null | grep -q true \
		|| { echo "$(YELLOW)Dagster not running — run 'make up' first$(NC)"; exit 1; }

etl-run: etl-check ## Run full ETL pipeline for all sources (HF + AI4Life + OpenML)
	@echo "$(BLUE)Running full ETL pipeline (all sources)...$(NC)"
	$(DAGSTER_ETL)

etl-both: etl-check ## Run full HF + AI4Life pipelines (excludes OpenML)
	@echo "$(BLUE)Running HuggingFace + AI4Life ETL pipelines...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="hf_etl" or tag:"pipeline"="ai4life_etl"'

hf-etl: etl-check ## Run full HuggingFace ETL pipeline
	@echo "$(BLUE)Running HuggingFace ETL pipeline...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="hf_etl"'

ai4life-etl: etl-check ## Run full AI4Life ETL pipeline
	@echo "$(BLUE)Running AI4Life ETL pipeline...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="ai4life_etl"'

extract: etl-check ## Run extraction stage for all sources
	@echo "$(BLUE)Running extraction stage (all sources)...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"stage"="extract"'

transform: etl-check ## Run transformation stage for all sources
	@echo "$(BLUE)Running transformation stage (all sources)...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"stage"="transform"'

load: etl-check ## Run loading stage for all sources
	@echo "$(BLUE)Running loading stage (all sources)...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"stage"="load"'

hf-extract: etl-check ## HF extraction stage only
	@echo "$(BLUE)Running HF extraction...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="hf_etl",tag:"stage"="extract"'

hf-transform: etl-check ## HF transformation stage only
	@echo "$(BLUE)Running HF transformation...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="hf_etl",tag:"stage"="transform"'

hf-load: etl-check ## HF loading stage only (Neo4j, RDF)
	@echo "$(BLUE)Running HF loading...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="hf_etl",tag:"stage"="load"'

hf-index: etl-check ## HF Elasticsearch indexing only
	@echo "$(BLUE)Running HF Elasticsearch indexing...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="hf_etl",tag:"stage"="index"'

hf-vector: etl-check ## HF vector backfill only
	@echo "$(BLUE)Running HF vector backfill...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="hf_etl",tag:"stage"="vector_index"'

ai4life-extract: etl-check ## AI4Life extraction stage only
	@echo "$(BLUE)Running AI4Life extraction...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="ai4life_etl",tag:"stage"="extract"'

ai4life-transform: etl-check ## AI4Life transformation stage only
	@echo "$(BLUE)Running AI4Life transformation...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="ai4life_etl",tag:"stage"="transform"'

ai4life-load: etl-check ## AI4Life loading stage only (Neo4j, RDF)
	@echo "$(BLUE)Running AI4Life loading...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="ai4life_etl",tag:"stage"="load"'

ai4life-index: etl-check ## AI4Life Elasticsearch indexing only
	@echo "$(BLUE)Running AI4Life Elasticsearch indexing...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="ai4life_etl",tag:"stage"="index"'

ai4life-vector: etl-check ## AI4Life vector backfill only
	@echo "$(BLUE)Running AI4Life vector backfill...$(NC)"
	$(DAGSTER_ETL) --select 'tag:"pipeline"="ai4life_etl",tag:"stage"="vector_index"'

run-by-tag: etl-check ## Run pipeline by tag (usage: make run-by-tag TAG="pipeline"="hf_etl")
	@if [ -z "$(TAG)" ]; then \
		echo "$(YELLOW)Please specify TAG, e.g., make run-by-tag TAG=\"pipeline\"=\"hf_etl\"$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Running assets with tag $(TAG)...$(NC)"
	$(DAGSTER_ETL) --select 'tag:$(TAG)'

##@ Setup

init: ## Initialize the project (copy .env.example to .env)
	@if [ -f .env ]; then \
		echo "$(YELLOW).env file already exists. Skipping...$(NC)"; \
	else \
		cp .env.example .env; \
		echo "$(GREEN).env file created! Please edit it with your configuration.$(NC)"; \
	fi

setup: up ## Complete initial setup (.env + all services per USE_STELLA)
	@echo "$(GREEN)Setup complete!$(NC)"
	@echo "Next steps:"
	@echo "  1. Edit .env file with your configuration if needed"
	@echo "  2. Visit http://localhost:3000 for Dagster UI"
	@echo "  3. Visit http://localhost:7474 for Neo4j Browser"
	@echo "  4. Run 'make hf-etl', 'make ai4life-etl', or 'make etl-both' to run pipelines"

##@ Information

status: ## Show status of all services
	@echo "$(BLUE)Service Status:$(NC)"
	@docker compose --profile=complete --profile=stella --profile=mcp ps
	@echo ""
	@echo "$(BLUE)Network Info:$(NC)"
	@docker network inspect mlentory-network --format '{{range .Containers}}{{.Name}}: {{.IPv4Address}}{{println}}{{end}}' 2>/dev/null || echo "Network not found"

env-check: ## Verify environment configuration
	@echo "$(BLUE)Checking environment configuration...$(NC)"
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)WARNING: .env file not found!$(NC)"; \
		echo "Run 'make init' to create it."; \
	else \
		echo "$(GREEN)✓ .env file exists$(NC)"; \
	fi
	@docker --version > /dev/null 2>&1 && echo "$(GREEN)✓ Docker installed$(NC)" || echo "$(YELLOW)✗ Docker not found$(NC)"
	@docker compose --version > /dev/null 2>&1 && echo "$(GREEN)✓ Docker Compose installed$(NC)" || echo "$(YELLOW)✗ Docker Compose not found$(NC)"

version: ## Show version information
	@echo "MLentory ETL Backend"
	@echo "Version: 0.1.0"
	@echo "Python: 3.11+"
	@echo "Dagster: Latest"

