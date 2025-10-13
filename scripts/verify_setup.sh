#!/bin/bash
# MLentory ETL Setup Verification Script
# This script checks if your environment is ready for development

set -e

echo "====================================="
echo "MLentory ETL Setup Verification"
echo "====================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check functions
check_command() {
    if command -v $1 &> /dev/null; then
        echo -e "${GREEN}✓${NC} $1 is installed"
        return 0
    else
        echo -e "${RED}✗${NC} $1 is not installed"
        return 1
    fi
}

check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1 exists"
        return 0
    else
        echo -e "${RED}✗${NC} $1 not found"
        return 1
    fi
}

check_directory() {
    if [ -d "$1" ]; then
        echo -e "${GREEN}✓${NC} $1 directory exists"
        return 0
    else
        echo -e "${RED}✗${NC} $1 directory not found"
        return 1
    fi
}

echo "1. Checking required commands..."
echo "--------------------------------"
check_command docker
check_command docker-compose
check_command git
check_command python3
echo ""

echo "2. Checking Python version..."
echo "--------------------------------"
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)
if (( $(echo "$PYTHON_VERSION >= 3.11" | bc -l) )); then
    echo -e "${GREEN}✓${NC} Python version $PYTHON_VERSION (>= 3.11 required)"
else
    echo -e "${YELLOW}⚠${NC} Python version $PYTHON_VERSION (3.11+ recommended)"
fi
echo ""

echo "3. Checking project structure..."
echo "--------------------------------"
check_directory "etl"
check_directory "extractors"
check_directory "transformers"
check_directory "loaders"
check_directory "schemas"
check_directory "tests"
check_directory "docs"
check_directory "deploy"
echo ""

echo "4. Checking configuration files..."
echo "--------------------------------"
check_file "docker-compose.yml"
check_file "pyproject.toml"
check_file "Makefile"
check_file ".env.example"

if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} .env file exists"
else
    echo -e "${YELLOW}⚠${NC} .env file not found. Run 'make init' to create it."
fi
echo ""

echo "5. Checking Docker daemon..."
echo "--------------------------------"
if docker ps &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker daemon is running"
else
    echo -e "${RED}✗${NC} Docker daemon is not running. Start Docker first."
fi
echo ""

echo "6. Checking data directories..."
echo "--------------------------------"
check_directory "data/raw"
check_directory "data/normalized"
check_directory "data/rdf"
echo ""

echo "====================================="
echo "Verification Complete!"
echo "====================================="
echo ""

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Run 'make init' to create .env file"
    echo "  2. Edit .env with your configuration"
    echo "  3. Run 'make up' to start services"
    echo "  4. Visit http://localhost:3000 for Dagster UI"
else
    echo -e "${GREEN}Setup looks good!${NC}"
    echo ""
    echo "Quick start:"
    echo "  make up      # Start all services"
    echo "  make logs    # View logs"
    echo "  make test    # Run tests"
fi
echo ""

