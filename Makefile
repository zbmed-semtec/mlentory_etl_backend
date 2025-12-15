.PHONY: help up down restart logs clean test format typecheck extract transform load etl-run build hf-etl run-by-tag

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

up: ## Start all services
	@echo "$(BLUE)Starting MLentory ETL services...$(NC)"
	sudo chown -R 1000:1000 ./config
	sudo chmod -R 775 ./config
	sudo docker compose --profile=complete up -d
	@echo "$(GREEN)Services started!$(NC)"
	@echo "Dagster UI: http://localhost:3000"
	@echo "Neo4j Browser: http://localhost:7474"
	@echo "Elasticsearch: http://localhost:9200"

down: ## Stop all services
	@echo "$(BLUE)Stopping MLentory ETL services...$(NC)"
	sudo docker compose --profile=complete down 
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
	sudo docker compose --profile=complete build
	@echo "$(GREEN)Build complete!$(NC)"

rebuild: ## Rebuild Docker images without cache
	@echo "$(BLUE)Rebuilding Docker images...$(NC)"
	docker compose build --no-cache
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

extract: ## Run extraction for all sources
	@echo "$(BLUE)Running extraction for $(SOURCE)...$(NC)"
	docker exec mlentory-dagster-webserver dagster asset materialize --select 'tag:"stage"="extract"' -f ./etl/repository.py

transform: ## Run transformation for all sources
	@echo "$(BLUE)Running transformation for $(SOURCE)...$(NC)"
	docker exec mlentory-dagster-webserver dagster asset materialize --select 'tag:"stage"="transform"' -f ./etl/repository.py

load: ## Run loading for all sources
	@echo "$(BLUE)Running loading for $(SOURCE)...$(NC)"
	docker exec mlentory-dagster-webserver dagster asset materialize --select 'tag:"stage"="load"' -f ./etl/repository.py

etl-run: ## Run full ETL pipeline for all sources
	@echo "$(BLUE)Running full ETL pipeline...$(NC)"
	docker exec mlentory-dagster-webserver dagster asset materialize -f ./etl/repository.py

hf-etl: ## Run HuggingFace ETL pipeline (all assets tagged with "pipeline"="hf_etl")
	@echo "$(BLUE)Running HuggingFace ETL pipeline...$(NC)"
	docker exec mlentory-dagster-webserver dagster asset materialize --select 'tag:"pipeline"="hf_etl"' -f ./etl/repository.py

run-by-tag: ## Run pipeline by tag (usage: make run-by-tag TAG="pipeline"="hf_etl")
	@if [ -z "$(TAG)" ]; then \
		echo "$(YELLOW)Please specify TAG, e.g., make run-by-tag TAG=\"pipeline:hf_etl\"$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Running assets with tag $(TAG)...$(NC)"
	docker exec mlentory-dagster-webserver dagster asset materialize --select 'tag:$(TAG)' -f ./etl/repository.py

##@ Setup

init: ## Initialize the project (copy .env.example to .env)
	@if [ -f .env ]; then \
		echo "$(YELLOW).env file already exists. Skipping...$(NC)"; \
	else \
		cp .env.example .env; \
		echo "$(GREEN).env file created! Please edit it with your configuration.$(NC)"; \
	fi

setup: init up ## Complete initial setup (init + start services)
	@echo "$(GREEN)Setup complete!$(NC)"
	@echo "Next steps:"
	@echo "  1. Edit .env file with your configuration"
	@echo "  2. Visit http://localhost:3000 for Dagster UI"
	@echo "  3. Visit http://localhost:7474 for Neo4j Browser"

##@ Information

status: ## Show status of all services
	@echo "$(BLUE)Service Status:$(NC)"
	@docker compose ps
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

