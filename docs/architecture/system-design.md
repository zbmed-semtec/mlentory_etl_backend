# System Design

Detailed design decisions, architectural principles, and technology choices for the MLentory ETL pipeline.

---

## Design Principles

The MLentory ETL pipeline is built on several core principles that guide all design decisions:

### 1. Modularity and Extensibility

**Principle:** Each data source has its own independent extractor, transformer, and loader modules. Adding a new platform doesn't require modifying existing code.

**Implementation:**

- Separate modules per source: `etl_extractors/hf/`, `etl_extractors/openml/`, etc.
- Shared base classes and interfaces for consistency
- Plugin-style architecture for entity identifiers
- Configuration-driven behavior (no hard-coded values)

**Benefits:**

- Easy to add new sources (see [Adding a New Extractor](../extractors/adding-extractor.md))
- Isolated testing and debugging
- Independent deployment and scaling
- Clear separation of concerns

### 2. Idempotency and Reproducibility

**Principle:** Running the same extraction, transformation, or loading operation multiple times produces the same result. Operations can be safely re-run without side effects.

**Implementation:**

- Dagster assets are idempotent by design
- Deterministic file naming with timestamps and UUIDs
- Upsert logic in loaders (update if exists, insert if new)
- No destructive operations on existing data

**Benefits:**

- Safe to re-run failed operations
- Enables incremental updates
- Supports data reprocessing with improved logic
- Maintains data consistency

### 3. Observability and Debugging

**Principle:** Full visibility into pipeline execution, data lineage, and system health.

**Implementation:**

- Dagster UI for real-time monitoring
- Comprehensive logging at all stages
- Run folders with complete data artifacts
- Extraction metadata tracking provenance
- Error files for failed transformations

**Benefits:**

- Easy debugging when issues occur
- Track data quality and sources
- Monitor performance and bottlenecks
- Audit trail for compliance

### 4. Fault Tolerance and Resilience

**Principle:** System continues operating even when individual components fail. Errors are isolated and don't cascade.

**Implementation:**

- Continue processing on individual item failures
- Retry logic with exponential backoff
- Graceful degradation (partial results better than none)
- Comprehensive error logging and reporting
- Health checks for all services

**Benefits:**

- High availability and reliability
- Maximum data extraction success rate
- Clear error reporting for manual intervention
- System stability under load

### 5. Data Quality and Validation

**Principle:** Validate data at every stage to catch errors early and ensure consistency.

**Implementation:**

- Pydantic schema validation for FAIR4ML
- Type checking and constraint validation
- Extraction metadata for provenance
- Error collection and reporting
- Required vs. optional field handling

**Benefits:**

- Catch errors before they reach production
- Ensure data consistency
- Track data quality metrics
- Enable data quality improvements

### 6. Performance and Scalability

**Principle:** System should handle large datasets efficiently and scale horizontally.

**Implementation:**

- Parallel processing (multi-threading, async operations)
- Batch processing for bulk operations
- Connection pooling for databases
- Efficient data structures (DataFrames, generators)
- Horizontal scaling support (Kubernetes-ready)

**Benefits:**

- Fast processing of large datasets
- Efficient resource utilization
- Scales with data volume
- Supports production workloads

### 7. Standardization and Interoperability

**Principle:** All data is transformed to a standard format (FAIR4ML) enabling cross-platform comparison and integration.

**Implementation:**

- FAIR4ML schema for all normalized data
- RDF export for semantic web compatibility
- Standard vocabularies (schema.org, FAIR4ML)
- Consistent data structures across sources

**Benefits:**

- Unified search across all sources
- Easy integration with other systems
- FAIR data compliance
- Cross-platform model comparison

---

## Technology Choices

### Orchestration: Dagster

**Why Dagster?**

Dagster is purpose-built for data pipelines with several key advantages:

1. **Asset-Based Model:** Data artifacts (files, database records) are first-class citizens, making dependencies explicit and visible.

2. **Excellent Observability:** Built-in web UI shows:

      - Real-time execution status
      - Data lineage graphs
      - Performance metrics
      - Error details and stack traces

3. **Dependency Management:** Automatic dependency resolution ensures correct execution order.

4. **Retry and Recovery:** Built-in retry logic with configurable backoff strategies.

5. **Type Safety:** Integration with Pydantic for type checking and validation.

6. **Flexible Execution:** Supports local, distributed, and cloud execution.

**Alternatives Considered:**

- **Airflow:** More complex, less intuitive for data pipelines
- **Prefect:** Good but less mature ecosystem
- **Luigi:** Older, less feature-rich

### Graph Database: Neo4j

**Why Neo4j?**

Neo4j is the leading native graph database, perfect for relationship-heavy data:

1. **Native Graph Model:** Stores data as nodes and relationships, not tables. Perfect for knowledge graphs.

2. **Cypher Query Language:** Intuitive, declarative language for graph queries. Much easier than SQL for relationship queries.

3. **Performance:** Optimized for graph traversals. Relationship queries are fast even with millions of nodes.

4. **Neosemantics (n10s) Plugin:** Enables RDF support, allowing us to:

      - Import/export RDF data
      - Use standard vocabularies
      - Support SPARQL queries
      - Enable semantic web integration

5. **Mature Ecosystem:** Well-documented, stable, production-ready.

**Alternatives Considered:**

- **Amazon Neptune:** Cloud-only, vendor lock-in
- **ArangoDB:** Multi-model but less optimized for pure graph use cases
- **PostgreSQL with extensions:** Not native graph, slower for relationship queries

### Search Engine: Elasticsearch

**Why Elasticsearch?**

Elasticsearch is the industry standard for full-text search:

1. **Full-Text Search:** Powerful text analysis, stemming, and relevance scoring.

2. **Flexible Querying:** Supports complex queries, filters, aggregations, and faceting.

3. **Performance:** Optimized for search workloads. Handles millions of documents efficiently.

4. **Rich Ecosystem:** Kibana for visualization, extensive plugin ecosystem.

5. **Scalability:** Horizontal scaling with sharding and replication.

6. **Production-Ready:** Battle-tested at scale by major companies.

**Alternatives Considered:**

- **Solr:** Similar features but less modern API
- **Algolia:** Commercial, expensive at scale
- **PostgreSQL Full-Text Search:** Less powerful, not optimized for search

### Schema Validation: Pydantic

**Why Pydantic?**

Pydantic provides type-safe data validation with excellent developer experience:

1. **Type Safety:** Automatic type checking and conversion.

2. **Validation:** Built-in validators for common patterns (URLs, emails, dates).

3. **JSON Schema:** Automatic JSON schema generation for API documentation.

4. **Performance:** Fast validation using Rust-based core.

5. **Python Integration:** Native Python types, excellent IDE support.

6. **Error Messages:** Clear, helpful error messages for debugging.

**Alternatives Considered:**

- **Cerberus:** Less type-safe, more verbose
- **Marshmallow:** Older, less performant
- **Manual validation:** Error-prone, time-consuming

### Language: Python 3.11+

**Why Python?**

Python is the language of choice for data processing and ML:

1. **Rich Ecosystem:** Excellent libraries for:

      - Data processing (Pandas, NumPy)
      - API clients (requests, httpx)
      - Web scraping (Selenium, BeautifulSoup)
      - ML libraries (transformers, scikit-learn)

2. **Developer Productivity:** Fast development, readable code, extensive documentation.

3. **Community:** Large, active community with extensive resources.

4. **Integration:** Easy integration with other systems and languages.

5. **Type Hints:** Python 3.11+ has excellent type hint support for better code quality.

**Trade-offs:**

- Slower than compiled languages, but acceptable for I/O-bound operations
- GIL limits true parallelism, but we use processes/threads where needed

### Containers: Docker & Docker Compose

**Why Docker?**

Docker provides service isolation and consistent environments:

1. **Isolation:** Each service runs in its own container with isolated dependencies.

2. **Reproducibility:** Same environment in development, testing, and production.

3. **Easy Deployment:** Single command to start all services.

4. **Resource Management:** Control CPU and memory per service.

5. **Development Experience:** Fast iteration, easy cleanup, consistent setup.

**Why Docker Compose?**

Docker Compose orchestrates multiple containers:

1. **Service Orchestration:** Define all services in one file.

2. **Networking:** Automatic service discovery and networking.

3. **Volume Management:** Persistent data storage.

4. **Health Checks:** Automatic service health monitoring.

5. **Profiles:** Run different service combinations (ETL, API, complete).

---

## Scalability Considerations

### Current Architecture (Single Node)

The current architecture is designed for single-node deployment suitable for:

- Development and testing
- Small to medium datasets (< 10M models)
- Single team usage

**Limitations:**

- Single point of failure
- Limited by single machine resources
- Sequential processing bottlenecks

### Horizontal Scaling Strategy

The system is designed to scale horizontally:

#### 1. Extractors

**Scaling Approach:**

- Run multiple extractors in parallel (different sources)
- Use thread pools for parallel API calls
- Distribute extraction across multiple workers

**Implementation:**

- Each extractor is independent
- Can run on separate machines
- Dagster supports distributed execution

#### 2. Transformers

**Scaling Approach:**

- Parallel property extraction (already implemented)
- Process multiple sources simultaneously
- Batch processing for large datasets

**Implementation:**

- Property groups extracted in parallel
- Can scale by adding more transformer workers
- Stateless transformation (easy to parallelize)

#### 3. Loaders

**Scaling Approach:**

- Parallel loading to multiple systems
- Batch operations for efficiency
- Connection pooling

**Implementation:**

- Neo4j: Batch RDF triple insertion
- Elasticsearch: Bulk indexing
- Can add more loader workers

#### 4. Storage Systems

**Neo4j Scaling:**

- Neo4j supports clustering (Enterprise edition)
- Read replicas for query scaling
- Sharding strategies for very large graphs

**Elasticsearch Scaling:**

- Native horizontal scaling with sharding
- Add more nodes to increase capacity
- Automatic load balancing

### Kubernetes Deployment (Future)

For production at scale, Kubernetes provides:

1. **Auto-Scaling:** Automatically scale workers based on load
2. **High Availability:** Automatic failover and recovery
3. **Resource Management:** CPU and memory limits per pod
4. **Service Discovery:** Automatic service registration
5. **Rolling Updates:** Zero-downtime deployments

**Architecture:**
```
Kubernetes Cluster
├── Dagster Workers (multiple pods)
├── Neo4j Cluster (StatefulSet)
├── Elasticsearch Cluster (StatefulSet)
├── PostgreSQL (StatefulSet)
└── API Servers (Deployment with replicas)
```

### Performance Optimization

**Current Optimizations:**

- Parallel processing (threads, async)
- Batch operations (bulk inserts, bulk indexing)
- Connection pooling
- Efficient data structures (DataFrames)

**Future Optimizations:**

- Caching frequently accessed data
- Incremental updates (only process changed data)
- Data partitioning by source/date
- Compression for stored data

---

## Data Architecture

### Storage Layers

The system uses a three-layer storage architecture:

1. **Raw Data Layer** (`/data/1_raw/`)

   - Original source data, unmodified
   - Organized by source and run
   - Preserved for debugging and reprocessing

2. **Normalized Data Layer** (`/data/2_normalized/`)

   - FAIR4ML-compliant data
   - Validated and enriched
   - Ready for loading

3. **RDF Export Layer** (`/data/3_rdf/`)

   - Semantic web format (Turtle)
   - For interoperability and archival
   - Human-readable and machine-processable

### Data Organization

**Run-Based Organization:**
```
/data/1_raw/hf/2025-01-15_12-00-00_abc123/
├── hf_models.json
├── hf_datasets.json
└── ...

/data/2_normalized/hf/2025-01-15_12-00-00_abc123/
├── mlmodels.json
├── datasets.json
└── ...
```

**Benefits:**

- Easy to track what was extracted when
- Compare outputs across runs
- Clean up or archive complete runs
- Debug specific extraction runs

### Data Retention

**Strategy:**

- Keep all raw data (for reprocessing)
- Keep normalized data (for reloading)
- Keep RDF exports (for archival)
- Configurable retention policies

**Implementation:**

- Manual cleanup scripts
- Future: Automated retention policies
- Future: Archive to object storage (S3, etc.)

---

## Security Considerations

### Current Security Measures

1. **Environment Variables:** Secrets stored in `.env` (not in code)
2. **Network Isolation:** Docker networks for service isolation
3. **Read-Only Access:** API uses read-only database credentials
4. **Input Validation:** Pydantic validation prevents injection attacks

### Production Security (Future)

1. **Authentication:** API key or OAuth2 for API access
2. **Rate Limiting:** Per-client throttling
3. **HTTPS:** SSL/TLS termination
4. **Secrets Management:** Kubernetes secrets, AWS Secrets Manager
5. **Network Policies:** Restrict service-to-service communication
6. **Audit Logging:** Track all data access and modifications

---

## Monitoring and Observability

### Current Monitoring

1. **Dagster UI:** Pipeline execution monitoring
2. **Logging:** Comprehensive logging at all stages
3. **Health Checks:** Service health endpoints
4. **Error Files:** Detailed error reporting

### Production Monitoring (Future)

1. **Metrics:** Prometheus for metrics collection
2. **Dashboards:** Grafana for visualization
3. **Alerting:** Alert on errors, performance degradation
4. **Tracing:** Distributed tracing for request flows
5. **Log Aggregation:** Centralized logging (ELK stack)

---

## Related Documentation

- **[Architecture Overview](overview.md)** - High-level system overview
- **[Data Flow](data-flow.md)** - Detailed data journey through the system
- **[Component Details](components.md)** - Deep dive into each component
- **[Deployment](deployment.md)** - Production deployment guide
