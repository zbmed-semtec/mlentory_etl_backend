# Documentation Structure

This directory contains the MkDocs documentation for MLentory ETL.

## Structure

The documentation is organized into the following sections:

- **Getting Started**: Installation, quickstart, and configuration
- **Architecture**: System design, data flow, components, and deployment
- **Concepts**: ETL overview, FAIR4ML schema, Dagster basics, graph databases
- **Extractors**: Overview and guides for each extractor (HuggingFace, OpenML, AI4Life)
- **Transformers**: Transformation overview, architecture, and guides
- **Loaders**: Loading guides for Neo4j, Elasticsearch, and RDF
- **Schemas**: FAIR4ML schema reference and structure
- **Development**: Setup, code style, testing, debugging, contributing
- **Operations**: Running pipelines, monitoring, troubleshooting, maintenance
- **API Reference**: Complete API documentation
- **Examples**: Practical examples and tutorials
- **Guides**: Step-by-step guides for common tasks

## Building the Documentation

To build and serve the documentation locally, you can use any of the following methods:

### Option 0: Using Makefile (Easiest)

If you have the project dependencies installed:

```bash
# Serve the documentation (with auto-reload)
make docs

# Build static site
make docs-build
```

The documentation will be available at `http://127.0.0.1:8000` when running `make docs`.

### Option 1: Using pip

```bash
# Create a virtual environment (if not already created)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies including MkDocs
pip install -e ".[dev]"  # Installs project with dev dependencies

# Serve the documentation (with auto-reload)
mkdocs serve

# Build static site
mkdocs build
```

### Option 2: Using uv (Recommended)

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --dev

# Activate the environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Serve the documentation (with auto-reload)
mkdocs serve

# Build static site
mkdocs build
```

### Option 3: Using Poetry

```bash
# Install dependencies
poetry install

# Activate the environment
poetry shell

# Serve the documentation (with auto-reload)
mkdocs serve

# Build static site
mkdocs build
```

### Option 4: Install MkDocs Only

If you only want to work on documentation without installing all project dependencies:

```bash
# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install only MkDocs and its dependencies
pip install mkdocs mkdocs-material mkdocstrings[python] pymdown-extensions

# Serve the documentation
mkdocs serve
```

The documentation will be available at `http://127.0.0.1:8000` when running `mkdocs serve`.

## Adding Content

All documentation files are currently placeholders. You can start filling them with content one by one. Each file has a basic structure with section headers to guide you.

## Configuration

The MkDocs configuration is in `mkdocs.yml` at the project root. It uses the Material theme with various extensions for enhanced markdown support.

