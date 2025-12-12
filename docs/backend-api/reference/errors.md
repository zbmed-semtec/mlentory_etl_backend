# Error Handling

Complete reference for API error responses and handling.

---

## HTTP Status Codes

The API uses standard HTTP status codes:

- `200 OK` - Successful request
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Invalid request parameters
- `500 Internal Server Error` - Server-side error

---

## Error Response Format

All errors follow a consistent format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Common Errors

### 404 Not Found

**When:** Requested resource doesn't exist

**Example:**
```json
{
  "detail": "Model not found"
}
```

**Common Causes:**
- Invalid model ID
- Model doesn't exist in database
- Incorrect entity type

---

### 422 Unprocessable Entity

**When:** Request parameters are invalid

**Example:**
```json
{
  "detail": [
    {
      "loc": ["query", "page"],
      "msg": "ensure this value is greater than 0",
      "type": "value_error.number.not_gt",
      "ctx": {"limit_value": 0}
    }
  ]
}
```

**Common Causes:**
- Invalid parameter types
- Parameter values outside allowed range
- Missing required parameters
- Invalid JSON in query parameters

---

### 500 Internal Server Error

**When:** Server-side error occurred

**Example:**
```json
{
  "detail": "Internal server error"
}
```

**Common Causes:**
- Database connection failure
- Unexpected server error
- Service unavailable

---

## Error Handling Examples

### Python

```python
import requests

try:
    response = requests.get("http://localhost:8000/api/v1/models/invalid-id")
    response.raise_for_status()
    data = response.json()
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 404:
        print("Model not found")
    elif e.response.status_code == 422:
        error_detail = e.response.json()
        print(f"Validation error: {error_detail['detail']}")
    else:
        print(f"HTTP error: {e}")
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
```

### JavaScript

```javascript
try {
  const response = await fetch('http://localhost:8000/api/v1/models/invalid-id');
  
  if (!response.ok) {
    if (response.status === 404) {
      console.error('Model not found');
    } else if (response.status === 422) {
      const error = await response.json();
      console.error('Validation error:', error.detail);
    } else {
      console.error(`HTTP error: ${response.status}`);
    }
    return;
  }
  
  const data = await response.json();
  // Process data
} catch (error) {
  console.error('Request failed:', error);
}
```

---

## Validation Errors

Pydantic validation errors provide detailed information:

```json
{
  "detail": [
    {
      "loc": ["query", "page_size"],
      "msg": "ensure this value is less than or equal to 100",
      "type": "value_error.number.not_le",
      "ctx": {"limit_value": 100}
    }
  ]
}
```

**Fields:**
- `loc` - Location of the error (path to field)
- `msg` - Error message
- `type` - Error type
- `ctx` - Additional context

---

## Best Practices

### Check Status Codes

Always check HTTP status codes before processing responses:

```python
response = requests.get(url)
if response.status_code == 200:
    data = response.json()
elif response.status_code == 404:
    print("Not found")
else:
    print(f"Error: {response.status_code}")
```

### Handle Network Errors

Network errors may occur independently of HTTP status codes:

```python
try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
except requests.exceptions.Timeout:
    print("Request timed out")
except requests.exceptions.ConnectionError:
    print("Connection failed")
except requests.exceptions.RequestException as e:
    print(f"Request error: {e}")
```

### Retry Logic

For transient errors, implement retry logic:

```python
import time
from requests.exceptions import RequestException

def retry_request(url, max_retries=3, backoff=1):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff * (2 ** attempt))
    return None
```

---

## Health Check Errors

The `/health` endpoint may return `degraded` status:

```json
{
  "status": "degraded",
  "version": "1.0.0",
  "elasticsearch": true,
  "neo4j": false
}
```

This indicates one or more services are unavailable, but the API is still partially functional.

---

## Next Steps

- **[API Schemas](schemas.md)** → Understand response formats
- **[API Endpoints](../endpoints/models.md)** → See error handling in context
- **[API Usage](../usage/examples.md)** → See error handling examples

