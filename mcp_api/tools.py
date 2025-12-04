"""
MCP Tools for MLentory Model Search and Retrieval.

This module defines the MCP tools that expose model search and retrieval
functionality to AI assistants through the Model Context Protocol.

Tools:
    - search_models: Search for ML models with text queries and pagination
    - get_model_detail: Get detailed information about a specific model

Example:
    >>> from mcp_api.tools import search_models, get_model_detail
    >>> 
    >>> # Search for models
    >>> result = search_models(query="bert", page=1, page_size=10)
    >>> print(f"Found {result['total']} models")
    >>> 
    >>> # Get model details
    >>> model = get_model_detail(model_id="https://w3id.org/mlentory/model/abc123")
    >>> print(model['name'])
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import spacy

from api.services.elasticsearch_service import elasticsearch_service
from api.services.graph_service import graph_service
from etl_extractors.hf.hf_readme_parser import MDParserChunker
from schemas.fair4ml.mlmodel import MLModel

logger = logging.getLogger(__name__)

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])


TRIVIAL_TOKENS = {"model", "models", "task", "tasks", "dataset", "datasets", "example"}
VALID_POS = {"NOUN", "PROPN", "ADJ"}


def _clean_description(description: Optional[str], max_section_length: int = 300) -> Optional[str]:
    """
    Clean and format model description by removing tables/lists and truncating long sections.
    
    Args:
        description: Raw description text (markdown format)
        max_section_length: Maximum length for each section before truncation
        
    Returns:
        Cleaned description text or None if input is None/empty
    """
    if not description or not description.strip():
        return description

    try:
        md_parser_chunker = MDParserChunker(logger=logger)

        # Build AST and section-like chunks from the markdown description
        ast = md_parser_chunker.generate_ast(description)
        chunks = md_parser_chunker.generate_chunks(ast, min_len=min_section_words)

        # Make the dicts compatible with the old section objects
        for d in chunks:
            # original key from chunker is "text"
            d["content"] = d.pop("text", "")
            parent = d.get("parent")
            d["title"] = (parent + "/" if parent else "") + d["id"]

        sections = [SimpleNamespace(**d) for d in chunks]

        # Build final cleaned text from sections, skipping code/table chunks
        cleaned_parts: List[str] = []
        for section in sections:
            section_type = getattr(section, "type", "")
            if section_type in {"code", "table"}:
                continue

            content = getattr(section, "content", "") or ""
            content = content.strip()
            if not content:
                continue

            # Truncate if longer than max_section_length (in characters)
            if len(content) > max_section_length:
                truncated = content[:max_section_length]
                # avoid cutting mid-word when possible
                if " " in truncated:
                    truncated = truncated.rsplit(" ", 1)[0]
                content = truncated + "..."

            cleaned_parts.append(content)

        # Join sections with double newline
        result = "\n\n".join(cleaned_parts)

        # If cleaning resulted in empty text, return original
        return result if result.strip() else description

    except Exception as e:
        logger.warning(f"Error cleaning description: {e}", exc_info=True)
        # Fall back to original description on error
        return description


def search_models(
    query: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    filters: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """
    Search for ML models in the MLentory knowledge graph with faceted navigation.

    This tool searches across model names, descriptions, and keywords using
    Elasticsearch full-text search with advanced faceting capabilities. 
    Results are paginated for efficient retrieval, and descriptions are 
    cleaned to remove tables and overly long sections.

    Args:
        query: Optional text search query. If not provided, returns all models.
               Searches across model name, description, and keywords.
        page: Page number (1-based). Default is 1.
        page_size: Number of results per page (1-100). Default is 20.
        filters: Optional dictionary of filters to apply. Keys are facet names,
                values are lists of filter values to match.
                Available facets: mlTask, license, keywords, platform, sharedBy

    Returns:
        Dictionary containing:
            - models: List of model objects with basic information and cleaned descriptions
            - total: Total number of matching models
            - page: Current page number
            - page_size: Number of results per page
            - has_next: Whether there are more results
            - has_prev: Whether there are previous results
            - facets: Dictionary of facet aggregations with counts
            - filters: Applied filters (echo back)

    Examples:
        >>> # Basic text search
        >>> result = search_models(query="transformer", page=1, page_size=10)
        >>> print(f"Found {result['total']} models")
        >>> 
        >>> # Search with filters
        >>> result = search_models(
        ...     query="bert",
        ...     filters={"mlTask": ["fill-mask"], "license": ["apache-2.0"]}
        ... )
        >>> print(f"Found {result['total']} BERT models for fill-mask with Apache 2.0 license")
        >>> 
        >>> # Filter by platform and shared by
        >>> result = search_models(
        ...     filters={"platform": ["Hugging Face"], "sharedBy": ["google"]}
        ... )
        >>> print(f"Found {result['total']} Google models on Hugging Face")
        >>> 
        >>> # Explore available facet values
        >>> result = search_models(query="nlp")
        >>> print("Available ML tasks:", [f['value'] for f in result['facets']['mlTask']])
        >>> print("Available licenses:", [f['value'] for f in result['facets']['license']])
    """
    try:
        # Validate and constrain parameters
        page = max(1, page)
        page_size = max(1, min(10, page_size))

        # Call the faceted search service
        models, total_count, facet_results = elasticsearch_service.search_models_with_facets(
            query=query or "",
            filters=filters,
            page=page,
            page_size=page_size,
            facets=["mlTask", "license", "keywords", "platform", "sharedBy"],
            facet_size=20,
            facet_query=None,
        )

        # Convert Pydantic models to dictionaries and clean descriptions
        models_list = [
            {
                "db_identifier": model.db_identifier,
                "name": model.name,
                "description": _clean_description(model.description),
                "sharedBy": model.sharedBy,
                "license": model.license,
                "mlTask": model.mlTask,
                "keywords": model.keywords,
                "platform": model.platform,
            }
            for model in models
        ]

        # Convert facet results to dictionaries
        facets_dict = {
            facet_key: [
                {"value": fv.value, "count": fv.count}
                for fv in facet_values
            ]
            for facet_key, facet_values in facet_results.items()
        }

        # Calculate pagination info
        has_next = (page * page_size) < total_count
        has_prev = page > 1
        print(f"Search returned {len(models_list)} models (page {page}/{(total_count + page_size - 1) // page_size})")
        return {
            "models": models_list,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "has_next": has_next,
            "has_prev": has_prev,
            "facets": facets_dict,
            "filters": filters or {},
        }

    except Exception as e:
        logger.error(f"Error searching models: {e}", exc_info=True)
        return {
            "error": str(e),
            "models": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "has_next": False,
            "has_prev": False,
            "facets": {},
            "filters": filters or {},
        }


def get_model_detail(
    model_id: str,
    resolve_properties: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific ML model.

    This tool retrieves comprehensive model information from Elasticsearch and
    optionally fetches related entities from the Neo4j graph database.

    Args:
        model_id: Model identifier (URI or alphanumeric ID).
                 Examples: "https://w3id.org/mlentory/model/abc123" or "abc123"
        resolve_properties: Optional list of relationship types to resolve as full entities.
                          Examples: ["HAS_LICENSE", "author", "dataset"]
                          If not provided, only basic model info is returned.

    Returns:
        Dictionary containing:
            - identifier: List of model URIs
            - name: Model name
            - description: Model description
            - sharedBy: Author/organization
            - license: License identifier
            - mlTask: List of ML tasks
            - keywords: List of keywords/tags
            - platform: Hosting platform
            - related_entities: Dict of related entities (if resolve_properties provided)

    Example:
        >>> # Get basic model info
        >>> model = get_model_detail(model_id="abc123")
        >>> print(f"{model['name']}: {model['description']}")
        >>> 
        >>> # Get model with related entities
        >>> model = get_model_detail(
        ...     model_id="abc123",
        ...     resolve_properties=["HAS_LICENSE", "dataset"]
        ... )
        >>> print(f"License: {model['related_entities']['HAS_LICENSE']}")
    """
    try:
        # Get basic model info from Elasticsearch
        model = elasticsearch_service.get_model_by_id(model_id)
        
        if not model:
            return {
                "error": f"Model not found: {model_id}",
                "identifier": [],
                "name": None,
                "description": None,
            }

        # Build basic response
        model_dict = {
            "identifier": [model.db_identifier],
            "name": model.name,
            "description": model.description,
            "sharedBy": model.sharedBy,
            "license": model.license,
            "mlTask": model.mlTask,
            "keywords": model.keywords,
            "platform": model.platform,
            "related_entities": {},
        }

        # If no properties to resolve, return basic info
        if not resolve_properties:
            return model_dict

        # Get related entities from Neo4j
        try:
            graph_data = graph_service.get_entity_graph(
                entity_id=model_id,
                depth=1,
                relationships=resolve_properties,
                direction="outgoing",
                entity_label="MLModel",
            )

            # Map nodes by ID for easy lookup
            nodes_map = {n.id: n for n in graph_data.nodes}
            start_uri = graph_data.metadata.get("start_uri")

            # Group neighbor nodes by relationship type
            related_entities: Dict[str, List[Dict[str, Any]]] = {}
            
            for edge in graph_data.edges:
                # Only care about edges starting from our model
                if edge.source == start_uri:
                    rel_type = edge.type
                    target_node = nodes_map.get(edge.target)
                    
                    if target_node:
                        if rel_type not in related_entities:
                            related_entities[rel_type] = []
                        
                        # Create entity dict from node properties + uri
                        entity_dict = target_node.properties.copy()
                        entity_dict["uri"] = target_node.id
                        
                        related_entities[rel_type].append(entity_dict)

            model_dict["related_entities"] = related_entities

        except Exception as graph_error:
            logger.warning(f"Error fetching related entities: {graph_error}")
            # Continue with basic model info even if graph query fails
            model_dict["related_entities"] = {"error": str(graph_error)}

        return model_dict

    except Exception as e:
        logger.error(f"Error getting model detail for {model_id}: {e}", exc_info=True)
        return {
            "error": str(e),
            "identifier": [],
            "name": None,
            "description": None,
        }

def get_schema_name_definitions(properties: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Return the name and description of MLModel fields based on input properties.

    Args:
        properties: Optional list of property names to include.
                    If None, returns all fields.

    Returns:
        Dictionary mapping field name -> {"name": <field name>, "description": <field description>}
    
    Example:
        >>> Get definitions for specific properties
        >>> schema_info = get_schema_name_definitions(properties=["name", "description"])
        >>> print(schema_info)
    """
    result: Dict[str, Dict[str, Any]] = {}
    all_schema_properties = MLModel.model_fields.keys()
    try:
        for property in properties:
            if property in all_schema_properties:
                alias = MLModel.model_fields[property].alias
                description = MLModel.model_fields[property].description
                result[property] = {
                    "alias": alias or "",
                    "description": description or "",
                }
        return result
    except Exception as e:
        logger.error(f"Error getting schema name/definitions: {e}", exc_info=True)
        return {"error": str(e)}


def get_related_models_by_entity(
    entity_name: str,
) -> Dict[str, Any]:
    """
    Get the related models by an entity name.

    Args:
        entity_name: Name of the entity (e.g., dataset, license, organization, author, ML task, keyword)    

    Returns:
        Dictionary containing:
            - models: List of related model objects
            - count: Number of related models
    Examples:
        >>> # Get models related to a specific dataset
        >>> result = get_related_models_by_entity(entity_name="ImageNet")
        >>> print(f"Found {result['count']} models related to ImageNet")
        >>> # Get models related to a specific license
        >>> result = get_related_models_by_entity(entity_name="apache-2.0")
        >>> print(f"Found {result['count']} models with Apache 2.0 license")
    """
    logger.info(f"get_related_models_by_entity called: entity_name='{entity_name}'")
    try:
        result = graph_service.find_entity_uri_by_name(entity_name=entity_name)
        if not result:
            return {
                "error": f"Entity not found: {entity_name}",
            }
        result = graph_service.get_models_by_entity_uri(entity_uri=result["uri"])
        
        # Transform results to only include requested fields
        transformed_models = []
        for model in result:
            model_properties = model.get("model_properties", {})
            transformed_models.append({
                "model_name": model.get("model_name") or model_properties.get("schema__name", ""),
                "model_description": model_properties.get("schema__description", ""),
                "shared_by": model_properties.get("fair4ml__sharedBy", ""),
            })
        
        return {
            "models": transformed_models,
            "count": len(transformed_models),
        }
    except Exception as e:
        logger.error(f"Error getting related models by entity: {e}", exc_info=True)
        return {
            "error": str(e),
        }


def clean_query(text: str) -> tuple[List[str], List[str]]:
    """
    Lowercase, remove punctuation (except hyphens), extract quoted phrases, tokenize the rest.

    Args:
        text: Input query string.
    Returns:  
        Tuple of (cleaned_tokens, quoted_phrases)
    Examples:
        >>> tokens, quotes = clean_query('Find "image classification" models with bert-based architectures.')
        >>> print(tokens)  # ['find', 'models', 'bert-based', 'architectures']
        >>> print(quotes)  # ['image classification']
    """

    text = text.lower().strip()
    # Extract quoted phrases first
    quoted_phrases = re.findall(r'"([^"]+)"', text)
    # Remove quoted phrases from main text
    text_no_quotes = re.sub(r'"[^"]+"', '', text)
    # Remove punctuation except hyphens
    text_no_quotes = re.sub(r"[^a-z0-9\-\. ]+", " ", text_no_quotes)
    # Tokenize
    tokens = text_no_quotes.split()
    # Use spaCy to remove stop words
    cleaned_tokens = [
        token for token in tokens
        if len(token) > 2 and token.lower() not in nlp.Defaults.stop_words
    ]
    return cleaned_tokens, quoted_phrases

def pos_tag_tokens(tokens: list) -> list[tuple[str, str]]:
    """
    Return a list of (token_text, pos_tag) tuples.

    Args:
        tokens: List of input tokens.
    Returns:
        List of (token_text, pos_tag) tuples.
    Examples:
        >>> tagged = pos_tag_tokens(['bert-based', 'models', 'classification'])
        >>> print(tagged)  # [('bert-based', 'PROPN'), ('models', 'NOUN'), ('classification', 'NOUN')]  
    """
    doc = nlp(" ".join(tokens))

    merged = []
    buffer = []

    for token in doc:
        if token.text == "-":
            # keep hyphen as part of the token
            buffer.append("-")
        else:
            # if previous buffer contains a word and hyphens, merge them
            if buffer:
                merged[-1] = merged[-1] + "".join(buffer) + token.text
                buffer = []
            else:
                merged.append(token.text)

    return [(t, nlp(t)[0].pos_) for t in merged]


def get_facets():
    """
    Retrieve available facet values from the graph service.
    Returns:
        Dictionary mapping facet name -> list of values
    """
    try:
        facet_schema_raw = graph_service.grouped_facet_values(
            ["fair4ml__mlTask", "schema__keywords", 
             "schema__license", "schema__sharedBy", 
             "fair4ml__trainedOn", "fair4ml__testedOn", 
             "fair4ml__validatedOn", "fair4ml__evaluatedOn"])
        return facet_schema_raw[0]

    except Exception as e:
        logger.error(f"Error fetching facet values: {e}", exc_info=True)
        return {}


def map_to_facets(tagged_tokens:list, quoted_phrases:list) -> tuple[Dict[str, list], list]:
    """
    Map tokens to facet values and clean domain terms using POS tags.
    tagged_tokens: list of (token_text, pos_tag)
    Args:
        tagged_tokens: List of (token_text, pos_tag) tuples.
        quoted_phrases: List of quoted phrases from the original query.
    Returns:
        Tuple of (extracted_facets, domain_terms)
        where extracted_facets is a dict mapping facet name -> list of matched values,
        and domain_terms is a list of remaining domain-specific terms.
    Examples:
        >>> tagged = [('bert-based', 'PROPN'), ('models', 'NOUN'), ('classification', 'NOUN')]
        >>> quotes = ['image classification']
        >>> facets, domain = map_to_facets(tagged, quotes)
        >>> print(facets)  # {'mlTask': ['classification']}
        >>> print(domain)  # ['bert-based', 'image classification'] 
    """

    FACET_SCHEMA = get_facets()
    facet_keys = set(FACET_SCHEMA.keys())
    facet_values_set = set(val for vals in FACET_SCHEMA.values() for val in vals)
    extracted = {facet: [] for facet in facet_keys}
    domain_candidates = []

    for t, pos in tagged_tokens + [(q, "PROPN") for q in quoted_phrases]:
        matched = False

        for facet, values in FACET_SCHEMA.items():
            if t in values:
                extracted[facet].append(t)
                matched = True
                break

        if not matched:
            domain_candidates.append((t, pos))

    domain_terms = [
        term for term, pos in domain_candidates
        if pos in VALID_POS
        and term not in facet_keys
        and term not in facet_values_set
        and term not in TRIVIAL_TOKENS
        and len(term) > 2
    ]

    extracted = {
        facet: list(set(vals))
        for facet, vals in extracted.items()
        if vals
    }
    return extracted, domain_terms

def build_output(ml_tasks, licenses, platforms, providers, keywords, domain_terms):
    """
    Unpacks and builds the final output dictionary.
    Args:      
        ml_tasks: List of ML tasks
        licenses: List of licenses      
        platforms: List of platforms
        providers: List of providers
        keywords: List of keywords
        domain_terms: List of remaining domain-specific terms
    Returns:
        Dictionary with 'query' and 'filters' keys.
    Examples:
        >>> output = build_output(      
        ml_tasks=['classification'],
        licenses=['apache-2.0'],    
        platforms=['Hugging Face'],    
        providers=['google'],    
        keywords=['bert'],    
        domain_terms=['image', 'segmentation']
        )
        >>> print(output)  
        {   'query': 'image segmentation',
            'filters': {
                'task': ['classification'],
                'license': ['apache-2.0'],
                'platform': ['Hugging Face'],
                'sharedBy': ['google'],
                'keywords': ['bert']
            }
        }
    """
    normalized_query = " ".join(domain_terms)

    filters = {}
    if ml_tasks:
        filters["task"] = ml_tasks
    if licenses:
        filters["license"] = licenses
    if platforms:
        filters["platform"] = platforms
    if providers:
        filters["sharedBy"] = providers
    if keywords:
        filters["keywords"] = keywords
    print("Normalized query:", normalized_query, "Filters:", filters)
    return {
        "query": normalized_query.strip(),
        "filters": filters
    }


def normalize_query(user_query: str):
    """
    Helper function to normalize and refine a user query.
    Args:
        user_query: Original user query string.
    Returns:        
        Dictionary with 'query' and 'filters' keys.
    Examples:
        >>> result = normalize_query('Find "image classification" models with bert-based architectures under apache-2.0 license.')
        >>> print(result)   
        {   'query': 'bert-based architectures image classification',
            'filters': {
                'task': ['classification'],
                'license': ['apache-2.0']
            }
        }
    """
    tokens, quoted = clean_query(user_query)
    tagged_tokens = pos_tag_tokens(tokens)
    extracted, domain_terms = map_to_facets(tagged_tokens, quoted)

    ml = extracted.get("mlTask", [])
    lic = extracted.get("license", [])
    plat = extracted.get("platform", [])
    prov = extracted.get("sharedBy", [])
    keywords = extracted.get("keywords", [])
    return build_output(ml, lic, plat, prov, keywords, domain_terms)

