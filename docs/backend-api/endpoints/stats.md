# Statistics Endpoints

Complete reference for statistics and aggregation API endpoints.

---

## Platform Statistics

### `GET /api/v1/stats/platform`

Get platform-wide statistics and aggregations.

**Response:**
```json
{
  "total_models": 15000,
  "platforms": {
    "Hugging Face": 12000,
    "OpenML": 2500,
    "AI4Life": 500
  },
  "licenses": {
    "MIT": 5000,
    "Apache-2.0": 3000,
    "CC-BY-4.0": 2000
  },
  "ml_tasks": {
    "text-classification": 4000,
    "image-classification": 3500,
    "text-generation": 2500
  }
}
```

---

## Error Responses

- `500 Internal Server Error` - Server-side error

See [Error Handling](../reference/errors.md) for details.

