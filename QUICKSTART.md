# MLentory ETL - Quick Start Guide

Get up and running with MLentory ETL in 5 minutes!

## Prerequisites

- Docker Desktop installed and running
- Docker Compose v2.0+
- At least 8GB RAM available
- Git

## Step 1: Clone the Repository

```bash
git clone <repository-url>
cd mlentory_etl_backend
```

## Step 2: Create Environment File

```bash
make init
```

This creates a `.env` file from `.env.example`. The default values are fine for local development.

**Optional:** Edit `.env` to customize:
- Database passwords
- API tokens (for extractors)
- Service ports

```bash
nano .env  # or use your preferred editor
```

## Step 3: Verify Setup

Run the verification script to ensure everything is configured:

```bash
./scripts/verify_setup.sh
```

You should see green checkmarks ✓ for all items.

## Step 4: Start Services

```bash
make up
```

This will start:
- Neo4j (graph database)
- Elasticsearch (search engine)
- Dagster (orchestration)
- PostgreSQL (Dagster metadata)

**First run takes 5-10 minutes** to download and build Docker images.

## Step 5: Access Services

Once services are running, open your browser:

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| **Dagster UI** | http://localhost:3000 | No login required |
| **Neo4j Browser** | http://localhost:7474 | `neo4j` / `mlentory_neo4j_password_change_me` |
| **Elasticsearch** | http://localhost:9200 | `elastic` / `mlentory_es_password_change_me` |

## Step 6: Verify Services are Running

Check service status:

```bash
make status
```

All services should show "Up" and "healthy".

View logs:

```bash
make logs
```

Press `Ctrl+C` to stop viewing logs.

## What's Next?

### Explore the Project

```bash
# View available commands
make help

# Open a shell in the Dagster container
make shell

# Run tests
make test

# Format code
make format
```

### Development Workflow

1. **Create a feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes**
   - Edit code in `etl/`, `extractors/`, `transformers/`, or `loaders/`
   - Add tests in `tests/`

3. **Run tests and format**
   ```bash
   make format
   make test
   ```

4. **Commit and push**
   ```bash
   git add .
   git commit -m "feat: Add my feature"
   git push origin feature/my-feature
   ```

### Adding Your First Extractor

See the [Architecture Documentation](docs/architecture.md) for detailed guides on:
- Adding a new data source
- Creating transformers
- Setting up Dagster assets

### Common Commands

```bash
# Start services
make up

# Stop services
make down

# Restart services
make restart

# View logs
make logs

# View Dagster logs only
make logs-dagster

# Run tests
make test

# Format code
make format

# Clean all data (WARNING: deletes database)
make clean
```

## Troubleshooting

### Services won't start

```bash
# Check Docker is running
docker ps

# Check for port conflicts
netstat -an | grep -E "3000|7474|7687|9200"

# Stop conflicting services and retry
make down
make up
```

### Can't connect to Neo4j

1. Wait 1-2 minutes after `make up` for Neo4j to initialize
2. Check Neo4j logs: `make logs-neo4j`
3. Verify password in `.env` matches docker-compose

### Dagster UI shows no pipelines

1. This is normal for initial setup
2. Pipelines will appear after implementing Dagster assets
3. Check repository configuration in `etl/repository.py`

### Build errors

```bash
# Rebuild from scratch
make rebuild

# If still failing, clean everything
make down
docker system prune -f
make up
```

## Getting Help

- 📖 Read the [README](README.md) for detailed documentation
- 🏗️ Check [Architecture Docs](docs/architecture.md) for system design
- 🤝 See [CONTRIBUTING](CONTRIBUTING.md) for development guidelines
- 🐛 Open an issue on GitHub for bugs
- 💬 Join community discussions

## Next Steps

Now that your environment is running, you can:

1. **Explore Dagster UI** at http://localhost:3000
   - Familiarize yourself with the interface
   - Check out the Asset Catalog (empty for now)

2. **Explore Neo4j Browser** at http://localhost:7474
   - Run Cypher queries
   - Visualize graph relationships

3. **Start Implementation**
   - Add your first extractor
   - Create FAIR4ML transformers
   - Build Dagster assets

4. **Read Documentation**
   - [FAIR4ML Schema](docs/fair4ml.md)
   - [Architecture Overview](docs/architecture.md)

---

