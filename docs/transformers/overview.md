#Overview

Transformers are the second stage of the MLentory ETL pipeline, responsible for converting source-specific raw data into the standardized FAIR4ML schema format. This transformation is what makes it possible to compare models from different platforms, build unified search systems, and create knowledge graphs that span multiple sources.

---

## What is Transformation and Why Does It Matter?

Imagine you're trying to build a search system that works across HuggingFace, OpenML, and AI4Life. HuggingFace calls a model's identifier `modelId`, OpenML calls it `flow_id`, and AI4Life calls it `id`. HuggingFace stores the ML task as `pipeline_tag`, OpenML uses `task_type`, and AI4Life might not have this field at all. Each platform uses different field names, different data structures, and different conventions.

**Transformation** is the process of converting all these different formats into a single, standardized format—FAIR4ML. Think of it as translating multiple languages into one common language. Just as a translator converts English, Spanish, and French into a target language, transformers convert HuggingFace format, OpenML format, and AI4Life format into FAIR4ML format.

Transformation acts as a universal translator, converting platform-specific formats into the standardized FAIR4ML schema that enables comparison and integration.

### The Problem Transformation Solves

Without transformation, you'd need separate search logic for each platform. Want to find all models for sentiment analysis? You'd need to:

- Search HuggingFace for models with `pipeline_tag` containing "sentiment"
- Search OpenML for flows with `task_type` equal to "classification" and check descriptions
- Search AI4Life using yet another approach
- Then somehow combine these results

With transformation, you have a single format. You search for models with `mlTask` containing "sentiment-analysis" or "text-classification", and it works across all sources because they've all been transformed to the same schema.

### The Transformation Journey

Transformation happens in several stages:

**Input** is raw JSON files from the extraction stage. These files contain data exactly as received from source platforms, with all their platform-specific quirks and formats.

**Processing** involves mapping each source field to FAIR4ML properties, handling missing data, normalizing values, and enriching information.

**Validation** ensures the transformed data conforms to the FAIR4ML schema, catching errors early before they cause problems downstream.

**Output** is normalized FAIR4ML JSON files that can be used by loaders, searched uniformly, and integrated with other systems.

---

## Why Normalize to FAIR4ML?

Normalization to FAIR4ML provides several critical benefits that make the entire MLentory system possible:

### Interoperability: Speaking the Same Language

When all sources use the same format, systems can work with data from any source without special handling. A search system doesn't need to know whether a model came from HuggingFace or OpenML—it just works with FAIR4ML.

**Unified Search** becomes possible because you can search across all sources using the same query. "Find all models for sentiment analysis" works the same way regardless of source.

**Comparison** becomes meaningful because models from different platforms use the same field names and structures. You can compare a HuggingFace model and an OpenML model directly because they're both in FAIR4ML format.

**Integration** with other systems becomes easier because FAIR4ML is a standard that other tools can understand. You're not locked into platform-specific formats.

### Standardization: Consistency and Predictability

FAIR4ML provides standardized field names, consistent data types, and well-defined relationships. This standardization eliminates ambiguity and makes the system predictable.

**Field Names** are consistent. Every model has an `identifier`, a `name`, an `mlTask`, regardless of source. You don't need to remember that HuggingFace uses `modelId` while OpenML uses `flow_id`.

**Data Types** are consistent. Dates are always ISO 8601 datetime objects, lists are always arrays, strings are always strings. This consistency prevents type-related bugs.

**Relationships** are well-defined. You know that `trainedOn` always contains dataset identifiers, `fineTunedFrom` always contains model identifiers. This structure enables reliable relationship queries.

### Data Quality: Catching Problems Early

Transformation includes validation that ensures data quality. By validating against the FAIR4ML Pydantic schema, we catch errors before they propagate through the system.

**Required Fields** are checked. If a model is missing its `name` or `identifier`, validation fails immediately with a clear error message, not later when someone tries to search for it.

**Data Types** are verified. If a date field contains "not-a-date" instead of a valid datetime, validation catches it. If a list field contains a string, validation catches it.

**Value Validation** ensures data makes sense. Confidence scores are between 0 and 1, dates are in valid ranges, URLs are properly formatted.

**Early Detection** means problems are found during transformation, when you have the original data available for debugging. This is much better than discovering issues later when debugging is harder.

### Extensibility: Growing Without Breaking

The transformation approach makes it easy to add new sources without changing downstream systems.

**New Source?** Just create a new transformer that maps that source's format to FAIR4ML. The loaders, search systems, and other downstream components don't need to change—they already understand FAIR4ML.

**Schema Evolution?** When FAIR4ML adds new properties, you can update transformers to populate them. Existing data continues to work (new fields are optional), and new data can include the new properties.

**Backward Compatibility** is maintained because transformation is a one-way process. Old raw data can be re-transformed with new logic, but existing normalized data continues to work.

---

## The Transformation Process: Step by Step

Understanding the transformation process helps you debug issues, extend transformers, and understand how data flows through the system.

### Step 1: Reading Raw Data

The transformation process begins by reading the raw JSON files created during extraction. These files contain data in source-specific formats, exactly as received from the platforms.

**File Loading** involves reading JSON files from the extraction stage's output directory. Files are organized by source and run, making it easy to find the right data.

**Parsing** converts JSON strings into Python objects (dictionaries, lists, etc.). This parsing handles platform-specific structures, including wrapped metadata formats used by some sources.

**Error Handling** deals with malformed JSON, missing files, or unexpected structures. Transformers are designed to handle these gracefully, logging errors and continuing with valid data.

### Step 2: Field Mapping

The core of transformation is mapping source fields to FAIR4ML properties. This mapping handles the differences between platforms.

**Direct Mapping** is the simplest case—a source field maps directly to a FAIR4ML property with the same meaning. For example, HuggingFace's `author` field maps directly to FAIR4ML's `author` property.

**Value Transformation** converts values to standard formats. HuggingFace's `pipeline_tag` (a string like "fill-mask") becomes FAIR4ML's `mlTask` (a list like ["fill-mask"]). This normalization ensures consistent structures.

**Field Combination** merges multiple source fields into one FAIR4ML property. Keywords might come from HuggingFace's `tags` field and `library_name` field, combined into FAIR4ML's `keywords` list.

**Reference Resolution** converts platform-specific references into standard identifiers. A HuggingFace base model name like "bert-base-uncased" becomes a full URL like "https://huggingface.co/bert-base-uncased" in FAIR4ML's `fineTunedFrom` property.

**Extraction from Text** parses structured data from unstructured text. Model cards (Markdown files) might contain license information in frontmatter, descriptions in the body, and code examples in code blocks. Transformers extract this information intelligently.

### Step 3: Data Validation

After mapping, transformed data is validated against the FAIR4ML Pydantic schema. This validation ensures data quality and catches errors early.

**Schema Validation** checks that all required fields are present, data types are correct, and values are in valid ranges. Pydantic provides automatic validation based on type annotations and field constraints.

**Error Collection** gathers all validation errors for a model, not just the first one. This provides comprehensive feedback about what needs to be fixed.

**Error Reporting** saves validation errors to separate files, allowing you to see which models failed validation and why, without stopping the entire transformation process.

**Partial Success** means that if some models fail validation, others continue processing. This maximizes the amount of valid data produced.

### Step 4: Data Enrichment

Enrichment adds information that wasn't in the raw data but can be computed or inferred.

**Computed Fields** are generated from existing data. MLentory IDs are minted for each model, providing unique identifiers that work across all sources.

**Derived Values** are calculated from other fields. A model's category might be inferred from its library name (e.g., "transformers" → "transformer").

**Reference Resolution** links to related entities. Dataset names mentioned in model descriptions are resolved to full dataset identifiers.

**Extraction Metadata** tracks how each field was obtained. This includes the extraction method, confidence score, and source field name. This metadata is crucial for debugging and understanding data quality.

### Step 5: Saving Normalized Data

Finally, validated and enriched data is saved as FAIR4ML JSON files.

**File Organization** follows the same run folder pattern as extraction. All normalized files from one transformation run are grouped together.

**Format Consistency** ensures all files use the same FAIR4ML structure, making them easy to process programmatically.

**Error Files** are saved alongside successful transformations, providing a complete picture of what succeeded and what failed.

---

## Modular Transformation Architecture: Parallel Processing

The HuggingFace transformer uses a sophisticated modular architecture where different property groups are extracted in parallel. This design provides several advantages over sequential processing.

### Why Modular Architecture?

**Parallel Processing** dramatically improves performance. Instead of processing all properties sequentially (which might take minutes), properties are extracted simultaneously (taking seconds).

**Error Isolation** means that if one property group fails (e.g., license extraction), others continue (e.g., basic properties, tasks). This maximizes success rate.

**Maintainability** is improved because each property group is a separate module. You can understand, test, and modify one property group without affecting others.

**Extensibility** makes it easy to add new property groups. Want to extract a new type of information? Just create a new property extractor module.

**Testability** is enhanced because each property group can be tested independently. You can test license extraction without running the entire transformation.

The modular architecture enables parallel processing of property groups, improving performance and maintainability. Each property group is extracted independently, then merged into complete FAIR4ML objects.

### Property Groups: Organized by Function

The HuggingFace transformer organizes properties into logical groups:

**Basic Properties** include core identification (identifier, name, url), authorship (author, sharedBy), temporal information (dates), and description. These are the foundation that every model needs.

**Keywords & Language** extracts tags and keywords, filters out language codes and licenses, and identifies which natural languages the model works with.

**Task & Category** determines the ML tasks the model addresses and infers the model category/architecture from library names and tags.

**License** extracts license information from tags, model card frontmatter, and other sources.

**Lineage** identifies base models and builds the model family tree by following fine-tuning relationships.

**Code & Usage** extracts code snippets and usage instructions from model cards and documentation.

**Datasets** identifies training and evaluation datasets mentioned in model descriptions and metadata.

**Ethics & Risks** extracts information about model limitations, biases, and ethical considerations from model cards.

Each group is processed independently, and results are merged at the end.

### Parallel Processing Flow

```
Raw Models JSON
    ↓
    ├─→ Extract Basic Properties (parallel)
    ├─→ Extract Keywords & Language (parallel)
    ├─→ Extract Task & Category (parallel)
    ├─→ Extract License (parallel)
    ├─→ Extract Lineage (parallel)
    ├─→ Extract Code & Usage (parallel)
    ├─→ Extract Datasets (parallel)
    └─→ Extract Ethics & Risks (parallel)
        ↓
    Merge All Partial Schemas
        ↓
    Validate & Save FAIR4ML JSON
```

This parallel approach means that if you have 8 property groups and each takes 1 second, the total time is about 1 second (plus merge time) instead of 8 seconds sequential.

---

## Validation: Ensuring Data Quality

Validation is a critical part of transformation that ensures data quality before it reaches downstream systems.

### Pydantic Schema Validation

All transformed data is validated against FAIR4ML Pydantic models. This validation is automatic and comprehensive:

**Type Checking** ensures that fields have the correct types. A string field can't contain a number, a list field can't contain a string, etc.

**Required Fields** are checked. If a required field is missing, validation fails with a clear error message.

**Value Constraints** are enforced. Confidence scores must be between 0 and 1, dates must be valid ISO 8601 format, etc.

**Relationship Validation** ensures that references to other entities (like datasets or papers) are properly formatted.

**Example:**
```python
from schemas.fair4ml import MLModel

# Validate transformed data
try:
    model = MLModel(**transformed_data)
    # Valid! Model conforms to FAIR4ML schema
except ValidationError as e:
    # Invalid - log errors for debugging
    logger.error(f"Validation failed: {e}")
    save_validation_errors(model_id, e.errors())
```

### Error Handling Strategy

Validation errors don't stop the entire transformation. Instead, they're handled gracefully:

**Error Logging** captures detailed information about what went wrong, including the field name, error type, and invalid value.

**Error Files** save validation errors to separate JSON files, making it easy to see which models failed and why without searching through logs.

**Partial Success** means that if some models fail validation, others continue processing. This maximizes the amount of valid data.

**Error Analysis** becomes possible because errors are collected and saved. You can analyze error patterns to improve transformation logic.

**Example error file:**
```json
{
  "model_id": "bert-base-uncased",
  "errors": [
    {
      "field": "dateCreated",
      "error": "Invalid date format",
      "value": "invalid-date",
      "expected": "ISO 8601 datetime"
    }
  ]
}
```

---

## Data Enrichment: Adding Value

Enrichment adds information that wasn't explicitly in the raw data but can be computed, inferred, or resolved.

### Types of Enrichment

**Computed Fields** are generated from existing data. MLentory IDs are minted for each model using a consistent algorithm, providing unique identifiers that work across all sources.

**Derived Values** are calculated from other fields. A model's category might be inferred from its library name—if the library is "transformers", the category is likely "transformer".

**Reference Resolution** converts platform-specific references into standard identifiers. A dataset name like "squad" mentioned in a model description is resolved to a full identifier like "https://huggingface.co/datasets/squad".

**Extraction Metadata** tracks how each field was obtained. This includes the extraction method (e.g., "Parsed_from_HF_dataset", "Inferred_from_tags"), confidence score (0.0 to 1.0), and source field name. This metadata is crucial for debugging and understanding data quality.

### Example Enrichment

**Input (raw HuggingFace data):**
```json
{
  "modelId": "bert-base-uncased",
  "author": "google"
}
```

**Output (enriched FAIR4ML):**
```json
{
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "google",
  "mlentory_id": "mlentory:model:xyz789",
  "extraction_metadata": {
    "identifier": {
      "extraction_method": "Parsed_from_HF_dataset",
      "confidence": 1.0,
      "source_field": "modelId"
    }
  }
}
```

Notice how the raw data is enriched with:

- Full URL identifiers (computed from modelId)
- MLentory ID (minted for cross-platform compatibility)
- Extraction metadata (tracks provenance)

---

## Transformation Patterns: Common Solutions

Transformers use several common patterns to handle different types of field mappings:

### Pattern 1: Direct Mapping

The simplest pattern is direct mapping, where a source field maps directly to a FAIR4ML property with the same meaning.

**Example:**
```python
# HuggingFace → FAIR4ML
fair4ml["author"] = raw["author"]  # Direct copy
```

This works when field names and meanings align between source and target.

### Pattern 2: Value Transformation

Sometimes the value needs to be transformed to match the target format.

**Example:**
```python
# HuggingFace → FAIR4ML
# Source: "fill-mask" (string)
# Target: ["fill-mask"] (list)
fair4ml["mlTask"] = [raw["pipeline_tag"]]
```

This converts a single value into a list format required by FAIR4ML.

### Pattern 3: Field Combination

Multiple source fields might need to be combined into one FAIR4ML property.

**Example:**
```python
# HuggingFace → FAIR4ML
# Combine tags and library_name into keywords
keywords = raw.get("tags", [])
if raw.get("library_name"):
    keywords.append(raw["library_name"])
fair4ml["keywords"] = keywords
```

This merges information from multiple sources into a single property.

### Pattern 4: Reference Resolution

Platform-specific references need to be converted to standard identifiers.

**Example:**
```python
# HuggingFace → FAIR4ML
# Source: "bert-base-uncased" (model name)
# Target: ["https://huggingface.co/bert-base-uncased"] (full URL)
if raw.get("base_model"):
    fair4ml["fineTunedFrom"] = [f"https://huggingface.co/{raw['base_model']}"]
```

This converts simple names into full, resolvable identifiers.

### Pattern 5: Extraction from Text

Structured data might be embedded in unstructured text (like Markdown model cards).

**Example:**
```python
# Extract from model card markdown
card_text = raw.get("card", "")
description = extract_description_from_markdown(card_text)
license = extract_license_from_frontmatter(card_text)
fair4ml["description"] = description
fair4ml["license"] = license
```

This requires parsing text to extract structured information.

---

## Error Handling: Maximizing Success

Transformation includes comprehensive error handling to maximize the amount of valid data produced:

### Validation Errors

When validation fails, errors are handled gracefully:

**Error Logging** captures detailed information about what went wrong, including which fields failed and why.

**Error Files** save validation errors to separate JSON files, organized by entity type (models, datasets, etc.).

**Partial Success** means that if some models fail validation, others continue. This ensures you get as much valid data as possible.

**Error Analysis** becomes possible because errors are collected. You can identify patterns (e.g., "many models missing dateCreated") and improve transformation logic.

### Missing Data

Not all sources provide all fields. Transformers handle missing data gracefully:

**Optional Fields** can be missing—FAIR4ML defines many fields as optional to accommodate different sources.

**Required Fields** must be present—if a required field is missing, validation fails. This ensures data quality.

**Default Values** are used when appropriate. Empty lists, None values, or sensible defaults prevent errors while maintaining data structure.

**Missing Data Logging** tracks which fields are commonly missing, helping identify data quality issues at the source.

### Data Quality Issues

Common data quality issues are handled during transformation:

**Invalid Date Formats** are caught and logged. Some sources might use non-standard date formats that need conversion.

**Type Mismatches** are detected and handled. A field expected to be a list might contain a string, requiring conversion.

**Invalid Values** are caught by validation. Confidence scores outside 0-1 range, invalid URLs, etc. are flagged.

**Data Cleaning** happens during transformation. Malformed data is cleaned when possible, or logged when not.

---

## Output Format: FAIR4ML JSON

Transformed data is saved as FAIR4ML JSON files, providing a consistent format for downstream processing:

### File Structure

Normalized data is organized in run folders, just like raw data:

```
/data/normalized/<source>/
└── <timestamp>_<uuid>/
    ├── mlmodels.json          # Models in FAIR4ML
    ├── datasets.json          # Datasets in FAIR4ML
    ├── papers.json            # Papers in FAIR4ML
    └── <entity>_transformation_errors.json  # Validation errors
```

### FAIR4ML Format

Each file contains an array of FAIR4ML entities:

```json
{
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "google",
  "mlTask": ["fill-mask"],
  "modelCategory": ["transformer"],
  "keywords": ["bert", "nlp", "transformer"],
  "license": "apache-2.0",
  "extraction_metadata": {
    "identifier": {
      "extraction_method": "Parsed_from_HF_dataset",
      "confidence": 1.0
    }
  }
}
```

This format is consistent across all sources, enabling unified processing.

---

## Key Takeaways

Transformation is the bridge between diverse source formats and a unified FAIR4ML schema. It enables comparison across platforms, ensures data quality through validation, enriches data with computed fields and resolved references, handles errors gracefully to maximize success, and produces standardized output that downstream systems can rely on.

Understanding transformation helps you debug issues, extend the system to new sources, and appreciate how diverse data becomes unified knowledge.

---

## Next Steps

- Learn about [HuggingFace Transformation](huggingface.md) - Detailed guide to the most comprehensive transformer
- Check [Adding a Transformer](adding-transformer.md) - How to add transformers for new sources
- Explore [Loaders](../loaders/overview.md) - How normalized data is loaded into storage systems
