"""
FAIR4ML MLModel schema definition.

Based on FAIR4ML 0.1.0 specification:
https://rda-fair4ml.github.io/FAIR4ML-schema/release/0.1.0/index.html

This module defines Pydantic models for the fair4ml:MLModel entity, using
field names aligned with FAIR4ML property names (without namespace prefixes)
to facilitate future JSON-LD conversion.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field
from pydantic import ConfigDict


class ExtractionMetadata(BaseModel):
    """
    Metadata about how a field was extracted/derived.
    
    This is a non-FAIR extension for traceability and provenance tracking.
    """
    extraction_method: str = Field(
        description="Method used to extract this field (e.g., 'Parsed_from_HF_dataset', 'Inferred_from_tags')"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this extraction (0.0 to 1.0)"
    )
    source_field: Optional[str] = Field(
        default=None,
        description="Original source field name from raw data"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes about the extraction"
    )


class MLModel(BaseModel):
    """
    FAIR4ML MLModel entity.
    
    Represents a trained machine learning model with metadata aligned to the
    FAIR4ML 0.1.0 specification. Field names use FAIR4ML local names (without
    namespace prefixes) for easier JSON-LD conversion later.
    
    Core identification and descriptive fields use schema.org properties,
    while ML-specific fields use fair4ml properties.
    """
    
    # ========== Core Identification (schema.org) ==========
    identifier: List[str] = Field(
        default_factory=list,
        description="Unique identifier for the model (typically the HuggingFace URL)",
        alias="https://schema.org/identifier"
    )
    name: str = Field(
        description="Human-readable name of the model", 
        alias="https://schema.org/name"
    )
    url: str = Field(
        description="Primary URL where the model can be accessed",
        alias="https://schema.org/url"
    )
    
    # ========== Authorship & Provenance (schema.org + fair4ml) ==========
    author: Optional[str] = Field(
        default=None,
        description="Author(s) of the model (schema:author)",
        alias="https://schema.org/author"
    )
    sharedBy: Optional[str] = Field(
        default=None,
        description="Person or Organization who shared the model online (fair4ml:sharedBy)",
        alias="https://w3id.org/fair4ml/sharedBy"
    )
    
    # ========== Temporal Information (schema.org) ==========
    dateCreated: Optional[datetime] = Field(
        default=None,
        description="Date the model was created (schema:dateCreated)",
        alias="https://schema.org/dateCreated"
    )
    dateModified: Optional[datetime] = Field(
        default=None,
        description="Date the model was last modified (schema:dateModified)",
        alias="https://schema.org/dateModified"
    )
    datePublished: Optional[datetime] = Field(
        default=None,
        description="Date the model was published (schema:datePublished)",
        alias="https://schema.org/datePublished"
    )
    
    # ========== Description & Documentation (schema.org + codemeta) ==========
    description: Optional[str] = Field(
        default=None,
        description="Full description of the model (schema:description)",
        alias="https://schema.org/description"
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Keywords or tags describing the model (schema:keywords)",
        alias="https://schema.org/keywords"
    )
    inLanguage: List[str] = Field(
        default_factory=list,
        description="Natural language(s) the model works with (schema:inLanguage)",
        alias="https://schema.org/inLanguage"
    )
    license: Optional[str] = Field(
        default=None,
        description="License under which the model is distributed (schema:license)",
        alias="https://schema.org/license"
    )
    
    referencePublication: Optional[List[str]] = Field(
        default_factory=list,
        description="Reference publication for the model (schema:referencePublication)",
        alias="https://schema.org/referencePublication"
    )
    
    # ========== ML Task & Category (fair4ml) ==========
    mlTask: Optional[list[str]] = Field(
        default_factory=list,
        description="ML task addressed by this model, e.g., 'text-generation', 'image-classification' (fair4ml:mlTask)",
        alias="https://w3id.org/fair4ml/mlTask"
    )
    modelCategory: Optional[List[str]] = Field(
        default_factory=list,
        description="Category/architecture of the model, e.g., 'transformer', 'CNN', 'LLM' (fair4ml:modelCategory)",
        alias="https://w3id.org/fair4ml/modelCategory"
    )
    
    # ========== Model Lineage (fair4ml) ==========
    fineTunedFrom: Optional[List[str]] = Field(
        default_factory=list,
        description="Identifier of the base model this was fine-tuned from (fair4ml:fineTunedFrom)",
        alias="https://w3id.org/fair4ml/fineTunedFrom"
    )
    
    # ========== Usage & Code (fair4ml) ==========
    intendedUse: Optional[str] = Field(
        default=None,
        description="Intended use case for the model (fair4ml:intendedUse)",        
        alias="https://w3id.org/fair4ml/intendedUse"
    )
    usageInstructions: Optional[str] = Field(
        default=None,
        description="Instructions on how to use the model (fair4ml:usageInstructions)",
        alias="https://w3id.org/fair4ml/usageInstructions"
    )
    codeSampleSnippet: Optional[str] = Field(
        default=None,
        description="Code snippet demonstrating model usage (fair4ml:codeSampleSnippet)",
        alias="https://w3id.org/fair4ml/codeSampleSnippet"
    )
    
    # ========== Ethics & Risks (fair4ml) ==========
    modelRisksBiasLimitations: Optional[str] = Field(
        default=None,
        description="Description of model risks, biases, and limitations (fair4ml:modelRisksBiasLimitations)",
        alias="https://w3id.org/fair4ml/modelRisksBiasLimitations"
    )
    ethicalSocial: Optional[str] = Field(
        default=None,
        description="Ethical and social considerations (fair4ml:ethicalSocial)",
        alias="https://w3id.org/fair4ml/ethicalSocial"
    )
    legal: Optional[str] = Field(
        default=None,
        description="Legal considerations (fair4ml:legal)",
        alias="https://w3id.org/fair4ml/legal"
    )
    
    # ========== Training & Evaluation Data (fair4ml) ==========
    trainedOn: List[str] = Field(
        default_factory=list,
        description="Dataset(s) used for training (fair4ml:trainedOn)",
        alias="https://w3id.org/fair4ml/trainedOn"
    )
    testedOn: List[str] = Field(
        default_factory=list,
        description="Dataset(s) used for testing (fair4ml:testedOn)",
        alias="https://w3id.org/fair4ml/testedOn"
    )
    validatedOn: List[str] = Field(
        default_factory=list,
        description="Dataset(s) used for validation (fair4ml:validatedOn)",
        alias="https://w3id.org/fair4ml/validatedOn"
    )
    evaluatedOn: List[str] = Field(
        default_factory=list,
        description="Dataset(s) used for evaluation/benchmarking (fair4ml:evaluatedOn)",
        alias="https://w3id.org/fair4ml/evaluatedOn"
    )
    evaluationMetrics: List[str] = Field(
        default_factory=list,
        description="Evaluation metrics and their values (fair4ml:evaluationMetrics)",
        alias="https://w3id.org/fair4ml/evaluationMetrics"
    )
    
    # ========== Additional URLs (schema.org + codemeta) ==========
    discussionUrl: Optional[str] = Field(
        default=None,
        description="URL for discussions about the model (schema:discussionUrl)",
        alias="https://schema.org/discussionUrl"
    )
    archivedAt: Optional[str] = Field(
        default=None,
        description="Archive URL for the model (schema:archivedAt)",
        alias="https://schema.org/archivedAt"
    )
    readme: Optional[str] = Field(
        default=None,
        description="URL to the README file (codemeta:readme)",
        alias="https://w3id.org/codemeta/readme"
    )
    issueTracker: Optional[str] = Field(
        default=None,
        description="URL to the issue tracker (codemeta:issueTracker)",
        alias="https://w3id.org/codemeta/issueTracker"
    )
    
    # ========== Technical Information (schema.org) ==========
    memoryRequirements: Optional[str] = Field(
        default=None,
        description="Memory/storage requirements for the model (schema:memoryRequirements)",
        alias="https://schema.org/memoryRequirements"
    )
    
    # ========== Environmental Impact (fair4ml) ==========
    hasCO2eEmissions: Optional[str] = Field(
        default=None,
        description="CO2 equivalent emissions from training (fair4ml:hasCO2eEmissions)",
        alias="https://w3id.org/fair4ml/hasCO2eEmissions"
    )
    
    # ========== Platform-Specific Metrics (non-FAIR extension) ==========
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Platform-specific metrics (e.g., downloads, likes) - non-FAIR extension for context",
        alias="https://w3id.org/fair4ml/metrics"
    )
    
    # ========== Extraction Metadata (non-FAIR extension) ==========
    extraction_metadata: Dict[str, ExtractionMetadata] = Field(
        default_factory=dict,
        description="Metadata about how each field was extracted - non-FAIR extension for provenance",
        alias="https://w3id.org/mlentory/mlentory_graph/meta/"
    )

    # Allow populating fields by their Python names even when aliases are defined
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "identifier": "https://huggingface.co/bert-base-uncased",
                "name": "bert-base-uncased",
                "url": "https://huggingface.co/bert-base-uncased",
                "author": "google",
                "dateCreated": "2020-01-01T00:00:00Z",
                "keywords": ["bert", "transformer", "nlp"],
                "mlTask": ["fill-mask", "text-classification"],
                "modelCategory": ["transformer", "bert"],
                "metrics": {"downloads": 1000000, "likes": 500}
            }
        },
    )
        

