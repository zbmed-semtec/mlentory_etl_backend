"""
Controller for handling related models functionality.

This controller provides methods to find models related to a reference model
using different criteria such as same author, similar tasks, same base models,
overlapping keywords, and different size variants.
"""

from typing import List, Dict, Any, Tuple
import re
from api.dbHandler.SQLHandler import SQLHandler
from api.dbHandler.IndexHandler import IndexHandler
from api.controllers.EntityController import EntityController
from api.controllers.SearchController import SearchController

class RelatedModelsController:
    """
    Controller for finding and managing related models based on various criteria.
    
    This controller provides functionality to discover models that are related
    to a reference model through different relationships such as shared authorship,
    similar tasks, common base models, overlapping keywords, and size variants.
    """
    
    def __init__(
        self, 
        sqlHandler: SQLHandler,
        indexHandler: IndexHandler, 
        entityController: EntityController,
        searchController: SearchController
    ):
        """
        Initialize the RelatedModelsController.
        
        Args:
            sqlHandler (SQLHandler): Handler for SQL database operations.
            indexHandler (IndexHandler): Handler for Elasticsearch operations.
            entityController (EntityController): Controller for entity operations.
        """
        self.sqlHandler = sqlHandler
        self.indexHandler = indexHandler
        self.entityController = entityController
        self.searchController = searchController

    
    def get_related_models_by_property(self, property_id: str, limit: int = 10, offset: int = 0) -> Tuple[int, Dict[str, Dict[str, Any]]]:
        """
        Retrieves models related to a specific property value.
        Args:
            property_id (str): The ID of the property value to search for
        """
        # Get total count
        count_query = f"""
            SELECT COUNT(DISTINCT t.subject) AS count
            FROM "Triplet" t
            JOIN "Version_Range" vr ON t.id = vr.triplet_id
            WHERE t.object = '{property_id}'
            AND vr.deprecated = False
        """
        count_result = self.sqlHandler.query(count_query)
        count = int(count_result.iloc[0]['count'])

        # Get paginated results
        data_query = f"""
            SELECT DISTINCT t.subject AS model_uri
            FROM "Triplet" t
            JOIN "Version_Range" vr ON t.id = vr.triplet_id
            WHERE t.object = '{property_id}'
            AND vr.deprecated = False
            ORDER BY t.subject
            LIMIT {limit} OFFSET {offset}
        """
        
        models_uris = self.sqlHandler.query(data_query, params={
            "property_id": property_id,
            "limit": limit,
            "offset": offset
        })
        
        models_dict = {}
        for _, row in models_uris.iterrows():
            model_uri = row["model_uri"]
            model_details = self.searchController.search_model_by_id(model_uri, extended=True)[0]
            type_value = model_details["type"][0]
            if "MLModel" in type_value or "Run" in type_value or "AI4Life_Model" in type_value:
                models_dict[model_uri] = model_details
                
        return count, models_dict
    
    def get_reference_model(self, model_id: str) -> Dict[str, Any]:
        """
        Retrieve the reference model details.
        
        Args:
            model_id (str): The ID of the reference model.
            
        Returns:
            Dict[str, Any]: The reference model details.
            
        Raises:
            ValueError: If reference model is not found.
            
        Example:
            >>> controller = RelatedModelsController(...)
            >>> model = controller.get_reference_model("model123")
            >>> print(model["name"])
        """
        # Search for the model using the search functionality with extended info to ensure all fields are included
        reference_models = self.searchController.search_model_by_id(model_id, extended=True)
        
        if not reference_models:
            raise ValueError(f"Reference model with ID {model_id} not found")
            
        return reference_models[0]  # Take the first match

    def find_models_by_same_author(
        self, 
        reference_model: Dict[str, Any], 
        extended: bool = False, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find models by the same author(s) as the reference model.
        
        Args:
            reference_model (Dict[str, Any]): The reference model details.
            extended (bool): Whether to include extended information.
            limit (int): Maximum number of models to return.
            
        Returns:
            List[Dict[str, Any]]: List of models by the same author(s).
            
        Raises:
            Exception: If there's an error during the search.
            
        Example:
            >>> models = controller.find_models_by_same_author(ref_model, limit=5)
            >>> print(f"Found {len(models)} models by same author")
        """
        # Handle sharedBy field - it might be stored as a single string or array
        reference_authors_raw = reference_model.get("sharedBy", [])
        reference_authors = []
        if isinstance(reference_authors_raw, list):
            reference_authors = reference_authors_raw
        elif isinstance(reference_authors_raw, str) and reference_authors_raw.strip():
            reference_authors = [reference_authors_raw.strip()]
        
        reference_model_id = reference_model.get("db_identifier", "")
        
        if not reference_authors:
            print("DEBUG: No authors found in reference model, returning empty list")
            return []
            
        try:
            # Use a more flexible query that finds models with ANY of the authors
            # This is more useful than requiring ALL authors to match
            same_author_models = self.searchController.search_models_with_filters(
                query="",
                filters={"sharedBy": reference_authors},
                extended=extended,
                limit=limit + 1  # +1 to account for reference model
            )
            
            # Remove the reference model from results
            filtered_results = [
                model for model in same_author_models 
                if model.get("db_identifier") != reference_model_id
            ]
        
            
            # Apply relevance scoring and sorting
            scored_results = self._score_and_sort_models_by_relevance(
                reference_model, filtered_results
            )
            
            return scored_results[:limit]
            
        except Exception as e:
            print(f"Error finding models by same author: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return []

    def _score_and_sort_models_by_relevance(
        self, 
        reference_model: Dict[str, Any], 
        candidate_models: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Score and sort models by relevance to the reference model.
        
        Args:
            reference_model: The reference model details
            candidate_models: List of candidate models to score
            
        Returns:
            List of models sorted by relevance score (highest first)
        """
        scored_models = []
        
        for model in candidate_models:
            relevance_score = self._calculate_relevance_score(reference_model, model)
            model_copy = model.copy()
            model_copy["relevance_score"] = relevance_score
            scored_models.append(model_copy)
        
        # Sort by relevance score (highest first)
        scored_models.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        return scored_models

    def _calculate_relevance_score(
        self, 
        reference_model: Dict[str, Any], 
        candidate_model: Dict[str, Any]
    ) -> float:
        """
        Calculate relevance score between reference model and candidate model.
        
        Args:
            reference_model: The reference model details
            candidate_model: The candidate model to score
            
        Returns:
            float: Relevance score between 0.0 and 1.0
        """
        score = 0.0
        
        # 1. Task Similarity (40% weight)
        if reference_model.get("mlTask") and candidate_model.get("mlTask"):
            ref_tasks = set(reference_model["mlTask"])
            cand_tasks = set(candidate_model["mlTask"])
            if ref_tasks and cand_tasks:
                common_tasks = ref_tasks & cand_tasks
                task_similarity = len(common_tasks) / max(len(ref_tasks), len(cand_tasks))
                score += task_similarity * 0.4
        
        # 2. Keyword Overlap (25% weight)
        if reference_model.get("keywords") and candidate_model.get("keywords"):
            ref_keywords = set(reference_model["keywords"])
            cand_keywords = set(candidate_model["keywords"])
            if ref_keywords and cand_keywords:
                common_keywords = ref_keywords & cand_keywords
                keyword_similarity = len(common_keywords) / max(len(ref_keywords), len(cand_keywords))
                score += keyword_similarity * 0.25
        
        # 3. Base Model Similarity (20% weight)
        if reference_model.get("baseModels") and candidate_model.get("baseModels"):
            ref_base_models = set(reference_model["baseModels"])
            cand_base_models = set(candidate_model["baseModels"])
            if ref_base_models and cand_base_models:
                common_base_models = ref_base_models & cand_base_models
                base_similarity = len(common_base_models) / max(len(ref_base_models), len(cand_base_models))
                score += base_similarity * 0.2
        
        # 4. Name Similarity (10% weight)
        if reference_model.get("name") and candidate_model.get("name"):
            ref_name = str(reference_model["name"]).lower()
            cand_name = str(candidate_model["name"]).lower()
            if ref_name and cand_name:
                # Simple substring matching
                if ref_name in cand_name or cand_name in ref_name:
                    score += 0.1
        
        # 5. License Compatibility (5% weight)
        if reference_model.get("license") and candidate_model.get("license"):
            ref_license = str(reference_model["license"]).lower()
            cand_license = str(candidate_model["license"]).lower()
            if ref_license and cand_license:
                # Check if both are open source or both are proprietary
                ref_is_open = any(term in ref_license for term in ["mit", "apache", "gpl", "bsd", "open"])
                cand_is_open = any(term in cand_license for term in ["mit", "apache", "gpl", "bsd", "open"])
                if ref_is_open == cand_is_open:
                    score += 0.05
        
        return min(score, 1.0)  # Cap at 1.0

    def find_models_with_similar_tasks(
        self, 
        reference_model: Dict[str, Any], 
        extended: bool = False, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find models with similar ML tasks to the reference model.
        
        Args:
            reference_model (Dict[str, Any]): The reference model details.
            extended (bool): Whether to include extended information.
            limit (int): Maximum number of models to return.
            
        Returns:
            List[Dict[str, Any]]: List of models with similar ML tasks.
            
        Raises:
            Exception: If there's an error during the search.
            
        Example:
            >>> models = controller.find_models_with_similar_tasks(ref_model)
            >>> for model in models:
            ...     print(f"Model: {model['name']}, Tasks: {model['mlTask']}")
        """
        reference_tasks = reference_model.get("mlTask", [])
        reference_model_id = reference_model.get("db_identifier", "")
        
        if not reference_tasks:
            return []
            
        try:
            similar_task_models = self.searchController.search_models_with_filters(
                query="",
                filters={"mlTask": reference_tasks},
                extended=extended,
                limit=limit + 1
            )
            
            return [
                model for model in similar_task_models 
                if model.get("db_identifier") != reference_model_id
            ][:limit]
            
        except Exception as e:
            print(f"Error finding models with similar tasks: {e}")
            return []

    def find_models_with_same_base_models(
        self, 
        reference_model: Dict[str, Any], 
        extended: bool = False, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find models based on the same base models as the reference model.
        
        Args:
            reference_model (Dict[str, Any]): The reference model details.
            extended (bool): Whether to include extended information.
            limit (int): Maximum number of models to return.
            
        Returns:
            List[Dict[str, Any]]: List of models with the same base models.
            
        Raises:
            Exception: If there's an error during the search.
            
        Example:
            >>> models = controller.find_models_with_same_base_models(ref_model)
            >>> for model in models:
            ...     print(f"Model: {model['name']}, Base: {model['baseModels']}")
        """
        reference_base_models = reference_model.get("baseModels", [])
        reference_model_id = reference_model.get("db_identifier", "")
        
        if not reference_base_models:
            return []
            
        try:
            same_base_models = self.searchController.search_models_with_filters(
                query="",
                filters={"baseModels": reference_base_models},
                extended=extended,
                limit=limit + 1
            )
            
            return [
                model for model in same_base_models 
                if model.get("db_identifier") != reference_model_id
            ][:limit]
            
        except Exception as e:
            print(f"Error finding models with same base models: {e}")
            return []

    def find_models_with_overlapping_keywords(
        self, 
        reference_model: Dict[str, Any], 
        extended: bool = False, 
        limit: int = 10,
        max_keywords: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find models with overlapping keywords to the reference model.
        
        Results are sorted by the number of overlapping keywords (most matches first).
        Models with at least one keyword match are considered related.
        
        Args:
            reference_model (Dict[str, Any]): The reference model details.
            extended (bool): Whether to include extended information.
            limit (int): Maximum number of models to return.
            max_keywords (int): Maximum number of keywords to use for matching.
            
        Returns:
            List[Dict[str, Any]]: List of models with overlapping keywords, sorted by overlap count.
            
        Raises:
            Exception: If there's an error during the search.
            
        Example:
            >>> models = controller.find_models_with_overlapping_keywords(
            ...     ref_model, max_keywords=3
            ... )
            >>> print(f"Found {len(models)} models with similar keywords")
        """
        reference_keywords = reference_model.get("keywords", [])
        reference_model_id = reference_model.get("db_identifier", "")
        
        if not reference_keywords:
            return []
            
        try:
            # Use only a subset of keywords to avoid too restrictive filtering
            keyword_subset = reference_keywords[:max_keywords]
            
            # Use Elasticsearch to find models with ANY keyword overlap
            # This ensures we check ALL models in the database, not just a limited sample
            models_with_keyword_matches = self.searchController.search_models_with_filters(
                query="",
                filters={"keywords": keyword_subset},  # Use keywords filter directly
                extended=extended,
                limit=limit * 5  # Get more candidates for better ranking
            )
            
            # Remove the reference model and calculate detailed overlap counts
            models_with_overlap = []
            for model in models_with_keyword_matches:
                if model.get("db_identifier") != reference_model_id:
                    model_keywords = set(model.get("keywords", []))
                    ref_keywords_set = set(keyword_subset)
                    
                    # Calculate overlapping keywords
                    overlapping_keywords = model_keywords & ref_keywords_set
                    overlap_count = len(overlapping_keywords)
                    
                    # Only include models with at least one keyword match
                    if overlap_count > 0:
                        model_copy = model.copy()
                        model_copy["keyword_overlap_count"] = overlap_count
                        model_copy["overlapping_keywords"] = list(overlapping_keywords)
                        models_with_overlap.append(model_copy)
            
            # Sort by overlap count (highest first), then by relevance score
            models_with_overlap.sort(
                key=lambda x: (x["keyword_overlap_count"], x.get("score", 0)), 
                reverse=True
            )
            
            return models_with_overlap[:limit]
            
        except Exception as e:
            print(f"Error finding models with overlapping keywords: {e}")
            return []

    def find_different_size_models(
        self, 
        reference_model: Dict[str, Any], 
        extended: bool = False, 
        limit: int = 10,
        min_score: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Find models that are different sizes/versions of similar models.
        
        This method searches for models with similar names but potentially
        different size indicators (e.g., 7B, 13B, small, large, etc.).
        
        Args:
            reference_model (Dict[str, Any]): The reference model details.
            extended (bool): Whether to include extended information.
            limit (int): Maximum number of models to return.
            min_score (float): Minimum relevance score for matches.
            
        Returns:
            List[Dict[str, Any]]: List of different size models.
            
        Raises:
            Exception: If there's an error during the search.
            
        Example:
            >>> models = controller.find_different_size_models(
            ...     ref_model, min_score=2.0
            ... )
            >>> for model in models:
            ...     print(f"Model: {model['name']}, Score: {model['score']}")
        """
        reference_name = reference_model.get("name", "")
        reference_model_id = reference_model.get("db_identifier", "")
        
        if not reference_name:
            return []
            
        try:
            # Extract base name (remove common size indicators)
            base_name_patterns = [
                r'-\d+[bB]',  # Remove -7B, -13B, etc.
                r'-[Ss]mall',  # Remove -small
                r'-[Mm]edium',  # Remove -medium  
                r'-[Ll]arge',  # Remove -large
                r'-[Xx][Ll]',  # Remove -XL
                r'-v\d+',  # Remove -v1, -v2, etc.
            ]
            
            base_name = reference_name
            for pattern in base_name_patterns:
                base_name = re.sub(pattern, '', base_name)
            
            # Search for models with similar base names
            if len(base_name.strip()) <= 3:  # Skip if base name too short
                return []
                
            different_size_models = self.searchController.search_models_by_phrase(
                query=base_name.strip(),
                extended=extended
            )
            
            # Filter and limit results
            return [
                model for model in different_size_models 
                if (model.get("db_identifier") != reference_model_id and 
                    model.get("score", 0) > min_score)
            ][:limit]
            
        except Exception as e:
            print(f"Error finding different size models: {e}")
            return []

    def get_all_related_models(
        self, 
        reference_model_id: str, 
        extended: bool = False, 
        limit_per_category: int = 10
    ) -> Dict[str, Any]:
        """
        Get models related to a reference model based on all criteria.
        
        This method combines all the different approaches to find related models
        and returns them categorized by relationship type.
        
        Args:
            reference_model_id (str): The ID of the reference model.
            extended (bool): Whether to include extended information for the results.
            limit_per_category (int): Maximum number of models to return per category.
            
        Returns:
            Dict[str, Any]: Dictionary containing different categories of related models:
                - 'sameAuthorModels': Models by the same author(s).
                - 'similarTaskModels': Models with similar ML tasks.
                - 'differentSizeModels': Models that are different sizes/versions.
                - 'sameBaseModels': Models based on the same base models.
                - 'relatedKeywordModels': Models with overlapping keywords.
                
        Raises:
            ValueError: If reference model is not found.
            Exception: If there's an error during any search operation.
            
        Example:
            >>> result = controller.get_all_related_models("model123", limit_per_category=5)
            >>> print(f"Same author: {len(result['related_models']['sameAuthorModels'])}")
            >>> print(f"Total related: {result['total_related']}")
        """
        try:
            # Get reference model details with extended info to ensure keywords are included
            reference_model = self.get_reference_model(reference_model_id)
            
            # Reference model now includes keywords by default
            
            # Initialize result categories
            related_models = {
                "sameAuthorModels": [],
                "similarTaskModels": [], 
                "differentSizeModels": [],
                "sameBaseModels": [],
                "relatedKeywordModels": []
            }
            
            # Find models by each criteria
            related_models["sameAuthorModels"] = self.find_models_by_same_author(
                reference_model, extended, limit_per_category
            )
            
            related_models["similarTaskModels"] = self.find_models_with_similar_tasks(
                reference_model, extended, limit_per_category
            )
            
            related_models["sameBaseModels"] = self.find_models_with_same_base_models(
                reference_model, extended, limit_per_category
            )
            
            related_models["relatedKeywordModels"] = self.find_models_with_overlapping_keywords(
                reference_model, extended, limit_per_category
            )
            
            related_models["differentSizeModels"] = self.find_different_size_models(
                reference_model, extended, limit_per_category
            )
            
            return {
                "reference_model": reference_model,
                "related_models": related_models,
                "total_related": sum(len(models) for models in related_models.values())
            }
            
        except Exception as e:
            print(f"Error finding related models: {e}")
            raise