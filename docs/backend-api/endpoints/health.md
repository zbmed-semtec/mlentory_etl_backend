# Health Endpoints

Complete reference for health check and system status endpoints.

---

## Health Check

### `GET /health`

Health check endpoint that tests connections to Elasticsearch and Neo4j.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "elasticsearch": true,
  "neo4j": true
}
```

**Status Values:**
- `healthy` - All services are operational
- `degraded` - One or more services are unavailable

**Service Status:**
- `true` - Service is reachable and responding
- `false` - Service is unreachable or not responding

---

## Root Endpoint

### `GET /`

Root endpoint with API information.

**Response:**
```json
{
  "name": "MLentory API",
  "version": "1.0.0",
  "description": "API for querying ML model metadata from FAIR4ML knowledge graph",
  "docs": "/docs",
  "health": "/health"
}
```

---

## Use Cases

### Monitoring

Use the health endpoint for monitoring and alerting:

```bash
# Check API health
curl http://localhost:8000/health

# Parse status
STATUS=$(curl -s http://localhost:8000/health | jq -r '.status')
if [ "$STATUS" != "healthy" ]; then
  echo "API is degraded!"
fi
```

### Load Balancer Health Checks

Configure load balancers to use the health endpoint:

```yaml
health_check:
  path: /health
  interval: 30s
  timeout: 5s
  healthy_threshold: 2
  unhealthy_threshold: 3
```

---

## Error Responses

- `500 Internal Server Error` - Health check failed

See [Error Handling](../reference/errors.md) for details.

