"""
Dagster assets for HuggingFace → FAIR4ML transformation.

Pipeline:
1) Read raw HF models from extraction (hf_models_with_ancestors.json)
2) Create separate assets for each property group:
   - hf_extract_basic_properties: Core identification, temporal, URLs
   - hf_extract_keywords_language: Tags → keywords, inLanguage
   - hf_extract_task_category: pipeline_tag, library_name → mlTask, modelCategory
   - hf_extract_license: License information
   - hf_extract_lineage: Base model relationships
   - hf_extract_code_usage: Code snippets and usage instructions
   - hf_extract_datasets: Training/evaluation datasets
   - hf_extract_ethics_risks: Limitations, biases, ethical considerations
3) Merge all partial schemas in hf_models_normalized
4) Validate with Pydantic
5) Write normalized models to /data/normalized/hf/<timestamp_uuid>/mlmodels.json
"""

from __future__ import annotations

import json
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Any
import logging

import pandas as pd
from pydantic import BaseModel, ValidationError

from dagster import asset, AssetIn

from etl_extractors.hf import HFHelper
from etl_transformers.hf.transform_mlmodel import map_basic_properties
from schemas.fair4ml import MLModel
from schemas.schemaorg import ScholarlyArticle


logger = logging.getLogger(__name__)


def _json_default(o):
    """Non-recursive JSON serializer for known non-serializable types."""
    if isinstance(o, BaseModel):
        return o.model_dump(mode='json', by_alias=True)
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, set):
        return list(o)
    if isinstance(o, tuple):
        return list(o)
    return str(o)

@asset(
    group_name="hf_transformation",
    ins={"models_data": AssetIn("hf_add_ancestor_models")},
    tags={"pipeline": "hf_etl"}
)
def hf_normalized_run_folder(models_data: Tuple[str, str]) -> Tuple[str, str]:
    """
    Create a run folder for normalized HF models.
    
    Follows the same pattern as raw extraction for traceability.
    
    Args:
        models_data: Tuple of (models_json_path, raw_run_folder)
        
    Returns:
        Path to the normalized run-specific output directory
    """
    raw_data_json_path, raw_run_folder = models_data
    
    # Extract timestamp and run_id from raw folder name
    raw_folder_name = Path(raw_run_folder).name  # e.g., "2025-10-30_16-45-38_a510a3c3"
    
    # Create corresponding normalized folder
    normalized_base = Path("/data/2_normalized/hf")
    normalized_run_folder = normalized_base / raw_folder_name
    normalized_run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created normalized run folder: {normalized_run_folder}")
    return (str(raw_data_json_path), str(normalized_run_folder))


@asset(
    group_name="hf_transformation",
    ins={
        "models_data": AssetIn("hf_normalized_run_folder"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_extract_basic_properties(
    models_data: Tuple[str, str],
) -> str:
    """
    Extract basic properties from HF models.
    
    Maps: modelId, author, createdAt, last_modified, card
    To: identifier, name, url, author, sharedBy, dates, description, URLs
    
    Args:
        models_data: Tuple of (raw_data_json_path, normalized_folder)
        
    Returns:
        Path to saved partial schema JSON file
    """
    raw_data_json_path, normalized_folder = models_data
    
    # Load raw models
    logger.info(f"Loading raw models from {raw_data_json_path}")
    with open(raw_data_json_path, 'r', encoding='utf-8') as f:
        raw_models = json.load(f)
    
    logger.info(f"Loaded {len(raw_models)} raw models")
    
    # Extract basic properties for each model
    partial_schemas: List[Dict[str, Any]] = []
    
    for idx, raw_model in enumerate(raw_models):
        model_id = raw_model.get("modelId", f"unknown_{idx}")
        
        try:
            # Map basic properties
            partial_data = map_basic_properties(raw_model)
            
            # Add model_id as key for merging later
            partial_data["_model_id"] = model_id
            partial_data["_index"] = idx
            
            partial_schemas.append(partial_data)
            
            if (idx + 1) % 100 == 0:
                logger.info(f"Extracted basic properties for {idx + 1}/{len(raw_models)} models")
                
        except Exception as e:
            logger.error(f"Error extracting basic properties for {model_id}: {e}", exc_info=True)
            
            # Create minimal partial schema with error info
            partial_schemas.append({
                "_model_id": model_id,
                "_index": idx,
                "_error": str(e),
                "identifier": model_id,
                "name": model_id,
                "url": ""
            })
    
    logger.info(f"Extracted basic properties for {len(partial_schemas)} models")
    
    # Save partial schemas
    output_path = Path(normalized_folder) / "partial_basic_properties.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(partial_schemas, f,
                  indent=2,
                  ensure_ascii=False,
                  default=_json_default)
    
    logger.info(f"Saved basic properties to {output_path}")
    return str(output_path)


@asset(
    group_name="hf_transformation",
    ins={
        "datasets_mapping": AssetIn("hf_identified_datasets"),
        "articles_mapping": AssetIn("hf_identified_articles"),
        "keywords_mapping": AssetIn("hf_identified_keywords"),
        "licenses_mapping": AssetIn("hf_identified_licenses"),
        "base_models_mapping": AssetIn("hf_identified_base_models"),
        "languages_mapping": AssetIn("hf_identified_languages"),
        "tasks_mapping": AssetIn("hf_identified_tasks"),
        "run_folder_data": AssetIn("hf_normalized_run_folder"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_entity_linking(
    datasets_mapping: Tuple[Dict[str, List[str]], str],
    articles_mapping: Tuple[Dict[str, List[str]], str],
    keywords_mapping: Tuple[Dict[str, List[str]], str],
    licenses_mapping: Tuple[Dict[str, List[str]], str],
    base_models_mapping: Tuple[Dict[str, List[str]], str],
    languages_mapping: Tuple[Dict[str, List[str]], str],
    tasks_mapping: Tuple[Dict[str, List[str]], str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Create entity linking mapping: model_id -> {datasets, articles, keywords, licenses}

    Links identified entities with their enriched metadata.

    Args:
        datasets_mapping: Tuple of ({model_id: [dataset_names]}, run_folder)
        articles_mapping: Tuple of ({model_id: [arxiv_ids]}, run_folder)
        keywords_mapping: Tuple of ({model_id: [keywords]}, run_folder)
        licenses_mapping: Tuple of ({model_id: [license_ids]}, run_folder)
        base_models_mapping: Tuple of ({model_id: [base_model_ids]}, run_folder)
        run_folder_data: Tuple of (models_json_path, normalized_folder)

    Returns:
        Path to saved entity linking JSON file
    """
    _, normalized_folder = run_folder_data

    # Extract the model-entity mappings from the tuples
    model_datasets = datasets_mapping[0]
    model_articles = articles_mapping[0]
    model_keywords = keywords_mapping[0]
    model_licenses = licenses_mapping[0]
    model_base_models = base_models_mapping[0]
    model_languages = languages_mapping[0]
    model_tasks = tasks_mapping[0]
    # Create the final linking structure
    entity_linking = {}

    logger.info(f"base models: {model_base_models}")
    logger.info(f"base models: {model_base_models.keys()}")
    
    for model_id in model_datasets.keys():
        model_entities = {
            "datasets": [HFHelper.generate_mlentory_entity_hash_id('Dataset', x) for x in model_datasets[model_id]],
            "articles": [HFHelper.generate_mlentory_entity_hash_id('Article', x) for x in model_articles[model_id]],
            "keywords": [HFHelper.generate_mlentory_entity_hash_id('Keyword', x) for x in model_keywords[model_id]],
            "licenses": [HFHelper.generate_mlentory_entity_hash_id('License', x) for x in model_licenses[model_id]],
            "base_models": [HFHelper.generate_mlentory_entity_hash_id('Model', x) for x in model_base_models[model_id]],
            "languages": [HFHelper.generate_mlentory_entity_hash_id('Language', x) for x in model_languages[model_id]],
            "tasks": [HFHelper.generate_mlentory_entity_hash_id('Task', x) for x in model_tasks[model_id]],
        }

        entity_linking[model_id] = model_entities

    # Save the linking data
    output_path = Path(normalized_folder) / "entity_linking.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(entity_linking, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"Saved entity linking data for {len(entity_linking)} models to {output_path}")
    return str(output_path)

@asset(
    group_name="hf_transformation",
    ins={
        "models_data": AssetIn("hf_normalized_run_folder"),
        "basic_properties": AssetIn("hf_extract_basic_properties"),
        "entity_linking": AssetIn("hf_entity_linking"),
        # TODO: Add more partial schema inputs as we implement them:
        # "keywords_language": AssetIn("hf_extract_keywords_language"),
        # "task_category": AssetIn("hf_extract_task_category"),
        # "license_data": AssetIn("hf_extract_license"),
        # "lineage": AssetIn("hf_extract_lineage"),
        # "code_usage": AssetIn("hf_extract_code_usage"),
        # "datasets": AssetIn("hf_extract_datasets"),
        # "ethics_risks": AssetIn("hf_extract_ethics_risks"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_models_normalized(
    models_data: Tuple[str, str],
    basic_properties: str,
    entity_linking: str,
) -> Tuple[str, str]:
    """
    Merge partial schemas and create final FAIR4ML MLModel objects.

    This asset aggregates all partial property extractions, merges them by model,
    validates against Pydantic schema, and writes the final normalized models.

    Args:
        models_data: Tuple of (raw_data_json_path, normalized_folder)
        basic_properties: Path to basic properties partial schema
        entity_linking: Path to entity linking JSON file


    Returns:
        Path to the saved normalized models JSON file
    """
    raw_data_json_path, normalized_folder = models_data
    
    # Load raw models for reference
    logger.info(f"Loading raw models from {raw_data_json_path}")
    with open(raw_data_json_path, 'r', encoding='utf-8') as f:
        raw_models = json.load(f)
    
    logger.info(f"Loaded {len(raw_models)} raw models")
    
    # Load all partial schemas
    logger.info("Loading partial schemas...")
    
    with open(basic_properties, 'r', encoding='utf-8') as f:
        basic_props = json.load(f)
    
    logger.info(f"Loaded {len(basic_props)} basic property schemas")

    # Load entity linking data
    logger.info(f"Loading entity linking data from {entity_linking}")
    with open(entity_linking, 'r', encoding='utf-8') as f:
        entity_linking_data = json.load(f)

    logger.info(f"Loaded entity linking data for {len(entity_linking_data)} models")

    # Create index mapping for efficient merging
    basic_props_by_index = {item["_index"]: item for item in basic_props}
    # TODO: Create indices for other partial schemas
    
    # Merge partial schemas
    logger.info("Merging partial schemas...")
    merged_schemas: List[Dict[str, Any]] = []
    
    for idx, raw_model in enumerate(raw_models):
        model_id = raw_model.get("modelId", f"unknown_{idx}")
        
        try:
            # Start with basic properties
            merged = basic_props_by_index.get(idx, {}).copy()
            # logger.info(f"Merged schemas: {merged}")
            
            # Remove internal fields used for merging
            merged.pop("_model_id", None)
            merged.pop("_index", None)
            merged.pop("_error", None)

            # Add platform-specific metrics
            # merged["metrics"] = {
            #     "downloads": raw_model.get("downloads", 0),
            #     "likes": raw_model.get("likes", 0),
            # }

            # Add linked entities
            if model_id in entity_linking_data:
                model_entities = entity_linking_data[model_id]

                # Add enriched datasets, articles, keywords, licenses
                merged["license"] = model_entities["licenses"][0] if len(model_entities["licenses"]) > 0 else None
                merged["trainedOn"] = model_entities["datasets"]
                merged["testedOn"] = model_entities["datasets"]
                merged["validatedOn"] = model_entities["datasets"]
                merged["evaluatedOn"] = model_entities["datasets"]
                merged["referencePublication"] = model_entities["articles"]
                merged["keywords"] = model_entities["keywords"]
                merged["fineTunedFrom"] = model_entities["base_models"]
                merged["inLanguage"] = model_entities["languages"]
                merged["mlTask"] = model_entities["tasks"]
            
            merged_schemas.append(merged)
            
            if (idx + 1) % 100 == 0:
                logger.info(f"Merged schemas for {idx + 1}/{len(raw_models)} models")
                
        except Exception as e:
            logger.error(f"Error merging schemas for model {model_id}: {e}", exc_info=True)
            logger.error(f"Stack trace: {traceback.format_exc()}")
    
    logger.info(f"Merged {len(merged_schemas)} schemas")
    
    # Validate and create MLModel instances
    logger.info("Validating merged schemas...")
    normalized_models: List[Dict[str, Any]] = []
    validation_errors: List[Dict[str, Any]] = []
    
    for idx, merged_data in enumerate(merged_schemas):
        model_id = merged_data.get("identifier", f"unknown_{idx}")
        
        try:
            # Validate with Pydantic
            mlmodel = MLModel(**merged_data)
            
            # Convert to dict for JSON serialization using IRI aliases
            normalized_models.append(mlmodel.model_dump(mode='json', by_alias=True))
            
            if (idx + 1) % 100 == 0:
                logger.info(f"Validated {idx + 1}/{len(merged_schemas)} models")
                
        except ValidationError as e:
            logger.error(f"Validation error for model {model_id}: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            validation_errors.append({
                "modelId": model_id,
                "error": str(e),
                "merged_data": merged_data
            })
        except Exception as e:
            logger.error(f"Unexpected error validating model {model_id}: {e}", exc_info=True)
            validation_errors.append({
                "modelId": model_id,
                "error": str(e),
                "error_type": type(e).__name__
            })
    
    logger.info(f"Successfully validated {len(normalized_models)}/{len(merged_schemas)} models")
    
    if validation_errors:
        logger.warning(f"Encountered {len(validation_errors)} validation errors")
    
    # Guardrail: fail the run if no models were successfully transformed
    if not normalized_models:
        logger.error("No models were successfully normalized. Failing the run.")
        raise RuntimeError("hf_models_normalized produced zero models. Aborting run.")
    
    # Write normalized models
    output_path = Path(normalized_folder) / "mlmodels.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(normalized_models, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"Wrote {len(normalized_models)} normalized models to {output_path}")
    
    # Write errors if any
    if validation_errors:
        errors_path = Path(normalized_folder) / "transformation_errors.json"
        with open(errors_path, 'w', encoding='utf-8') as f:
            json.dump(validation_errors, f, indent=2, ensure_ascii=False)
        logger.info(f"Wrote {len(validation_errors)} errors to {errors_path}")
    
        # Warn if fewer models were produced than provided as input, and provide file paths to the errors
        if len(normalized_models) < len(raw_models):
            logger.warning(
                "Normalized model count (%s) is less than input raw models (%s).",
                "check the entity linking and validation errors files: %s",
                len(normalized_models),
                len(raw_models),
                str(errors_path)
            )
    
    return (str(output_path), str(normalized_folder))



def _load_enriched_entity_mapping(json_path: str, entity_type: str) -> Dict[str, Dict]:
    """
    Load enriched entity JSON file and create {entity_id: entity_data} mapping.

    Args:
        json_path: Path to the enriched entities JSON file
        entity_type: Type of entity ("datasets", "articles", "keywords", "licenses")

    Returns:
        Dict mapping entity identifier to enriched entity data
    """
    if not json_path or not Path(json_path).exists():
        logger.warning(f"Enriched {entity_type} file not found: {json_path}")
        return {}

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            entities = json.load(f)

        entity_mapping = {}

        for entity in entities:
            # Use mlentory_id as the key
            mlentory_id = entity.get("mlentory_id")
            if mlentory_id:
                entity_mapping[mlentory_id] = entity
            else:
                # Fallback: generate mlentory_id if not present (for backward compatibility)
                if entity_type == "datasets":
                    entity_id = entity.get("datasetId")
                elif entity_type == "articles":
                    entity_id = entity.get("arxiv_id")
                elif entity_type == "keywords":
                    entity_id = entity.get("keyword")
                elif entity_type == "licenses":
                    entity_id = entity.get("Name") or entity.get("Identifier")
                else:
                    logger.warning(f"Unknown entity type: {entity_type}")
                    continue

                if entity_id:
                    from etl_extractors.hf import HFHelper
                    mlentory_id = HFHelper.generate_mlentory_entity_hash_id(entity_type.rstrip("s").capitalize(), entity_id)
                    entity["mlentory_id"] = mlentory_id
                    entity_mapping[mlentory_id] = entity

        logger.info(f"Loaded {len(entity_mapping)} enriched {entity_type} entities")
        return entity_mapping

    except Exception as e:
        logger.error(f"Error loading enriched {entity_type} from {json_path}: {e}")
        return {}


@asset(
    group_name="hf_transformation",
    ins={
        "articles_json": AssetIn("hf_enriched_articles"),
        "run_folder": AssetIn("hf_normalized_run_folder"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_articles_normalized(
    articles_json: str,
    run_folder: Tuple[str, str],
) -> str:
    """
    Normalize arXiv articles from HF enrichment to Schema.org ScholarlyArticle format.
    
    Maps raw arXiv metadata extracted by HFArxivClient to IRI-aliased JSON
    following the Schema.org ScholarlyArticle specification.
    
    Args:
        articles_json: Path to enriched arXiv articles JSON (arxiv_articles.json)
        run_folder: Tuple of (raw_data_json_path, normalized_folder)
        
    Returns:
        Path to normalized articles JSON file
    """
    _, normalized_folder = run_folder
    
    # Handle empty articles case
    if not articles_json or articles_json == "":
        logger.info("No articles to normalize (empty input)")
        return ""
    
    articles_path = Path(articles_json)
    if not articles_path.exists():
        logger.warning(f"Articles JSON not found: {articles_json}")
        return ""
    
    # Load raw articles
    logger.info(f"Loading raw articles from {articles_json}")
    with open(articles_path, 'r', encoding='utf-8') as f:
        raw_articles = json.load(f)
    
    if not raw_articles:
        logger.info("No articles to normalize (empty list)")
        return ""
    
    logger.info(f"Loaded {len(raw_articles)} raw articles")
    
    # Normalize each article
    normalized_articles: List[Dict[str, Any]] = []
    validation_errors: List[Dict[str, Any]] = []
    
    for idx, raw_article in enumerate(raw_articles):
        arxiv_id = raw_article.get("arxiv_id", f"unknown_{idx}")
        
        try:
            # Build normalized article data
            article_data = {}
            
            # Identifiers
            identifiers = []
            mlentory_id = raw_article.get("mlentory_id")
            if mlentory_id:
                identifiers.append(mlentory_id)
            
            if arxiv_id and arxiv_id != f"unknown_{idx}":
                identifiers.append(f"https://arxiv.org/abs/{arxiv_id}")
                identifiers.append(f"arXiv:{arxiv_id}")
            
            article_data["identifier"] = identifiers
            
            # Name (title)
            article_data["name"] = raw_article.get("title") or f"Article {arxiv_id}"
            
            # URL
            if arxiv_id and arxiv_id != f"unknown_{idx}":
                article_data["url"] = f"https://arxiv.org/abs/{arxiv_id}"
            else:
                article_data["url"] = mlentory_id or ""
            
            # sameAs (DOI, PDF, other links)
            same_as = []
            doi = raw_article.get("doi")
            if doi:
                same_as.append(f"https://doi.org/{doi}")
            
            pdf_url = raw_article.get("pdf_url")
            if pdf_url:
                same_as.append(pdf_url)
            
            links = raw_article.get("links", [])
            if links:
                for link in links:
                    if isinstance(link, str) and link.startswith("http"):
                        same_as.append(link)
            
            article_data["sameAs"] = same_as
            
            # Description (summary)
            article_data["description"] = raw_article.get("summary")
            
            # Authors
            authors = []
            authors_data = raw_article.get("authors", [])
            if authors_data:
                for author in authors_data:
                    if isinstance(author, dict):
                        author_name = author.get("name")
                        if author_name:
                            authors.append(author_name)
                    elif isinstance(author, str):
                        authors.append(author)
            article_data["author"] = authors
            
            # Temporal information
            published = raw_article.get("published")
            if published:
                try:
                    # Parse date string to datetime
                    if isinstance(published, str):
                        # Handle various formats
                        if 'T' in published:
                            article_data["datePublished"] = datetime.fromisoformat(published.replace('Z', '+00:00'))
                        else:
                            article_data["datePublished"] = datetime.fromisoformat(f"{published}T00:00:00")
                    elif isinstance(published, datetime):
                        article_data["datePublished"] = published
                except Exception as e:
                    logger.warning(f"Failed to parse published date for {arxiv_id}: {e}")
            
            updated = raw_article.get("updated")
            if updated:
                try:
                    if isinstance(updated, str):
                        if 'T' in updated:
                            article_data["dateModified"] = datetime.fromisoformat(updated.replace('Z', '+00:00'))
                        else:
                            article_data["dateModified"] = datetime.fromisoformat(f"{updated}T00:00:00")
                    elif isinstance(updated, datetime):
                        article_data["dateModified"] = updated
                except Exception as e:
                    logger.warning(f"Failed to parse updated date for {arxiv_id}: {e}")
            
            # About (categories)
            about = []
            categories = raw_article.get("categories", [])
            if categories:
                about.extend(categories)
            
            primary_category = raw_article.get("primary_category")
            if primary_category and primary_category not in about:
                about.append(primary_category)
            
            article_data["about"] = about
            
            # isPartOf (journal reference)
            journal_ref = raw_article.get("journal_ref")
            if journal_ref:
                article_data["isPartOf"] = journal_ref
            
            # Comment
            comment = raw_article.get("comment")
            if comment:
                article_data["comment"] = comment
            
            # Extraction metadata
            extraction_metadata = raw_article.get("extraction_metadata", {})
            article_data["extraction_metadata"] = extraction_metadata
            
            # Validate with Pydantic
            scholarly_article = ScholarlyArticle(**article_data)
            
            # Convert to dict for JSON serialization using IRI aliases
            normalized_articles.append(scholarly_article.model_dump(mode='json', by_alias=True))
            
            if (idx + 1) % 50 == 0:
                logger.info(f"Normalized {idx + 1}/{len(raw_articles)} articles")
                
        except ValidationError as e:
            logger.error(f"Validation error for article {arxiv_id}: {e}")
            validation_errors.append({
                "arxiv_id": arxiv_id,
                "error": str(e),
                "raw_data": raw_article
            })
        except Exception as e:
            logger.error(f"Unexpected error normalizing article {arxiv_id}: {e}", exc_info=True)
            validation_errors.append({
                "arxiv_id": arxiv_id,
                "error": str(e),
                "error_type": type(e).__name__
            })
    
    logger.info(f"Successfully normalized {len(normalized_articles)}/{len(raw_articles)} articles")
    
    if validation_errors:
        logger.warning(f"Encountered {len(validation_errors)} validation errors")
    
    # Write normalized articles
    output_path = Path(normalized_folder) / "articles.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(normalized_articles, f, indent=2, ensure_ascii=False, default=_json_default)
    
    logger.info(f"Wrote {len(normalized_articles)} normalized articles to {output_path}")
    
    # Write errors if any
    if validation_errors:
        errors_path = Path(normalized_folder) / "articles_transformation_errors.json"
        with open(errors_path, 'w', encoding='utf-8') as f:
            json.dump(validation_errors, f, indent=2, ensure_ascii=False)
        logger.info(f"Wrote {len(validation_errors)} errors to {errors_path}")
    
    return str(output_path)