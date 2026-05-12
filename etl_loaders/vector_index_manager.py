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
                    "modelSize": {"type": "keyword"},
                    "dataset": {"type": "text"},
                    "trainingType": {"type": "keyword"},
                    
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
        
        # Model size (extracted)
        model_size = extracted_data.get('modelSize') or extracted_data.get('model_size')
        if model_size:
            text_parts.append(f"The model size is {model_size}.")
        
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
                        # For now, we don't have metadata extraction in etl_backend
                        # So we'll use empty extracted_data
                        extracted_data = {}
                        
                        # Prepare searchable text using structured format
                        searchable_text = self.prepare_searchable_text(model_data, extracted_data)
                        
                        if not searchable_text:
                            self.logger.warning(f"Skipping model {model_id} - no searchable text")
                            total_skipped += 1
                            continue
                        
                        # Generate embedding using integrated model
                        model_vector = self._encode_text(searchable_text)
                        
                        # Prepare update document with extracted fields, vector, and searchable text
                        # Only update/add vector-related fields, keep existing document data intact
                        update_doc = {
                            **extracted_data,  # Extracted fields (empty for now)
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

