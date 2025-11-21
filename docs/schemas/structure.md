# Schema Structure: Implementing FAIR4ML with Pydantic

This document explains how we implement the FAIR4ML schema in MLentory using Pydantic, a powerful Python library for data validation. Understanding this implementation helps you work with the codebase, debug transformation issues, and extend the schema as needed.

---

## Why Pydantic? The Foundation of Type Safety

When building data pipelines, one of the biggest challenges is ensuring data quality. You might receive data from external APIs, transform it through multiple stages, and load it into databases—and at any point, the data could be malformed, missing required fields, or have incorrect types. Catching these issues early saves hours of debugging later.

**Pydantic** solves this problem by providing data validation using Python type annotations. Instead of writing manual validation code, you define what your data should look like using Python types, and Pydantic automatically validates that incoming data matches those expectations.

Think of Pydantic as a contract system: you define a contract (the model) that specifies what data is acceptable, and Pydantic enforces that contract. If data doesn't match, you get clear error messages explaining what's wrong. If data does match, you get a validated object that you can trust.

### The Benefits in Practice

**Type Safety** means that if you define a field as `str`, Pydantic will reject anything that isn't a string. This catches errors at runtime, before they cause problems downstream. For example, if a transformation accidentally produces a number where a string is expected, Pydantic will catch it immediately.

**Automatic Validation** means you don't have to write boilerplate code to check if fields exist, if types are correct, or if values are in valid ranges. Pydantic does this automatically based on your type annotations.

**Documentation** is built-in because type hints serve as living documentation. When you see `name: str`, you immediately know that `name` must be a string. This makes code self-documenting and easier to understand.

**JSON Serialization** is seamless because Pydantic models can be easily converted to and from JSON. This is crucial for our pipeline, where data flows through JSON files at various stages.

**IDE Support** means that modern IDEs can provide autocomplete, type checking, and error detection based on your Pydantic models. This makes development faster and less error-prone.

Here's a simple example that demonstrates these benefits:

```python
from pydantic import BaseModel, Field

class MLModel(BaseModel):
    name: str  # Required field - must be a string
    description: Optional[str] = None  # Optional field - can be None
    
# Pydantic automatically validates
model = MLModel(name="BERT")  # ✅ Valid - creates the model
model = MLModel()  # ❌ Error: name is required
model = MLModel(name=123)  # ❌ Error: name must be a string
```

Notice how Pydantic catches errors automatically. You don't need to write `if not name: raise ValueError()`—Pydantic does it for you.

---

## Our Pydantic Models: The Building Blocks

In MLentory, we use Pydantic models to represent FAIR4ML entities. These models serve multiple purposes: they validate data, provide type safety, enable JSON serialization, and serve as documentation.

### The MLModel Model: Our Primary Entity

The **MLModel** model (located in `schemas/fair4ml/mlmodel.py`) is the most important model in our system. It represents a FAIR4ML MLModel entity and implements the FAIR4ML v0.1.0 specification.

![Pydantic Model Structure](images/pydantic-model-structure.png)
*Figure 1: Pydantic models provide structure, validation, and type safety for FAIR4ML data throughout the pipeline.*

What makes this model special is how it balances multiple requirements:

**FAIR4ML Compliance**: The model implements all properties defined in the FAIR4ML v0.1.0 specification, ensuring our data conforms to the standard.

**JSON-LD Compatibility**: Fields use aliases that match JSON-LD property names (like `https://schema.org/identifier`), enabling seamless conversion to and from JSON-LD format.

**Validation Rules**: Each field has appropriate validation—required fields must be present, optional fields have defaults, and types are strictly enforced.

**MLentory Extensions**: The model includes MLentory-specific extensions like `extraction_metadata` that track how data was extracted, which is crucial for debugging and provenance.

Here's how you'd use it in practice:

```python
from schemas.fair4ml import MLModel

# Create a model with required fields
model = MLModel(
    identifier=["https://huggingface.co/bert-base-uncased"],
    name="bert-base-uncased",
    url="https://huggingface.co/bert-base-uncased",
    mlTask=["fill-mask"]
)

# Access fields
print(model.name)  # "bert-base-uncased"
print(model.mlTask)  # ["fill-mask"]

# Pydantic validates automatically
try:
    invalid_model = MLModel(name=123)  # Wrong type
except ValidationError as e:
    print(e)  # Clear error message
```

### ExtractionMetadata: Tracking Provenance

The **ExtractionMetadata** model is a MLentory-specific extension that tracks how each field was extracted. This might seem like overhead, but it's incredibly valuable for:

- **Debugging**: When a field has an unexpected value, you can see exactly how it was extracted
- **Data Quality**: Confidence scores help you understand how reliable each field is
- **Provenance**: You can trace data back to its source, which is crucial for research reproducibility
- **Improvement**: Understanding extraction methods helps you improve transformation logic

The structure is simple but powerful:

```python
class ExtractionMetadata(BaseModel):
    extraction_method: str  # How it was extracted (e.g., "Parsed_from_HF_dataset")
    confidence: float = 1.0  # Confidence score from 0.0 to 1.0
    source_field: Optional[str] = None  # Original field name in source data
    notes: Optional[str] = None  # Additional context
```

When you use it, you attach metadata to specific fields:

```python
model.extraction_metadata = {
    "identifier": ExtractionMetadata(
        extraction_method="Parsed_from_HF_dataset",
        confidence=1.0,  # High confidence - direct from source
        source_field="modelId"  # Original field name
    ),
    "mlTask": ExtractionMetadata(
        extraction_method="Inferred_from_tags",
        confidence=0.8,  # Lower confidence - inferred, not explicit
        notes="Inferred from pipeline_tag field"
    )
}
```

This metadata travels with the data through the pipeline, providing a complete audit trail.

### Related Entity Models: The Ecosystem

MLentory also includes models for related entities that connect to ML models:

**ScholarlyArticle** represents research papers that describe or cite models. It uses Schema.org's ScholarlyArticle vocabulary, ensuring compatibility with other systems that track academic publications.

**CroissantDataset** represents training and evaluation datasets. It uses the Croissant ML schema, which is specifically designed for ML datasets and provides rich metadata about data structure, licensing, and usage.

**Language**, **DefinedTerm**, and **CreativeWork** represent languages, ML tasks, and licenses respectively. These use standard Schema.org types, ensuring broad compatibility.

These models work together to create a rich, interconnected representation of the ML ecosystem. A model links to its datasets, papers, and other entities, creating a knowledge graph that enables powerful queries and discovery.

---

## Understanding Field Types: The Language of Data

Fields in Pydantic models use Python type annotations to specify what kind of data they accept. Understanding these types is crucial for working with the models effectively.

### Required vs Optional: Making Fields Flexible

The distinction between required and optional fields is fundamental to data modeling. Required fields must always be present—they're the essential information that defines an entity. Optional fields can be missing—they provide additional context but aren't strictly necessary.

In our MLModel, `name` is required because you can't have a model without a name. But `description` is optional because while it's helpful, a model can exist without a detailed description.

Here's how this works in practice:

```python
class MLModel(BaseModel):
    name: str  # Required - no default value means it must be provided
    description: Optional[str] = None  # Optional - has a default (None)
    keywords: List[str] = Field(default_factory=list)  # Optional - defaults to empty list
```

When you create a model:
- You **must** provide `name` (it's required)
- You **can** omit `description` (it will default to `None`)
- You **can** omit `keywords` (it will default to an empty list)

This design balances strictness (ensuring essential data is present) with flexibility (allowing partial data when full information isn't available).

### Common Field Types: Building Complex Structures

Pydantic supports all Python types, but some are particularly common in our models:

**Strings** (`str`) are used for text data like names, descriptions, and URLs. They're simple but crucial—most human-readable information is stored as strings.

**Lists** (`List[str]`, `List[int]`, etc.) are used when a field can have multiple values. For example, `identifier` is a list because a model might have multiple identifiers (HuggingFace URL, arXiv URL, GitHub URL). Lists are also used for `keywords`, `mlTask`, and other multi-value fields.

**Datetime objects** (`datetime`) are used for temporal information like creation dates and publication dates. Pydantic automatically parses ISO 8601 date strings into Python datetime objects, making date handling seamless.

**Dictionaries** (`Dict[str, Any]`) are used for flexible key-value structures. Our `metrics` field uses a dictionary to store platform-specific metrics like download counts and likes, which vary by platform.

**Nested models** allow complex structures. For example, `extraction_metadata` is a dictionary where values are `ExtractionMetadata` objects, creating a nested structure that tracks provenance for each field.

Here are examples of each:

```python
# String
name: str  # Simple text

# List
identifier: List[str] = Field(default_factory=list)  # Multiple values
mlTask: Optional[List[str]] = Field(default_factory=list)  # Optional list

# Datetime
from datetime import datetime
dateCreated: Optional[datetime] = None  # Parsed from ISO 8601 strings

# Dictionary
from typing import Dict, Any
metrics: Dict[str, Any] = Field(default_factory=dict)  # Flexible key-value pairs

# Nested model
extraction_metadata: Dict[str, ExtractionMetadata] = Field(default_factory=dict)
```

Each type serves a specific purpose, and choosing the right type makes the model more expressive and easier to work with.

---

## Validation Rules: Ensuring Data Quality

Validation is where Pydantic really shines. Instead of writing manual checks, you define rules using type annotations and Field constraints, and Pydantic enforces them automatically.

### Automatic Type Validation

The most basic validation is type checking. If you define a field as `str`, Pydantic will reject anything that isn't a string:

```python
model = MLModel(
    name="BERT",  # ✅ String - valid
    identifier=123  # ❌ Integer - invalid, must be List[str]
)
```

Pydantic will raise a `ValidationError` with a clear message explaining what went wrong. This catches errors early, before they propagate through the pipeline and cause mysterious failures later.

### Field Constraints: Beyond Types

Sometimes type checking isn't enough. You might need to ensure a string isn't empty, a number is in a valid range, or a list has at least one item. Pydantic's `Field` function lets you specify these constraints:

**String length constraints** ensure text fields aren't too short or too long:

```python
name: str = Field(..., min_length=1, max_length=255)
```

The `...` means the field is required. `min_length=1` ensures the name isn't empty, and `max_length=255` prevents extremely long names that might cause database issues.

**Numeric range constraints** ensure numbers are in valid ranges:

```python
confidence: float = Field(default=1.0, ge=0.0, le=1.0)
```

`ge=0.0` means "greater than or equal to 0.0", and `le=1.0` means "less than or equal to 1.0". This ensures confidence scores are always between 0 and 1, which makes sense semantically.

**List constraints** ensure lists meet requirements:

```python
identifier: List[str] = Field(..., min_items=1)
```

`min_items=1` ensures at least one identifier is provided, which is required by FAIR4ML.

### Custom Validators: Complex Logic

Sometimes you need validation logic that's more complex than simple constraints. Pydantic's `field_validator` decorator lets you write custom validation functions:

```python
from pydantic import field_validator

@field_validator('identifier')
@classmethod
def validate_identifier(cls, v):
    if not v:
        raise ValueError('At least one identifier is required')
    # Could add more complex checks here
    # e.g., ensure all identifiers are valid URLs
    return v
```

Custom validators run after type checking and constraint validation, allowing you to implement domain-specific rules that can't be expressed with simple constraints.

---

## Field Aliases: Bridging Python and JSON-LD

One of the most powerful features of our Pydantic models is field aliases. These allow fields to be accessed by multiple names, which is crucial for JSON-LD compatibility.

### Why Aliases Matter

In Python, we want field names to be Pythonic: `identifier`, `name`, `mlTask`. But in JSON-LD, we need property names to be full IRIs: `https://schema.org/identifier`, `https://schema.org/name`, `https://w3id.org/fair4ml/mlTask`.

Aliases let us have both. We define fields with Python-friendly names, but also specify aliases that match JSON-LD property names:

```python
identifier: List[str] = Field(
    default_factory=list,
    alias="https://schema.org/identifier"
)
```

Now the field can be accessed using either name:
- Python code uses `model.identifier`
- JSON-LD uses `"https://schema.org/identifier"`

### Populate by Name: The Best of Both Worlds

The `populate_by_name=True` configuration option makes this even more powerful. It allows models to be created using either the Python field name or the alias:

```python
# Using Python field name (normal Python code)
model = MLModel(
    identifier=["https://example.com/model"],
    name="My Model"
)

# Using JSON-LD alias (from JSON-LD data)
model = MLModel(
    **{"https://schema.org/identifier": ["https://example.com/model"],
       "https://schema.org/name": "My Model"}
)
```

This flexibility means:
- **Python developers** can use familiar, Pythonic names
- **JSON-LD systems** can use standard property IRIs
- **Data conversion** is seamless in both directions
- **Compatibility** is maintained with semantic web standards

![Field Aliases Diagram](images/field-aliases.png)
*Figure 2: Field aliases enable seamless conversion between Python-friendly names and JSON-LD property IRIs, maintaining compatibility with both programming and semantic web standards.*

---

## JSON Serialization: Moving Data Through the Pipeline

Our pipeline moves data through JSON files at multiple stages. Pydantic makes this seamless by providing easy conversion to and from JSON.

### Converting to JSON

When you need to save a model to a JSON file or send it over an API, Pydantic provides simple methods:

**Standard JSON** uses Python field names, which is convenient for internal use:

```python
model = MLModel(name="BERT", identifier=["https://example.com/bert"])
json_str = model.model_dump_json()
# Result: {"name": "BERT", "identifier": ["https://example.com/bert"], ...}
```

**JSON-LD format** uses aliases (property IRIs), which is required for semantic web compatibility:

```python
json_ld = model.model_dump(by_alias=True)
# Result: {"https://schema.org/name": "BERT", 
#          "https://schema.org/identifier": ["https://example.com/bert"], ...}
```

The `by_alias=True` parameter tells Pydantic to use aliases instead of Python field names, producing JSON-LD compatible output.

### Converting from JSON

Reading JSON back into models is equally simple:

**Standard JSON** works directly:

```python
data = {"name": "BERT", "identifier": ["https://example.com/bert"]}
model = MLModel(**data)  # Creates model from JSON
```

**JSON-LD** also works because of `populate_by_name=True`:

```python
data = {
    "https://schema.org/name": "BERT",
    "https://schema.org/identifier": ["https://example.com/bert"]
}
model = MLModel(**data)  # Also works! Aliases are recognized
```

This bidirectional compatibility means you can read data from semantic web systems and write data for semantic web systems, all while using Python-friendly code internally.

---

## Schema Evolution: Growing Without Breaking

As FAIR4ML evolves and our needs change, we need to update our models. Schema evolution is the process of changing models while maintaining compatibility with existing data.

### Adding New Fields: Backward Compatible Changes

The safest way to evolve a schema is to add optional fields with defaults. This is backward compatible because:

- Existing data (without the new field) still validates
- New code can use the new field
- Old code continues to work (it just ignores the new field)

For example, if we add a new `hasCO2eEmissions` field:

```python
# New field added
hasCO2eEmissions: Optional[str] = None  # Optional, backward compatible
```

Existing JSON files without this field will still validate (the field will just be `None`). New JSON files can include this field. This allows gradual migration without breaking existing code or data.

### Removing Fields: Breaking Changes

Removing fields is more dangerous and requires careful planning:

**Removing required fields** breaks existing data because that data won't validate anymore. This should only happen in major version updates with a deprecation period.

**Removing optional fields** is usually safe because existing data can continue without them. However, you should still deprecate them first to give users time to migrate.

**Best practice** for removing fields:

1. **Deprecate** the field (mark it as deprecated in documentation)
2. **Keep it** for several versions to allow migration
3. **Remove it** in a major version update
4. **Document** the change clearly in release notes

This process gives users time to adapt and prevents sudden breakage.

---

## Error Handling: Graceful Failures

When validation fails, Pydantic raises `ValidationError` exceptions. Understanding how to handle these errors is crucial for building robust pipelines.

### Understanding Validation Errors

Pydantic's `ValidationError` provides detailed information about what went wrong:

```python
from pydantic import ValidationError

try:
    model = MLModel()  # Missing required fields
except ValidationError as e:
    print(e.errors())
    # [
    #   {
    #     'type': 'missing',
    #     'loc': ('name',),
    #     'msg': 'Field required',
    #     'input': {}
    #   }
    # ]
```

Each error in the list describes one validation problem:
- **`type`**: The kind of error (missing, type_error, value_error, etc.)
- **`loc`**: The location of the error (which field, or nested path)
- **`msg`**: A human-readable error message
- **`input`**: The invalid input that caused the error

This detailed information makes debugging much easier.

### Error Handling in Our Pipeline

In MLentory's transformation stage, we handle validation errors gracefully:

```python
try:
    model = MLModel(**transformed_data)
    # Success - model is valid
except ValidationError as e:
    # Failure - log error but continue processing
    logger.error(f"Validation failed for {model_id}: {e}")
    save_validation_errors(model_id, e.errors())
    # Continue with next model - don't stop entire pipeline
```

This approach ensures that:
- **One bad model** doesn't stop the entire pipeline
- **Errors are logged** for later investigation
- **Partial results** are still useful
- **Data quality issues** are tracked and can be fixed

This is crucial in production systems where data quality varies and you need to process as much as possible while tracking problems.

---

## Configuration: Tuning Model Behavior

Pydantic models can be configured to behave differently based on your needs. Our models use specific configurations to support JSON-LD compatibility and provide good defaults.

### Model Configuration

Our MLModel uses this configuration:

```python
model_config = ConfigDict(
    populate_by_name=True,  # Allow both Python name and alias
    json_schema_extra={
        "example": {
            "identifier": "https://huggingface.co/bert-base-uncased",
            "name": "bert-base-uncased",
            # ... example values for documentation
        }
    }
)
```

**`populate_by_name=True`** is the key setting that enables alias support. Without this, you could only use Python field names. With it, you can use either Python names or aliases.

**`json_schema_extra`** provides example values that are used when generating JSON Schema documentation. This helps users understand what valid data looks like.

### Available Configuration Options

Pydantic offers many configuration options:

- **`populate_by_name`**: Allow both field names and aliases (we use this)
- **`validate_assignment`**: Validate when fields are assigned (not just on creation)
- **`use_enum_values`**: Use enum values instead of enum objects
- **`json_encoders`**: Custom encoders for specific types
- **`json_schema_extra`**: Example values for documentation (we use this)

We keep our configuration minimal to maintain simplicity and performance, but these options are available if needed.

---

## Best Practices: Writing Maintainable Models

Based on our experience building and maintaining these models, here are some best practices:

### Use Type Hints Consistently

Type hints aren't just for Pydantic—they're documentation that helps everyone understand the code:

```python
# Good: Clear type information
name: str
description: Optional[str] = None

# Bad: No type information
name = None  # What type is this? Who knows!
```

### Provide Sensible Defaults

Optional fields should have defaults that make sense:

```python
# Good: Empty list is a sensible default
keywords: List[str] = Field(default_factory=list)

# Bad: Required when it should be optional
keywords: List[str]  # Forces users to always provide a list, even if empty
```

### Document Fields with Descriptions

Field descriptions help users understand what each field means:

```python
# Good: Self-documenting
name: str = Field(description="Human-readable name of the model")

# Bad: Requires reading code or external docs
name: str  # What is this? What format? What's required?
```

### Validate Early and Often

Don't defer validation—validate as soon as you have data:

```python
# Good: Validate immediately
model = MLModel(**data)  # Catches errors early

# Bad: Defer validation, hope for the best
model_data = data  # No validation, errors surface later
```

These practices make models more maintainable, easier to understand, and less error-prone.

---

## Key Takeaways

Pydantic provides a powerful foundation for implementing FAIR4ML in MLentory:

- **Type safety** catches errors before they cause problems
- **Field aliases** enable JSON-LD compatibility while keeping Python code clean
- **Automatic validation** ensures data quality throughout the pipeline
- **JSON serialization** makes data movement seamless
- **Error handling** allows graceful failures and partial success
- **Schema evolution** enables growth without breaking existing code

Understanding these concepts helps you work effectively with the codebase, debug issues, and extend the system as needs evolve.

---

## Next Steps

Now that you understand how we implement FAIR4ML with Pydantic:

- See [FAIR4ML Schema Reference](fair4ml.md) - Complete property reference
- Explore [Source Schemas](source-schemas.md) - How source data maps to FAIR4ML
- Check [Transformers](../transformers/overview.md) - How we use Pydantic in transformation
- Review [Schemas API](../api/schemas.md) - Complete API reference for developers

---

## Resources

- **Pydantic Documentation:** [https://docs.pydantic.dev/](https://docs.pydantic.dev/) - Comprehensive guide to Pydantic
- **Python Type Hints:** [https://docs.python.org/3/library/typing.html](https://docs.python.org/3/library/typing.html) - Official type hints documentation
- **JSON Schema:** [https://json-schema.org/](https://json-schema.org/) - JSON Schema specification
