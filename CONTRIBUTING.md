# Contributing to MLentory ETL

Thank you for your interest in contributing to MLentory ETL! This document provides guidelines and instructions for contributing to the project.

## Getting Started

1. **Fork the repository**
2. **Clone your fork**
   ```bash
   git clone https://github.com/your-username/mlentory_etl_backend.git
   cd mlentory_etl_backend
   ```

3. **Set up your environment**
   ```bash
   make init  # Copy .env.example to .env
   # Edit .env with your configuration
   make up    # Start Docker services
   ```

4. **Create a branch for your changes**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### 1. Code Style

We follow strict code formatting and style guidelines:

- **Formatter**: Black (line length: 100)
- **Type Checker**: mypy
- **Linter**: Ruff

Run formatting and checks:
```bash
make format      # Format code with Black
make typecheck   # Run mypy type checking
make lint        # Run all checks
```

### 2. Testing

All new features and bug fixes should include tests:

```bash
make test              # Run all tests
make test-unit         # Run unit tests only
make test-integration  # Run integration tests
make test-coverage     # Run tests with coverage report
```

**Test Requirements:**
- Unit tests for all new functions/classes
- Integration tests for ETL pipelines
- Minimum 80% code coverage
- All tests must pass before merging

### 3. Adding a New Data Source

To add support for a new ML model source:

1. **Create extractor module**
   ```
   extractors/
     └── <source_name>/
         ├── __init__.py
         ├── extractor.py      # Main extraction logic
         └── config.py         # Source-specific configuration
   ```

2. **Create transformer module**
   ```
   transformers/
     └── <source_name>/
         ├── __init__.py
         └── transformer.py    # Normalization to FAIR4ML
   ```

3. **Define source schema**
   ```
   schemas/
     └── sources/
         └── <source_name>.py  # Source-specific Pydantic models
   ```

4. **Create Dagster assets**
   ```
   etl/
     └── assets/
         └── <source_name>.py  # Dagster asset definitions
   ```

5. **Add tests**
   ```
   tests/
     ├── unit/
     │   └── test_<source_name>_*.py
     └── integration/
         └── test_<source_name>_pipeline.py
   ```

6. **Update documentation**
   - Add source to README.md
   - Document API requirements in docs/

### 4. Commit Guidelines

We follow conventional commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

**Examples:**
```bash
git commit -m "feat(extractors): Add HuggingFace extractor for model metadata"
git commit -m "fix(loaders): Handle Neo4j connection timeout gracefully"
git commit -m "docs: Update architecture documentation with data flow diagrams"
```

### 5. Pull Request Process

1. **Update your branch**
   ```bash
   git fetch origin
   git rebase origin/main
   ```

2. **Run all checks**
   ```bash
   make lint
   make test
   ```

3. **Push your changes**
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create Pull Request**
   - Fill out the PR template
   - Link related issues
   - Add screenshots/examples if applicable
   - Request review from maintainers

5. **Address review comments**
   - Make requested changes
   - Push updates to the same branch
   - Re-request review

### 6. Code Review Guidelines

**For Contributors:**
- Be responsive to feedback
- Keep PRs focused and small
- Write descriptive PR descriptions
- Update tests and docs

**For Reviewers:**
- Be constructive and respectful
- Check for code quality and style
- Verify test coverage
- Test functionality locally if needed

## Project Structure

```
mlentory_etl_backend/
├── etl/              # Dagster orchestration
├── extractors/       # Data extraction
├── transformers/     # FAIR4ML normalization
├── loaders/          # Data persistence
├── schemas/          # Pydantic models
├── tests/            # Test suite
├── docs/             # Documentation
└── deploy/           # Deployment configs
```

## Architecture Principles

1. **Modularity**: Each source should be self-contained
2. **Idempotency**: ETL operations should be repeatable
3. **Validation**: All data must validate against schemas
4. **Traceability**: Log all operations for debugging
5. **Scalability**: Design for horizontal scaling

## Documentation

- Keep README.md up to date
- Document all public APIs with docstrings (Google style)
- Add inline comments for complex logic
- Update architecture docs for major changes

## Environment Variables

- Never commit secrets or API keys
- Add new variables to `.env.example`
- Document variables in README.md
- Use meaningful variable names (UPPER_SNAKE_CASE)

## Docker Best Practices

- Keep Dockerfiles minimal
- Use multi-stage builds when possible
- Pin dependency versions
- Clean up unnecessary files

## Troubleshooting

### Common Issues

1. **Docker services won't start**
   ```bash
   make down
   make clean-data
   make up
   ```

2. **Dagster can't find modules**
   ```bash
   # Rebuild Dagster container
   make rebuild
   ```

3. **Neo4j connection errors**
   - Check credentials in `.env`
   - Verify Neo4j is healthy: `docker-compose ps`

4. **Tests failing**
   ```bash
   # Ensure services are running for integration tests
   make up
   make test
   ```

## Getting Help

- Open an issue for bugs or feature requests
- Join our community discussions
- Read the documentation in `/docs`
- Check existing issues and PRs

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Thank You!

Your contributions make MLentory ETL better for everyone. We appreciate your time and effort!

