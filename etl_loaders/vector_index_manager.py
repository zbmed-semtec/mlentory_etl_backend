"""
Vector Index Manager for ETL Backend.

This module provides functionality to add vector embeddings to existing Elasticsearch indices.
Vectors are appended as additional columns to pre-existing indices per data source (HF, OpenML, AI4Life).
"""

from __future__ import annotations

import os
import time
import logging
from typing import Dict, Any, List, Optional

try:
    from sentence_transformers import SentenceTransformer
    from huggingface_hub import login
except ImportError:
    SentenceTransformer = None
    login = None

from etl_loaders.elasticsearch_store import ElasticsearchConfig, create_elasticsearch_client

logger = logging.getLogger(__name__)


def _extracted_data_from_indexed_model(model_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build extracted_data for searchable text from indexed model fields."""
    extracted: Dict[str, Any] = {}

    domain = model_data.get("domain")
    if domain:
        extracted["domain"] = domain

    model_category = model_data.get("model_category") or model_data.get("architecture")
    if model_category:
        if isinstance(model_category, list):
            extracted["architecture"] = ", ".join(str(c) for c in model_category if c)
        else:
            extracted["architecture"] = str(model_category)

    adaption = model_data.get("adaption_techniques") or model_data.get("trainingType")
    if adaption:
        extracted["trainingType"] = adaption

    data_splits = model_data.get("data_splits")
    if data_splits:
        extracted["data_splits"] = data_splits

    return extracted


_MISSING_TEXT = frozenset({"", "information not found", "unknown", "none", "null"})


def _field_text(value: Any) -> str:
    """Join a metadata value into one line, dropping empty placeholders."""
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [_field_text(item) for item in value]
        return ", ".join(part for part in parts if part)
    text = str(value).strip()
    if text.lower() in _MISSING_TEXT:
        return ""
    return text


def _searchable_card_fields(
    model_data: Dict[str, Any],
    extracted_data: Optional[Dict[str, Any]] = None,
) -> List[tuple]:
    """Non-empty card fields in index order: (label, value).

    Shared by the labeled BGE-M3 card and the values-only SPLADE card so the
    two texts cannot pick up different fields.
    """
    extracted = extracted_data or {}
    datasets: List[str] = []
    seen_datasets = set()
    for source in (
        model_data.get("datasets"),
        model_data.get("dataset"),
        extracted.get("dataset"),
    ):
        for item in source if isinstance(source, list) else [source]:
            text = _field_text(item)
            key = text.lower()
            if text and key not in seen_datasets:
                seen_datasets.add(key)
                datasets.append(text)

    fields = [
        ("name", model_data.get("name")),
        ("author", model_data.get("sharedBy") or model_data.get("shared_by")),
        ("task", model_data.get("mlTask") or model_data.get("ml_task") or model_data.get("ml_tasks")),
        ("keywords", model_data.get("keywords")),
        ("datasets", datasets),
        ("domain", extracted.get("domain") or model_data.get("domain")),
        (
            "architecture",
            extracted.get("architecture")
            or model_data.get("architecture")
            or model_data.get("model_category"),
        ),
        ("modalities", extracted.get("modalities") or model_data.get("modalities")),
        ("description", model_data.get("description")),
    ]
    pairs = []
    for label, value in fields:
        text = _field_text(value)
        if text:
            pairs.append((label, text))
    return pairs


def build_improved_searchable_text(
    model_data: Dict[str, Any],
    extracted_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Build label:value text for the improved embedding.

    Includes the fields people search for. License, version, parameter count,
    data splits, and training type stay out of the vector so they can remain
    filters. The description is not shortened here; the embedding model applies
    its own token window.
    """
    return "\n".join(
        f"{label}: {text}" for label, text in _searchable_card_fields(model_data, extracted_data)
    )


def _truncate_to_tokens(tokenizer, text: str, max_tokens: int) -> str:
    """Cut text to ``max_tokens`` wordpieces. Short text is returned unchanged."""
    if not text or max_tokens <= 0:
        return ""
    if len(text) <= max_tokens:
        return text
    token_ids = tokenizer.encode(
        text,
        add_special_tokens=False,
        truncation=True,
        max_length=max_tokens,
    )
    if len(token_ids) < max_tokens:
        return text
    return tokenizer.decode(token_ids, skip_special_tokens=True).strip()


def build_splade_searchable_text(
    model_data: Dict[str, Any],
    extracted_data: Optional[Dict[str, Any]] = None,
    *,
    description_max_tokens: Optional[int] = None,
    tokenizer=None,
) -> str:
    """Values-only card for SPLADE, same fields and order as the BGE-M3 card.

    Fields are joined with ``". "``. Empty fields are omitted, so a missing
    value does not leave an empty separator. When ``description_max_tokens``
    is set, only the description is cut to that many wordpieces.
    """
    values: List[str] = []
    for label, text in _searchable_card_fields(model_data, extracted_data):
        if label == "description" and description_max_tokens and tokenizer is not None:
            text = _truncate_to_tokens(tokenizer, text, description_max_tokens)
        if text:
            values.append(text)
    return ". ".join(values)


class VectorIndexManager:
    """
    Manager for adding vector embeddings to existing Elasticsearch indices.
    
    This class handles:
    - Adding vector field mappings to existing indices
    - Generating embeddings for models using integrated embedding model
    - Updating documents in-place with vector fields
    
    The embedding model is initialized directly in this class (no external dependency).
    """
    
    # Default embedding configuration
    DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
    DEFAULT_EMBEDDING_DIMENSION = 768  # MPNet default
    DEFAULT_MAX_SEQUENCE_LENGTH = 512
    
    def __init__(self, es_client, index_name: str, logger_instance=None):
        """
        Initialize the vector index manager.
        
        Args:
            es_client: Elasticsearch client instance
            index_name: Name of the Elasticsearch index to update
            logger_instance: Optional logger instance
        """
        self.es = es_client
        self.index_name = index_name
        self.logger = logger_instance or logger
        
        # Initialize embedding model directly
        self.model = None
        self.embedding_model = self.DEFAULT_EMBEDDING_MODEL
        self.embedding_dimension = self.DEFAULT_EMBEDDING_DIMENSION
        self.max_sequence_length = self.DEFAULT_MAX_SEQUENCE_LENGTH
        self.device = self._resolve_device()
        self._load_embedding_model()
    
    def _resolve_device(self) -> str:
        """Resolve the device to use for embeddings (CUDA if available, else CPU)."""
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    
    def _load_embedding_model(self):
        """Load the sentence transformer model for generating embeddings."""
        if not SentenceTransformer:
            self.logger.warning("sentence-transformers not available. Vector indexing disabled.")
            return
        
        # Authenticate with HuggingFace if token is provided
        self._authenticate_huggingface()
        
        # Set PyTorch environment variables
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'
        
        try:
            start_time = time.time()
            token = os.getenv('HUGGINGFACE_HUB_TOKEN') or os.getenv('HF_TOKEN')
            
            # Load the model
            try:
                # Handle special cases for certain models
                if "google/embeddinggemma" in self.embedding_model:
                    import torch
                    os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'
                    torch.backends.cudnn.enabled = False
                
                self.model = SentenceTransformer(
                    self.embedding_model,
                    device=self.device,
                    trust_remote_code=True,
                    token=token if token else None
                )
            except Exception as meta_error:
                if "meta tensor" in str(meta_error).lower():
                    self.logger.warning("Meta tensor issue detected, trying alternative loading method...")
                    import torch
                    torch.backends.cudnn.enabled = False
                    self.model = SentenceTransformer(
                        self.embedding_model,
                        device=self.device,
                        trust_remote_code=True,
                        use_auth_token=False
                    )
                else:
                    raise meta_error
            
            load_time = time.time() - start_time
            
            # Validate the model
            self._validate_model()
            
            self.logger.info(f"Embedding model initialized: {self.embedding_model} (loaded in {load_time:.2f}s)")
            
        except Exception as e:
            self.logger.warning(f"Failed to load embedding model {self.embedding_model}: {e}")
            # Try minimal configuration as fallback
            try:
                self.logger.info("Retrying with minimal configuration...")
                self.model = SentenceTransformer(self.embedding_model)
                self._validate_model()
                self.logger.info("Model loaded with minimal configuration")
            except Exception as retry_error:
                self.logger.error(f"Failed to load embedding model: {retry_error}")
                self.model = None
    
    def _authenticate_huggingface(self):
        """Authenticate with HuggingFace if token is available."""
        if not login:
            return
        
        if not hasattr(self, '_hf_authenticated'):
            token = os.getenv('HUGGINGFACE_HUB_TOKEN') or os.getenv('HF_TOKEN')
            if token:
                try:
                    login(token=token)
                    self.logger.info("Authenticated with Hugging Face")
                except Exception as e:
                    self.logger.warning(f"Hugging Face authentication failed: {e}")
            self._hf_authenticated = True
    
    def _validate_model(self):
        """Validate that the loaded model works correctly."""
        if not self.model:
            return
        
        try:
            # Test with a simple sentence
            test_text = "This is a test sentence for validation"
            test_embedding = self.model.encode(
                [test_text],
                show_progress_bar=False,
                normalize_embeddings=False
            )
            
            # Check dimensions
            actual_dimension = len(test_embedding[0])
            if actual_dimension != self.embedding_dimension:
                self.logger.warning(
                    f"Expected dimension {self.embedding_dimension}, "
                    f"but got {actual_dimension}. Updating..."
                )
                self.embedding_dimension = actual_dimension
        except Exception as e:
            self.logger.error(f"Model validation failed: {e}")
            raise
    
    def _clean_text(self, text: str) -> str:
        """Clean and prepare text for embedding."""
        if not text:
            return ""
        
        # Basic cleaning
        cleaned = text.strip()
        
        # Truncate if too long (models have limits)
        if len(cleaned) > self.max_sequence_length:
            cleaned = cleaned[:self.max_sequence_length]
        
        return cleaned
    
    def _encode_text(self, text: str) -> List[float]:
        """
        Encode text to vector using the loaded embedding model.
        
        Args:
            text: Text to encode
            
        Returns:
            List of floats representing the embedding vector
        """
        if not self.model:
            return [0.0] * self.embedding_dimension
        
        if not text or not text.strip():
            return [0.0] * self.embedding_dimension
        
        try:
            # Clean and prepare the text
            cleaned_text = self._clean_text(text)
            
            # Generate embedding
            embedding = self.model.encode(
                [cleaned_text],
                show_progress_bar=False,
                normalize_embeddings=False
            )
            vector = embedding[0].tolist()  # Convert numpy array to list
            
            return vector
            
        except Exception as e:
            self.logger.error(f"Failed to encode text: {e}")
            return [0.0] * self.embedding_dimension

    def _encode_text_full(self, text: str) -> Optional[List[float]]:
        """Encode text without the 512-character cut used by `_encode_text`."""
        if not self.model or not text or not text.strip():
            return None
        embedding = self.model.encode(
            [text.strip()],
            show_progress_bar=False,
            normalize_embeddings=False,
        )
        return embedding[0].tolist()
    
    def initialize_vector_index(self) -> bool:
        """
        Add vector fields to the existing index mapping.
        Updates the index mapping to include vector fields without creating a separate index.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.model:
            self.logger.warning("Embedding model not available, skipping vector field initialization")
            return False
        
        try:
            # Check if source index exists
            if not self.es.indices.exists(index=self.index_name):
                self.logger.error(f"Index {self.index_name} does not exist. Cannot add vector fields.")
                return False
            
            # Check current mapping to see if vector fields already exist
            current_mapping = self.es.indices.get_mapping(index=self.index_name)
            properties = current_mapping[self.index_name]["mappings"].get("properties", {})
            
            # Check if vector fields already exist
            if "model_vector" in properties:
                self.logger.info(f"Vector fields already exist in {self.index_name}")
                return True
            
            # Add vector fields to existing index mapping
            vector_fields_mapping = {
                "properties": {
                    # Extracted fields from description (add if not present)
                    "version": {"type": "keyword"},
                    "modalities": {"type": "keyword"},
                    "domain": {"type": "keyword"},
                    "architecture": {"type": "text"},
                    "parameterCount": {"type": "text"},
                    "dataset": {"type": "text"},
                    "trainingType": {"type": "keyword"},
                    "data_splits": {"type": "text"},
                    "adaption_techniques": {"type": "keyword"},
                    
                    # MPNet vector field
                    "model_vector": {
                        "type": "dense_vector",
                        "dims": self.embedding_dimension,
                        "index": True,
                        "similarity": "cosine"
                    },
                    
                    # Searchable text field
                    "searchable_text": {"type": "text"},
                    
                    # Metadata fields
                    "vector_created_at": {"type": "date"},
                    "embedding_model": {"type": "keyword"}
                }
            }
            
            # Update the index mapping
            self.es.indices.put_mapping(
                index=self.index_name,
                body=vector_fields_mapping
            )
            self.logger.info(f"Added vector fields to index: {self.index_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add vector fields to index: {e}")
            import traceback
            traceback.print_exc()
            return False

    def ensure_improved_vector_mapping(self) -> bool:
        """Add `improved_model_vector` without changing the existing `model_vector` field."""
        if not self.model:
            self.logger.warning("Embedding model not available, skipping improved vector mapping")
            return False
        try:
            if not self.es.indices.exists(index=self.index_name):
                self.logger.error("Index %s does not exist. Cannot add improved vector fields.", self.index_name)
                return False

            current_mapping = self.es.indices.get_mapping(index=self.index_name)
            index_key = self.index_name if self.index_name in current_mapping else next(iter(current_mapping))
            properties = current_mapping[index_key]["mappings"].get("properties", {})
            if "improved_model_vector" in properties:
                self.logger.info("Improved vector field already exists in %s", self.index_name)
                return True

            self.es.indices.put_mapping(
                index=self.index_name,
                body={
                    "properties": {
                        "improved_model_vector": {
                            "type": "dense_vector",
                            "dims": self.embedding_dimension,
                            "index": True,
                            "similarity": "cosine",
                        },
                        "improved_searchable_text": {"type": "text"},
                        "improved_vector_created_at": {"type": "date"},
                        "improved_embedding_model": {"type": "keyword"},
                    }
                },
            )
            self.logger.info("Added improved vector fields to index: %s", self.index_name)
            return True
        except Exception as e:
            self.logger.error("Failed to add improved vector fields to index: %s", e)
            return False
    
    def prepare_searchable_text(self, model_data: Dict[str, Any], extracted_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Prepare structured searchable text from model data for embedding.
        
        This creates a structured text representation from available model fields.
        
        Args:
            model_data: Dictionary containing model information from source index
            extracted_data: Optional dictionary containing extracted fields from description
            
        Returns:
            str: Structured text for embedding and storage
        """
        text_parts = []
        extracted_data = extracted_data or {}
        
        # === ORIGINAL DATA FIELDS ===
        
        # Model name
        name = model_data.get('name')
        if name:
            text_parts.append(f"The model name is {name}.")
        
        # Shared by
        shared_by = model_data.get('sharedBy') or model_data.get('shared_by')
        if shared_by:
            text_parts.append(f"It is shared by {shared_by}.")
        
        # ML Task
        ml_task = model_data.get('mlTask') or model_data.get('ml_task') or model_data.get('ml_tasks')
        if ml_task:
            if isinstance(ml_task, list):
                ml_task_str = ', '.join(str(t) for t in ml_task if t)
            else:
                ml_task_str = str(ml_task)
            text_parts.append(f"The model performs the {ml_task_str} task.")
        
        # Keywords
        keywords = model_data.get('keywords')
        if keywords and isinstance(keywords, list) and keywords:
            keywords_str = ', '.join(str(k) for k in keywords if k)
            text_parts.append(f"Keywords: {keywords_str}.")
        
        # Description
        description = model_data.get('description')
        if description:
            # Truncate description if too long
            desc_text = str(description)
            if len(desc_text) > 500:
                desc_text = desc_text[:500] + "..."
            text_parts.append(f"Description: {desc_text}")
        
        # === EXTRACTED FIELDS (if available) ===
        
        # Version (extracted)
        version = extracted_data.get('version')
        if version:
            text_parts.append(f"The version is {version}.")
        
        # Modalities (extracted)
        modalities = extracted_data.get('modalities')
        if modalities and isinstance(modalities, list) and modalities:
            modalities_str = ', '.join(str(m) for m in modalities if m)
            text_parts.append(f"The model works with {modalities_str} modalities.")
        
        # Domain (extracted)
        domain = extracted_data.get('domain')
        if domain:
            text_parts.append(f"The domain of the model is {domain}.")
        
        # Training type (extracted)
        training_type = extracted_data.get('trainingType') or extracted_data.get('training_type')
        if training_type:
            text_parts.append(f"The training type is {training_type}.")
        
        # Architecture (extracted)
        architecture = extracted_data.get('architecture')
        if architecture:
            text_parts.append(f"The architecture is {architecture}.")
        
        # Data splits (extracted)
        data_splits = extracted_data.get('data_splits') or model_data.get('data_splits')
        if data_splits:
            text_parts.append(f"Data splits: {data_splits}.")
        
        # Parameter count scale label (extracted or from source doc)
        # Canonical FAIR4ML-style field; ``model_data`` may still carry legacy ``modelSize`` from older indices
        pc_label = (
            extracted_data.get("parameterCount")
            or model_data.get("parameterCount")
            or model_data.get("modelSize")
            or model_data.get("model_size")
            or model_data.get("parameter_count")
        )
        if pc_label:
            text_parts.append(f"The model has approximately {pc_label} parameters.")
        
        # Datasets
        datasets = model_data.get('datasets') or model_data.get('dataset')
        extracted_ds = extracted_data.get('dataset')
        
        combined_datasets = []
        seen_lower = set()
        
        # From original field
        if datasets:
            if isinstance(datasets, list):
                candidates = datasets
            else:
                candidates = [str(datasets)]
            for ds in candidates:
                if not ds:
                    continue
                ds_str = str(ds).strip()
                if not ds_str or ds_str.lower() == 'information not found':
                    continue
                key = ds_str.lower()
                if key not in seen_lower:
                    seen_lower.add(key)
                    combined_datasets.append(ds_str)
        
        # From extracted field
        if extracted_ds:
            ds_str = str(extracted_ds).strip()
            if ds_str:
                key = ds_str.lower()
                if key not in seen_lower:
                    seen_lower.add(key)
                    combined_datasets.append(ds_str)
        
        if combined_datasets:
            if len(combined_datasets) == 1:
                text_parts.append(f"It was trained on the {combined_datasets[0]} dataset.")
            else:
                datasets_str = ', '.join(combined_datasets)
                text_parts.append(f"It was trained on the {datasets_str} datasets.")
        
        # Join all parts
        searchable_text = ' '.join(text_parts)
        
        return searchable_text
    
    def update_vector_index(
        self, 
        model_ids: Optional[List[str]] = None, 
        batch_size: int = 50, 
        skip_existing: bool = True
    ) -> Dict[str, Any]:
        """
        Add vector fields to existing documents in the index.
        Updates documents in-place by adding vector embeddings and extracted metadata.
        
        Args:
            model_ids: Optional list of specific model IDs to update.
                      If None, updates all models from index.
            batch_size: Number of models to process in each batch
            skip_existing: If True, skip documents that already have model_vector field
            
        Returns:
            Dictionary with statistics about the update operation
        """
        if not self.model:
            self.logger.warning("Embedding model not available")
            return {"processed": 0, "errors": 0, "skipped": 0}
        
        try:
            # Ensure vector index exists
            if not self.initialize_vector_index():
                return {"processed": 0, "errors": 0, "skipped": 0}
            
            # Get models to process
            if model_ids:
                # Process specific models
                query = {"query": {"terms": {"_id": model_ids}}}
            else:
                # Process all models
                query = {"query": {"match_all": {}}}
            
            # Use scroll API for large datasets
            response = self.es.search(
                index=self.index_name,
                body=query,
                scroll='5m',
                size=batch_size,
                _source=True
            )
            
            scroll_id = response['_scroll_id']
            hits = response['hits']['hits']
            total_processed = 0
            total_errors = 0
            total_skipped = 0
            
            while hits:
                self.logger.info(f"Processing batch of {len(hits)} models...")
                
                # Process batch
                for hit in hits:
                    model_data = hit["_source"]
                    model_id = hit["_id"]
                    
                    # Skip if document already has vector fields and skip_existing is True
                    if skip_existing and "model_vector" in model_data:
                        total_skipped += 1
                        continue
                    
                    try:
                        extracted_data = _extracted_data_from_indexed_model(model_data)
                        
                        # Prepare searchable text using structured format
                        searchable_text = self.prepare_searchable_text(model_data, extracted_data)
                        
                        if not searchable_text:
                            self.logger.warning(f"Skipping model {model_id} - no searchable text")
                            total_skipped += 1
                            continue
                        
                        # Generate embedding using integrated model
                        model_vector = self._encode_text(searchable_text)

                        _skip_extracted = frozenset(
                            {
                                "parameterCount",
                                "modelSize",
                                "model_size",
                                "parameter_count",
                                "citation",
                                "https://schema.org/citation",
                            }
                        )
                        vector_doc = {
                            k: v
                            for k, v in extracted_data.items()
                            if k not in _skip_extracted
                        }
                        pc_val = (
                            extracted_data.get("parameterCount")
                            or model_data.get("parameterCount")
                            or model_data.get("modelSize")
                            or model_data.get("model_size")
                            or model_data.get("parameter_count")
                        )
                        if pc_val is not None:
                            vector_doc["parameterCount"] = str(pc_val)
                        if model_data.get("adaption_techniques"):
                            vector_doc["adaption_techniques"] = model_data["adaption_techniques"]

                        # Prepare update document with extracted fields, vector, and searchable text
                        # Only update/add vector-related fields, keep existing document data intact
                        update_doc = {
                            **vector_doc,
                            "model_vector": model_vector,
                            "searchable_text": searchable_text,  # Store the text used for embedding
                            "vector_created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "embedding_model": self.embedding_model
                        }
                        
                        # Update existing document in index with vector fields
                        self.es.update(
                            index=self.index_name,
                            id=model_id,
                            body={"doc": update_doc}
                        )
                        total_processed += 1
                        
                    except Exception as e:
                        total_errors += 1
                        self.logger.warning(f"Error processing model {model_id}: {e}")
                        continue
                
                # Get next batch
                response = self.es.scroll(scroll_id=scroll_id, scroll='5m')
                scroll_id = response['_scroll_id']
                hits = response['hits']['hits']
                
                self.logger.info(f"Processed {total_processed} models so far...")
            
            # Clear scroll and refresh
            self.es.clear_scroll(scroll_id=scroll_id)
            self.es.indices.refresh(index=self.index_name)
            
            self.logger.info(
                f"Successfully processed {total_processed} models, "
                f"skipped {total_skipped}, errors {total_errors} "
                f"and added vector fields to {self.index_name}"
            )
            
            return {
                "processed": total_processed,
                "skipped": total_skipped,
                "errors": total_errors,
                "index": self.index_name
            }
            
        except Exception as e:
            self.logger.error(f"Vector index update failed: {e}")
            import traceback
            traceback.print_exc()
            return {"processed": 0, "errors": 1, "skipped": 0}

    def update_improved_vector_index(
        self,
        model_ids: Optional[List[str]] = None,
        batch_size: int = 50,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """Write `improved_model_vector` beside `model_vector`. Does not update `model_vector`."""
        if not self.model:
            self.logger.warning("Embedding model not available")
            return {"processed": 0, "errors": 0, "skipped": 0}

        try:
            if not self.ensure_improved_vector_mapping():
                return {"processed": 0, "errors": 0, "skipped": 0}

            if model_ids:
                query = {"query": {"terms": {"_id": model_ids}}}
            else:
                query = {"query": {"match_all": {}}}

            response = self.es.search(
                index=self.index_name,
                body=query,
                scroll="5m",
                size=batch_size,
                _source=True,
            )
            scroll_id = response["_scroll_id"]
            hits = response["hits"]["hits"]
            total_processed = 0
            total_errors = 0
            total_skipped = 0

            while hits:
                self.logger.info("Processing improved-vector batch of %s models...", len(hits))
                for hit in hits:
                    model_data = hit["_source"]
                    model_id = hit["_id"]
                    if skip_existing and "improved_model_vector" in model_data:
                        total_skipped += 1
                        continue
                    try:
                        extracted_data = _extracted_data_from_indexed_model(model_data)
                        searchable_text = build_improved_searchable_text(model_data, extracted_data)
                        if not searchable_text:
                            self.logger.warning("Skipping model %s - no improved searchable text", model_id)
                            total_skipped += 1
                            continue
                        model_vector = self._encode_text_full(searchable_text)
                        if not model_vector:
                            total_errors += 1
                            continue
                        self.es.update(
                            index=self.index_name,
                            id=model_id,
                            body={
                                "doc": {
                                    "improved_model_vector": model_vector,
                                    "improved_searchable_text": searchable_text,
                                    "improved_vector_created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "improved_embedding_model": self.embedding_model,
                                }
                            },
                        )
                        total_processed += 1
                    except Exception as e:
                        total_errors += 1
                        self.logger.warning("Error processing improved vector for model %s: %s", model_id, e)
                        continue

                response = self.es.scroll(scroll_id=scroll_id, scroll="5m")
                scroll_id = response["_scroll_id"]
                hits = response["hits"]["hits"]

            self.es.clear_scroll(scroll_id=scroll_id)
            self.es.indices.refresh(index=self.index_name)
            self.logger.info(
                "Improved vectors: processed %s, skipped %s, errors %s on %s",
                total_processed,
                total_skipped,
                total_errors,
                self.index_name,
            )
            return {
                "processed": total_processed,
                "skipped": total_skipped,
                "errors": total_errors,
                "index": self.index_name,
            }
        except Exception as e:
            self.logger.error("Improved vector index update failed: %s", e)
            return {"processed": 0, "errors": 1, "skipped": 0}


def run_vector_index_update(
    index_name: str,
    *,
    es_client=None,
    es_config: Optional[ElasticsearchConfig] = None,
    es_ready: Optional[Dict[str, Any]] = None,
    model_ids: Optional[List[str]] = None,
    batch_size: int = 50,
    skip_existing: bool = True,
    logger_instance=None,
) -> Dict[str, Any]:
    """
    Run vector embedding backfill for an Elasticsearch index using VectorIndexManager.

    Creates an ES client from config when ``es_client`` is not provided.
    Used by Dagster assets and one-off scripts so pipeline code stays thin.
    """
    log = logger_instance or logger
    cfg = es_config or ElasticsearchConfig.from_env()
    client = es_client or create_elasticsearch_client(cfg)

    if not client.indices.exists(index=index_name):
        log.warning("Index %s does not exist. Skipping vector indexing.", index_name)
        return {
            "status": "skipped",
            "reason": "index_not_found",
            "index": index_name,
            "processed": 0,
            "skipped": 0,
            "errors": 0,
        }

    manager = VectorIndexManager(es_client=client, index_name=index_name, logger_instance=log)
    stats = manager.update_vector_index(
        model_ids=model_ids,
        batch_size=batch_size,
        skip_existing=skip_existing,
    )
    result: Dict[str, Any] = {
        "status": "success",
        "index": index_name,
        **stats,
    }
    if es_ready is not None:
        cluster = es_ready.get("cluster_name")
        if cluster is not None:
            result["cluster_name"] = cluster
    return result


def run_improved_vector_index_update(
    index_name: str,
    *,
    es_client=None,
    es_config: Optional[ElasticsearchConfig] = None,
    model_ids: Optional[List[str]] = None,
    batch_size: int = 50,
    skip_existing: bool = True,
    logger_instance=None,
) -> Dict[str, Any]:
    """Backfill `improved_model_vector` from label:value text, leaving `model_vector` unchanged."""
    log = logger_instance or logger
    cfg = es_config or ElasticsearchConfig.from_env()
    client = es_client or create_elasticsearch_client(cfg)

    if not client.indices.exists(index=index_name):
        log.warning("Index %s does not exist. Skipping improved vector indexing.", index_name)
        return {
            "status": "skipped",
            "reason": "index_not_found",
            "index": index_name,
            "processed": 0,
            "skipped": 0,
            "errors": 0,
        }

    manager = VectorIndexManager(es_client=client, index_name=index_name, logger_instance=log)
    stats = manager.update_improved_vector_index(
        model_ids=model_ids,
        batch_size=batch_size,
        skip_existing=skip_existing,
    )
    return {"status": "success", "index": index_name, "profile": "improved", **stats}


BGE_M3_MODEL_NAME = "BAAI/bge-m3"
BGE_M3_DIMENSION = 1024
# Same gate as search: a model is indexed only when these fields exist and the
# text fields are not the loader's "Unknown" placeholder.
_SEARCH_REQUIRED_FIELDS = (
    "db_identifier",
    "name",
    "url",
    "shared_by",
    "datecreated",
    "datemodified",
    "description",
    "keywords",
    "license",
    "readme",
    "ml_tasks",
    "source",
)
_SEARCH_NONEMPTY_FIELDS = ("name", "description", "shared_by", "license", "readme", "source")
_SEARCH_MISSING_VALUES = ["", "Unknown"]
_MIN_FREE_BYTES = 2_000_000_000
_MAX_DISK_PERCENT = 96


def _metadata_gate_query() -> Dict[str, Any]:
    """Models search can return that do not already have a BGE vector."""
    return {
        "query": {
            "bool": {
                "must": [{"exists": {"field": field}} for field in _SEARCH_REQUIRED_FIELDS],
                "must_not": [
                    {"terms": {field: _SEARCH_MISSING_VALUES}}
                    for field in _SEARCH_NONEMPTY_FIELDS
                ]
                + [{"exists": {"field": "bge_m3_vector"}}],
            }
        }
    }


def _disk_is_tight(client) -> bool:
    """True when Elasticsearch is within 4 points of its high disk watermark."""
    stats = client.nodes.stats(metric="fs")
    for node in (stats.get("nodes") or {}).values():
        total = ((node.get("fs") or {}).get("total") or {})
        avail = int(total.get("available_in_bytes") or 0)
        size = int(total.get("total_in_bytes") or 0)
        if size <= 0:
            continue
        used_percent = (size - avail) * 100 / size
        if avail < _MIN_FREE_BYTES or used_percent >= _MAX_DISK_PERCENT:
            return True
    return False


def _load_bge_m3_model():
    """Load BGE-M3 without touching the MPNet model used by VectorIndexManager."""
    if SentenceTransformer is None:
        raise RuntimeError("sentence-transformers is not available")
    token = os.getenv("HUGGINGFACE_HUB_TOKEN") or os.getenv("HF_TOKEN")
    model = SentenceTransformer(
        BGE_M3_MODEL_NAME,
        trust_remote_code=True,
        token=token if token else None,
    )
    return model


def _ensure_bge_m3_mapping(es_client, index_name: str) -> None:
    current_mapping = es_client.indices.get_mapping(index=index_name)
    index_key = index_name if index_name in current_mapping else next(iter(current_mapping))
    properties = current_mapping[index_key]["mappings"].get("properties", {})
    if "bge_m3_vector" in properties:
        return
    es_client.indices.put_mapping(
        index=index_name,
        body={
            "properties": {
                "bge_m3_vector": {
                    "type": "dense_vector",
                    "dims": BGE_M3_DIMENSION,
                    "index": True,
                    "similarity": "cosine",
                },
                "bge_m3_searchable_text": {"type": "text"},
                "bge_m3_vector_created_at": {"type": "date"},
                "bge_m3_embedding_model": {"type": "keyword"},
            }
        },
    )


def run_bge_m3_vector_index_update(
    index_name: str,
    *,
    es_client=None,
    es_config: Optional[ElasticsearchConfig] = None,
    model_ids: Optional[List[str]] = None,
    batch_size: int = 16,
    skip_existing: bool = True,
    only_with_improved_vector: bool = True,
    metadata_gate: bool = False,
    logger_instance=None,
) -> Dict[str, Any]:
    """Write `bge_m3_vector` from the same label:value text as the improved vectors.

    Does not update `model_vector` or `improved_model_vector`.
    With `metadata_gate`, only models that pass the search metadata filter and
    do not already have `bge_m3_vector` are embedded.
    """
    log = logger_instance or logger
    cfg = es_config or ElasticsearchConfig.from_env()
    client = es_client or create_elasticsearch_client(cfg)

    if not client.indices.exists(index=index_name):
        log.warning("Index %s does not exist. Skipping BGE-M3 indexing.", index_name)
        return {
            "status": "skipped",
            "reason": "index_not_found",
            "index": index_name,
            "processed": 0,
            "skipped": 0,
            "errors": 0,
        }

    _ensure_bge_m3_mapping(client, index_name)
    model = _load_bge_m3_model()

    if model_ids:
        query: Dict[str, Any] = {"query": {"terms": {"_id": model_ids}}}
    elif metadata_gate:
        query = _metadata_gate_query()
    elif only_with_improved_vector:
        query = {"query": {"exists": {"field": "improved_model_vector"}}}
    else:
        query = {"query": {"match_all": {}}}

    search_body = dict(query)
    search_body["_source"] = {
        "excludes": ["model_vector", "improved_model_vector", "bge_m3_vector"]
    }
    response = client.search(index=index_name, body=search_body, scroll="5m", size=batch_size)
    scroll_id = response["_scroll_id"]
    hits = response["hits"]["hits"]
    total_processed = 0
    total_errors = 0
    total_skipped = 0
    stopped_for_disk = False

    try:
        while hits:
            if _disk_is_tight(client):
                stopped_for_disk = True
                log.warning(
                    "Stopping BGE-M3 indexing for %s: Elasticsearch disk is past %s%%.",
                    index_name,
                    _MAX_DISK_PERCENT,
                )
                break
            pending: List[tuple] = []
            for hit in hits:
                model_data = hit["_source"]
                model_id = hit["_id"]
                if skip_existing and model_data.get("bge_m3_vector"):
                    total_skipped += 1
                    continue
                extracted = _extracted_data_from_indexed_model(model_data)
                text = build_improved_searchable_text(model_data, extracted)
                if not text:
                    total_skipped += 1
                    continue
                pending.append((model_id, text))

            if pending:
                vectors = model.encode(
                    [text for _, text in pending],
                    show_progress_bar=False,
                    normalize_embeddings=True,
                )
                for (model_id, text), vector in zip(pending, vectors):
                    try:
                        client.update(
                            index=index_name,
                            id=model_id,
                            body={
                                "doc": {
                                    "bge_m3_vector": vector.tolist(),
                                    "bge_m3_searchable_text": text,
                                    "bge_m3_vector_created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "bge_m3_embedding_model": BGE_M3_MODEL_NAME,
                                }
                            },
                        )
                        total_processed += 1
                    except Exception as exc:
                        total_errors += 1
                        log.warning("Error writing BGE-M3 vector for %s: %s", model_id, exc)
            log.info(
                "BGE-M3 batch done. processed=%s skipped=%s errors=%s",
                total_processed,
                total_skipped,
                total_errors,
            )
            response = client.scroll(scroll_id=scroll_id, scroll="5m")
            scroll_id = response["_scroll_id"]
            hits = response["hits"]["hits"]
    finally:
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass
        client.indices.refresh(index=index_name)

    return {
        "status": "stopped_disk" if stopped_for_disk else "success",
        "index": index_name,
        "profile": "bge-m3",
        "processed": total_processed,
        "skipped": total_skipped,
        "errors": total_errors,
    }


def _ensure_splade_mapping(es_client, index_name: str) -> None:
    """Add SPLADE fields when they are missing. Existing fields stay as they are."""
    current_mapping = es_client.indices.get_mapping(index=index_name)
    index_key = index_name if index_name in current_mapping else next(iter(current_mapping))
    properties = current_mapping[index_key]["mappings"].get("properties", {})
    new_properties: Dict[str, Any] = {}
    if "splade_vector" not in properties:
        new_properties["splade_vector"] = {"type": "sparse_vector"}
    if "splade_searchable_text" not in properties:
        new_properties["splade_searchable_text"] = {"type": "text"}
    if new_properties:
        es_client.indices.put_mapping(index=index_name, body={"properties": new_properties})


def _metadata_gate_clauses() -> tuple:
    """Same gate as search: required fields exist and are not empty or Unknown."""
    must = [{"exists": {"field": field}} for field in _SEARCH_REQUIRED_FIELDS]
    must_not = [
        {"terms": {field: list(_SEARCH_MISSING_VALUES)}}
        for field in _SEARCH_NONEMPTY_FIELDS
    ]
    return must, must_not


def run_splade_index_update(
    index_name: str,
    *,
    es_client=None,
    es_config: Optional[ElasticsearchConfig] = None,
    model_ids: Optional[List[str]] = None,
    batch_size: int = 8,
    skip_existing: bool = True,
    metadata_gate: bool = False,
    progress_every: int = 100,
    logger_instance=None,
) -> Dict[str, Any]:
    """Write ``splade_vector`` and ``splade_searchable_text`` for one index.

    Documents that already have ``splade_vector`` are left alone, so the update
    can be stopped and started again. With ``metadata_gate``, only models that
    pass the search metadata filter are encoded. Does not read or write the
    dense vector fields.
    """
    from etl_loaders.splade_encoder import get_splade_encoder

    log = logger_instance or logger
    cfg = es_config or ElasticsearchConfig.from_env()
    client = es_client or create_elasticsearch_client(cfg)

    if not client.indices.exists(index=index_name):
        log.warning("Index %s does not exist. Skipping SPLADE indexing.", index_name)
        return {
            "status": "skipped",
            "reason": "index_not_found",
            "index": index_name,
            "processed": 0,
            "skipped": 0,
            "errors": 0,
        }

    _ensure_splade_mapping(client, index_name)
    encoder = get_splade_encoder()

    must: List[Dict[str, Any]] = []
    must_not: List[Dict[str, Any]] = []
    if metadata_gate:
        gate_must, gate_must_not = _metadata_gate_clauses()
        must.extend(gate_must)
        must_not.extend(gate_must_not)
    if model_ids:
        must.append({"terms": {"_id": model_ids}})
    if skip_existing:
        must_not.append({"exists": {"field": "splade_vector"}})
    if not must:
        must.append({"match_all": {}})
    query: Dict[str, Any] = {"query": {"bool": {"must": must, "must_not": must_not}}}

    already_indexed = 0
    if skip_existing:
        count_must: List[Dict[str, Any]] = [{"exists": {"field": "splade_vector"}}]
        count_must_not: List[Dict[str, Any]] = []
        if metadata_gate:
            gate_must, gate_must_not = _metadata_gate_clauses()
            count_must.extend(gate_must)
            count_must_not.extend(gate_must_not)
        if model_ids:
            count_must.append({"ids": {"values": model_ids}})
        count_query = {"query": {"bool": {"must": count_must, "must_not": count_must_not}}}
        already_indexed = int(client.count(index=index_name, body=count_query).get("count", 0))

    search_body = dict(query)
    search_body["size"] = batch_size
    search_body["_source"] = {
        "excludes": ["model_vector", "improved_model_vector", "bge_m3_vector", "splade_vector"]
    }
    response = client.search(index=index_name, body=search_body, scroll="5m")
    scroll_id = response["_scroll_id"]
    hits = response["hits"]["hits"]
    total_processed = 0
    total_errors = 0
    total_skipped = already_indexed
    stopped_for_disk = False
    next_progress = progress_every if progress_every > 0 else 0
    log.info(
        "SPLADE indexing %s. already_have_vector=%s progress_every=%s",
        index_name,
        already_indexed,
        progress_every,
    )

    try:
        while hits:
            if _disk_is_tight(client):
                stopped_for_disk = True
                log.warning(
                    "Stopping SPLADE indexing for %s: Elasticsearch disk is past %s%%.",
                    index_name,
                    _MAX_DISK_PERCENT,
                )
                break
            pending: List[tuple] = []
            for hit in hits:
                model_data = hit["_source"]
                model_id = hit["_id"]
                extracted = _extracted_data_from_indexed_model(model_data)
                text = encoder.prepare_document_text(model_data, extracted)
                if not text:
                    total_skipped += 1
                    continue
                pending.append((model_id, text))

            if pending:
                vectors = encoder.encode_documents([text for _, text in pending])
                for (model_id, text), weights in zip(pending, vectors):
                    if not weights:
                        total_skipped += 1
                        continue
                    try:
                        client.update(
                            index=index_name,
                            id=model_id,
                            body={
                                "doc": {
                                    "splade_vector": weights,
                                    "splade_searchable_text": text,
                                }
                            },
                        )
                        total_processed += 1
                        if next_progress and total_processed >= next_progress:
                            log.info(
                                "SPLADE progress index=%s created=%s skipped=%s errors=%s",
                                index_name,
                                total_processed,
                                total_skipped,
                                total_errors,
                            )
                            next_progress += progress_every
                    except Exception as exc:
                        total_errors += 1
                        log.warning("Error writing SPLADE vector for %s: %s", model_id, exc)
            response = client.scroll(scroll_id=scroll_id, scroll="5m")
            scroll_id = response["_scroll_id"]
            hits = response["hits"]["hits"]
    finally:
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass
        client.indices.refresh(index=index_name)

    return {
        "status": "stopped_disk" if stopped_for_disk else "success",
        "index": index_name,
        "profile": "splade",
        "processed": total_processed,
        "skipped": total_skipped,
        "errors": total_errors,
    }

