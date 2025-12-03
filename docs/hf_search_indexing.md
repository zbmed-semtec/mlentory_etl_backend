# HuggingFace Search Index & Faceted Search

## Overview

This document explains how the HuggingFace search index in Elasticsearch is wired into the API layer, and how to **add new properties** to:

- The Elasticsearch index (documents and mappings)
- The API response models
- The faceted search and filters

The main components involved are:

- `etl/assets/hf_loading.py` – Dagster assets that orchestrate Elasticsearch indexing
- `etl_loaders/hf_index_loader.py` – Index document definition and indexing logic
- `api/services/elasticsearch_service.py` – Core search service used by the API
- `api/services/faceted_search.py` – Faceted search mixin and aggregations
- `api/schemas/responses.py` – Pydantic response models (`ModelListItem`, faceted search responses)
- `api/routers/models.py` – HTTP endpoints that expose search and facets

The example below uses the `datasets` field, which is indexed from FAIR4ML model metadata and exposed in the search & facet APIs.

---

## Data Flow Recap (HF → Elasticsearch → API)

1. **Normalized FAIR4ML models**
   - Produced by `hf_models_normalized` asset.
   - Serialized as `/data/2_normalized/hf/{run_id}/mlmodels.json`.

2. **Indexing into Elasticsearch**
   - Orchestrated by `hf_index_models_elasticsearch` asset in `etl/assets/hf_loading.py`.
   - Uses `etl_loaders/hf_index_loader.py`:
     - `HFModelDocument` – Elasticsearch DSL document mapping.
     - `build_hf_model_document()` – Translates FAIR4ML JSON → `HFModelDocument` fields.
     - `index_hf_models()` – Bulk indexing loop.

3. **Search service**
   - `api/services/elasticsearch_service.py`:
     - `search_models()` – Simple list search (no facets).
     - `get_model_by_id()` – Fetch a single model.
   - Both return `ModelListItem` objects.

4. **Faceted search**
   - `api/services/faceted_search.py` (`FacetedSearchMixin`):
     - `get_facets_config()` – Declares available facets & their ES fields.
     - `search_models_with_facets()` – Executes ES query + aggregations.
     - `fetch_facet_values()` – Paginates facet values.

5. **HTTP API**
   - `api/routers/models.py`:
     - `GET /api/v1/models` – Uses `search_models()`.
     - `GET /api/v1/models/{model_id}` – Uses `get_model_by_id()`.
     - `GET /api/v1/models/search` – Uses `search_models_with_facets()`.
     - `GET /api/v1/models/facets/values` – Uses `fetch_facet_values()`.

---

## Checklist: Adding a New Property to the Index

When you add a new property (e.g., `datasets`, `modelCategory`, `language`), you generally need to touch **four layers**:

1. **Normalized FAIR4ML JSON** – make sure the data actually exists.
2. **Elasticsearch index & loader** – add a field to the ES document and populate it.
3. **API response models & services** – expose the field in `ModelListItem`.
4. **Faceted search configuration (optional)** – if the field should be used as a facet.

The sections below describe each step in detail.

---

## 1. Ensure the Normalized Data Contains the Property

Before changing the index, confirm the property is present in the normalized FAIR4ML models:

- Source: the JSON produced by `hf_models_normalized` (e.g. `/data/2_normalized/hf/{run_id}/mlmodels.json`).
- For example, `datasets` are collected from FAIR4ML properties like:
  - `https://w3id.org/fair4ml/trainedOn`
  - `https://w3id.org/fair4ml/testedOn`
  - `https://w3id.org/fair4ml/validatedOn`
  - `https://w3id.org/fair4ml/evaluatedOn`

If the property is missing here, add it in the **transformation** layer first (see the HF transformation docs).

---

## 2. Add the Property to the Elasticsearch Document

### 2.1. Add a Field to `HFModelDocument`

File: `etl_loaders/hf_index_loader.py`

Define a new field on the `HFModelDocument` class with the correct Elasticsearch type, e.g.:

- `Keyword()` for exact matches
- `Text()` for full-text search
- `Keyword(multi=True)` for multi-valued keyword fields

Example (simplified):

```python
class HFModelDocument(Document):
    ...
    datasets = Keyword(multi=True)
    ...
```

### 2.2. Populate the Field in `build_hf_model_document`

Still in `etl_loaders/hf_index_loader.py`, update `build_hf_model_document()` to:

1. Extract the value(s) from the normalized model dict.
2. Normalize them to the right shape (string vs list of strings).
3. Optionally translate IRIs to human-readable labels using the translation mapping.
4. Pass the value(s) into the `HFModelDocument` constructor.

Example (simplified, using `datasets`):

```python
datasets = [...]  # collect from FAIR4ML properties

# Optional: translate URIs to names using translation_mapping
datasets = [translation_mapping.get(dataset, dataset) for dataset in datasets]

doc = HFModelDocument(
    ...
    datasets=_extract_list(datasets),
    ...
)
```

> **Note:** `HFModelDocument.init()` in `index_hf_models()` ensures the index and mappings exist. Adding a **new** field of a compatible type is usually safe; changing the type of an existing field typically requires re-creating the index.

### 2.3. Reindex the Data

To apply the new field to all documents:

1. Optionally clean the index (removes documents, keeps mappings):
   - Use `clean_hf_models_index()` (from `etl_loaders/elasticsearch_store.py`) if you just want to delete all docs.
2. Re-materialize the HF indexing assets:
   - Run the `hf_index_models_elasticsearch` asset (or the full `hf_etl` pipeline) as described in `docs/running_pipelines.md`.

---

## 3. Expose the Property in API Response Models

### 3.1. Add the Field to `ModelListItem`

File: `api/schemas/responses.py`

Add a field to the `ModelListItem` Pydantic model so that it appears in API responses:

```python
class ModelListItem(BaseModel):
    ...
    datasets: List[str] = Field(
        description="Datasets the model was trained on",
        default_factory=list,
    )
    ...
```

### 3.2. Map the Field in `ElasticsearchService`

File: `api/services/elasticsearch_service.py`

Update both `search_models()` and `get_model_by_id()` to map the Elasticsearch field onto the new Pydantic field.

Example:

```python
model = ModelListItem(
    db_identifier=hit.db_identifier,
    name=hit.name or "",
    description=hit.description,
    sharedBy=hit.shared_by,
    license=hit.license,
    mlTask=hit.ml_tasks or [],
    keywords=hit.keywords or [],
    datasets=getattr(hit, "datasets", None) or [],
    platform=hit.platform or "Unknown",
)
```

> **Tip:** Always default to an empty list (`[]`) for multi-valued fields to keep the API stable.

---

## 4. Wire the Property into Faceted Search (Optional but Recommended)

If the new property should be filterable / faceted in the UI, you must:

1. Add it to the facet configuration (`FacetedSearchMixin.get_facets_config()`).
2. Include it in `_source` so Elasticsearch returns it with hits.
3. Map it into `ModelListItem` in the faceted search path.
4. Optionally add it to default facets and docs in the router.

### 4.1. Facet Configuration

File: `api/services/faceted_search.py`

Add a new entry in `get_facets_config()` specifying the ES field and facet metadata:

```python
return {
    ...
    "datasets": FacetConfig(
        field="datasets",
        label="Datasets",
        type="keyword",
        icon="mdi-database",
        is_high_cardinality=True,
        default_size=10,
        supports_search=True,
        pinned=False,
    ),
    ...
}
```

### 4.2. Ensure `_source` Includes the Field

Still in `FacetedSearchMixin.search_models_with_facets()`, make sure the `_source` list contains the field so it is available in the `_source` of hits:

```python
search_body = {
    ...
    "_source": [
        "name",
        "ml_tasks",
        "shared_by",
        "db_identifier",
        "keywords",
        "license",
        "description",
        "platform",
        "datasets",
    ],
}
```

### 4.3. Map Hits to `ModelListItem` in Faceted Search

In `search_models_with_facets()`, update the hit → model mapping:

```python
for hit in hits_data.get("hits", []):
    source = hit.get("_source", {})
    model = ModelListItem(
        db_identifier=source.get("db_identifier", ""),
        name=source.get("name", ""),
        description=source.get("description"),
        sharedBy=source.get("shared_by"),
        license=source.get("license"),
        mlTask=source.get("ml_tasks", []),
        keywords=source.get("keywords", []),
        datasets=source.get("datasets", []) or [],
        platform=source.get("platform", "Unknown"),
    )
    models.append(model)
```

### 4.4. Router Defaults and Documentation

File: `api/routers/models.py`

Update the default facets parameter and the docs for supported facet fields:

```python
@router.get("/models/search", response_model=FacetedSearchResponse)
async def search_models_with_facets(
    ...
    facets: str = Query(
        '["mlTask", "license", "keywords", "datasets", "platform"]',
        description="JSON array of facet field names to aggregate",
        examples=['["mlTask", "license", "keywords", "datasets"]'],
    ),
    ...
)
```

And in the `get_facet_values` docstring, add the new field to the **Supported Fields** list.

---

## 5. Verifying the New Property End-to-End

After implementing all the steps above:

1. **Rebuild & rerun indexing**
   - Run the HF ETL pipeline (or at least the indexing stage) so new documents with the added field are written to Elasticsearch.

2. **Inspect an ES document**
   - Use Kibana or `curl` to fetch a document and confirm the field exists:
   - Check that it has the expected type (e.g. keyword array).

3. **Call the API**
   - `GET /api/v1/models` – verify the new field appears in `results[*]`.
   - `GET /api/v1/models/search` – verify the field is present in `models[*]` and, if configured, in `facets`.
   - `GET /api/v1/models/facets/values?field=<yourFacetKey>` – verify facet values can be fetched.

4. **UI verification (if applicable)**
   - Confirm that the front-end renders the new property / facet as expected.

---

## 6. Minimal Change Checklist (Copy/Paste)

When adding a new property (example: `datasets`):

1. **Loader / Index**
   - [ ] Add field to `HFModelDocument` in `etl_loaders/hf_index_loader.py`.
   - [ ] Populate the field in `build_hf_model_document()`.
   - [ ] Re-run `hf_index_models_elasticsearch` (or full `hf_etl`).

2. **API Models & Services**
   - [ ] Add field to `ModelListItem` in `api/schemas/responses.py`.
   - [ ] Map field in `ElasticsearchService.search_models()` and `get_model_by_id()`.

3. **Faceted Search (optional)**
   - [ ] Add facet entry in `get_facets_config()` in `api/services/faceted_search.py`.
   - [ ] Include field in `_source` in `search_models_with_facets()`.
   - [ ] Map field in the hit → `ModelListItem` conversion.
   - [ ] Add to default facets and docs in `api/routers/models.py`.

Following this checklist keeps the **ETL, index, and API** layers in sync whenever you introduce new search properties. 


