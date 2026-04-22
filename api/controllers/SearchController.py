from datetime import datetime
import re

from api.dbHandler.IndexHandler import IndexHandler
from api.controllers.EntityController import EntityController
from typing import List, Dict, Any
from api.controllers.LLMController import LLMController

class SearchController:
    def __init__(
        self, indexHandler: IndexHandler, entityController: EntityController,
        llmController: LLMController
    ):
        self.indexHandler = indexHandler
        self.entityController = entityController
        self.llmController = llmController

    def list_all_models(self, limit: int = 50, extended: bool = False, page: int = 1):
        """
        Retrieves a list of all models from the databases using the modern faceted search approach.
        
        This method now uses the same underlying faceted search infrastructure for consistency.
        It performs a match_all query with default facets to show all models.
        
        Args:
            limit (int): The maximum number of models to retrieve per page.
            extended (bool): Whether to include extended information for the results.
            page (int): Page number (1-indexed) for pagination.
            
        Returns:
            Dict[str, Any]: A dictionary containing:
                - 'models': List of models for the current page.
                - 'total': Total number of models found.
                - 'facets': Dynamic facet aggregations with counts.
                - 'facet_config': Configuration metadata for default facets.
                
        Example:
            >>> controller.list_all_models(limit=20, page=1)
            {
                "models": [...],
                "total": 1500,
                "facets": {
                    "mlTask": [{"value": "text-classification", "count": 300}],
                    "license": [{"value": "MIT", "count": 250}]
                },
                "facet_config": {...}
            }
        """
        # Use the new faceted search method with empty query (match_all)
        # This ensures consistency with the main search functionality
        return self.search_models_with_facets(
            query="",  # Empty query = match_all
            filters={},  # No filters = all models
            extended=extended,
            limit=limit,
            page=page,
            facets=["mlTask", "license", "keywords", "platform", "dateCreated"],  # Default facets including date
            facet_size=100,  # Larger size for initial load
            facet_query={}  # No facet search queries
        )

    def search_models_by_phrase(self, query: str, extended: bool = False):
        """
        Searches for models based on a given phrase.
        Args:
            query (str): The search phrase.
            extended (bool): Whether to include extended information for the results.
        Returns:
            List[Dict[str, Any]]: A json object containing the list of models.
        """

        indexes = self.indexHandler.list_indexes()

        result_models = []

        for index_name in indexes:
            search_query = {
                "size": 50,
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["name^3", "releaseNotes^2", "mlTask", "sharedBy"],
                        "fuzziness": "AUTO",
                    }
                },
            }

            results = self.indexHandler.search(index_name, search_query)

            formatted_results = []
            for hit in results:
                result_entity = {
                    "score": hit["_score"],
                    "name": hit["_source"].get("name", ""),
                    "mlTask": hit["_source"].get("mlTask", []),
                    "sharedBy": hit["_source"].get("sharedBy", []),
                    "db_identifier": hit["_source"].get("db_identifier", ""),
                    "keywords": hit["_source"].get("keywords", []),
                    "baseModels": hit["_source"].get("baseModels", []),
                    "relatedDatasets": hit["_source"].get("relatedDatasets", []),
                    "license": hit["_source"].get("license", []),
                    "description": hit["_source"].get("description", ""),
                }

                if extended:
                    result_entity.update(self.entityController.get_entity_details(result_entity["db_identifier"]))

                # print("Result Entity:")
                # print(result_entity)
                formatted_results.append(result_entity)
                # print("\n")

            result_models.extend(formatted_results)

        return result_models

    def search_model_by_id(self, model_id: str, extended: bool = False):
        """
        Searches for a model based on a given model ID.
        Args:
            model_id (str): The ID of the model to search for.
            extended (bool): Whether to include extended information for the results.
        Returns:
            List[Dict[str, Any]]: A json object containing the list of models.
        """

        indexes = self.indexHandler.list_indexes()

        result_combined = []

        for index_name in indexes:
            search_query = {"size": 1, "query": {"term": {"db_identifier": model_id}}}

            results = self.indexHandler.search(index_name, search_query)

            results_per_index = []
            for hit in results:
                result_entity = {
                    "score": hit["_score"],
                    "name": hit["_source"].get("name", ""),
                    "releaseNotes": hit["_source"].get("releaseNotes", ""),
                    "relatedDatasets": hit["_source"].get("relatedDatasets", []),
                    "mlTask": hit["_source"].get("mlTask", []),
                    "sharedBy": hit["_source"].get("sharedBy", []),
                    "db_identifier": hit["_source"].get("db_identifier", ""),
                    "keywords": hit["_source"].get("keywords", []),
                    "baseModels": hit["_source"].get("baseModels", []),
                    "license": hit["_source"].get("license", []),
                    "description": hit["_source"].get("description", ""),
                }
                
                if extended:
                    extended_entity = self.entityController.get_entity_details(hit["_source"].get("db_identifier", ""))
                    result_entity.update(extended_entity)
               
                results_per_index.append(result_entity)
                
            result_combined.extend(results_per_index)
            
        return result_combined

    def search_models_with_filters(
                                        self, 
                                        query: str = "", 
                                        filters: Dict[str, List[str]] = None,
                                        extended: bool = False,
                                        limit: int = 50
                                    ) -> List[Dict[str, Any]]:
        """
        Search for models with text query and property filters.
        
        Args:
            query (str): Optional text search query
            filters (Dict[str, List[str]]): Dictionary of property names and their allowed values
            extended (bool): Whether to include extended information
            limit (int): Maximum number of results to return
            
        Returns:
            List[Dict[str, Any]]: List of matching models
        """
        indexes = self.indexHandler.list_indexes()
        result_models = []
        print("Indexes available:")
        print(indexes)
        for index_name in indexes:
            print(f"Searching index: {index_name}")
            # Build elasticsearch query
            must_conditions = []
            
            # Add text search if query provided
            if query:
                must_conditions.append({
                    "multi_match": {
                        "query": query,
                        "fields": ["name^3", "releaseNotes^2", "mlTask", "sharedBy"],
                        "fuzziness": "AUTO"
                    }
                })
            
            # Add filters if provided
            if filters:
                print("\nWatching filters:")
                for prop, values in filters.items():
                    print(f"Property: {prop}, Values: {values}")
                    if values:  
                        if type(values) == list:
                            # Special handling for sharedBy field to find ANY author match
                            if prop == "sharedBy":
                                # Use should clause to find models with ANY of the authors
                                # Since sharedBy is Text() field, use match instead of term with .keyword
                                should_conditions = []
                                for author in values:
                                    # Use fuzzy matching to find similar author names
                                    should_conditions.extend([
                                        {
                                            "match": {
                                                "sharedBy": {
                                                    "query": author,
                                                    "operator": "or",
                                                    "fuzziness": "AUTO"
                                                }
                                            }
                                        },
                                        {
                                            "wildcard": {
                                                "sharedBy": f"*{author}*"
                                            }
                                        }
                                    ])
                                must_conditions.append({
                                    "bool": {
                                        "should": should_conditions,
                                        "minimum_should_match": 1
                                    }
                                })
                                print(f"DEBUG: Added fuzzy match filter for {prop} with values: {values}")
                            else:
                                # Handle Keyword fields specially since they don't need .keyword suffix
                                if prop in ["keywords", "mlTask", "baseModels"]:
                                    must_conditions.append({
                                        "terms": {
                                            prop: values  # Use field directly without .keyword suffix
                                        }
                                    })
                                    print(f"DEBUG: Added {prop} filter with values: {values}")
                                else:
                                    # Default behavior for other fields
                                    prop = prop+".keyword"
                                    must_conditions.append({
                                        "terms": {
                                            prop: values
                                        }
                                    })
                                    print(f"DEBUG: Added terms filter for {prop} with values: {values}")
                        else:
                            must_conditions.append({
                                "match": {
                                    prop: values
                                }
                            })
                            print(f"DEBUG: Added match filter for {prop} with value: {values}")

            # Construct final query
            search_query = {
                "size": limit,
                "query": {
                    "bool": {
                        "must": must_conditions if must_conditions else [{"match_all": {}}]
                    }
                }
            }
            

            try:
                results = self.indexHandler.search(index_name, search_query)

                formatted_results = []
                for hit in results:
                    # Handle sharedBy field - it might be stored as a single string or array
                    shared_by_raw = hit["_source"].get("sharedBy", "")
                    shared_by = []
                    if isinstance(shared_by_raw, list):
                        shared_by = shared_by_raw
                    elif isinstance(shared_by_raw, str) and shared_by_raw.strip():
                        shared_by = [shared_by_raw.strip()]
                    
                    result_entity = {
                        "score": hit["_score"],
                        "name": hit["_source"].get("name", ""),
                        "mlTask": hit["_source"].get("mlTask", []),
                        "sharedBy": shared_by,
                        "db_identifier": hit["_source"].get("db_identifier", ""),
                        "keywords": hit["_source"].get("keywords", []),
                        "baseModels": hit["_source"].get("baseModels", []),
                        "relatedDatasets": hit["_source"].get("relatedDatasets", []),
                        "license": hit["_source"].get("license", []),
                        "description": hit["_source"].get("description", "")
                    }
                    

                    if extended:
                        result_entity.update(self.entityController.get_entity_details(result_entity["db_identifier"]))

                    formatted_results.append(result_entity)

                result_models.extend(formatted_results)
            except Exception as e:
                print(f"Error searching index {index_name}: {e}")
                print(f"Detailed error traceback: {traceback.format_exc()}")
                continue

        return result_models


    def search_models_with_pagination_and_filters(
        self,
        query: str = "",
        filters: Dict[str, List[str]] = None,
        extended: bool = False,
        limit: int = 50,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Search for models with text query and property filters, with pagination support.
        
        Args:
            query (str): Optional text search query.
            filters (Dict[str, List[str]]): Dictionary of property names and 
                                           their allowed values.
            extended (bool): Whether to include extended information.
            limit (int): Maximum number of results per page.
            page (int): The page number to return (1-indexed).
            
        Returns:
            Dict[str, Any]: Dictionary with keys:
                - 'models': List of matching models for the current page.
                - 'total': Total number of models matching the query and filters.
                - 'filter_counts': Aggregation counts for 'mlTask', 'license', 'keywords'.
        """
        all_indices = self.indexHandler.list_indexes()

        model_indices = [idx for idx in all_indices if idx.endswith("_models")]

        if not model_indices:
            return {"models": [], "total": 0, "filter_counts": {}}

        target_indices_str = ",".join(model_indices)
        
        result_models = []
        from_offset = (page - 1) * limit

        must_conditions = []
        
        if query:
            must_conditions.append({
                "multi_match": {
                    "query": query,
                    "fields": ["name^3", "releaseNotes^2", "mlTask", "sharedBy"],
                    "fuzziness": "AUTO"
                }
            })
        
        if filters:
            for prop, values in filters.items():
                if values:  
                    if isinstance(values, list):
                        # Ensure .keyword for terms query on text fields if not already specified
                        prop_keyword = prop if prop.endswith(".keyword") else prop + ".keyword"
                        must_conditions.append({
                            "terms": {
                                prop_keyword: values
                            }
                        })
                    else: # Single value match
                        must_conditions.append({
                            "match": {
                                prop: values
                            }
                        })
        
        search_query = {
            "from": from_offset,
            "size": limit,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": must_conditions if must_conditions else [{"match_all": {}}]
                }
            },
            "aggs": {
                "mlTask_counts": {"terms": {"field": "mlTask.keyword", "size": 100}},
                "license_counts": {"terms": {"field": "license.keyword", "size": 100}},
                "keywords_counts": {"terms": {"field": "keywords.keyword", "size": 300}}
            }
        }
        
        total_hits = 0
        aggregation_results = {}
        try:
            # The indexHandler.search should return the full Elasticsearch response or at least hits and total
            es_response = self.indexHandler.search_complete_response(target_indices_str, search_query)

            # If indexHandler.search returns only hits, we need to get the full response
            hits = es_response.get("hits", {})
            total = hits.get("total", 0)
            # ES 7.x+ returns total as an object: {"value": int, "relation": "eq"}
            if isinstance(total, dict):
                total_hits = total.get("value", 0)
            else:
                total_hits = total

            # Process aggregations
            if "aggregations" in es_response:
                aggs_data = es_response["aggregations"]
                if "mlTask_counts" in aggs_data:
                    aggregation_results["mlTask"] = [
                        {"value": bucket["key"], "count": bucket["doc_count"]}
                        for bucket in aggs_data["mlTask_counts"]["buckets"]
                    ]
                if "license_counts" in aggs_data:
                    aggregation_results["license"] = [
                        {"value": bucket["key"], "count": bucket["doc_count"]}
                        for bucket in aggs_data["license_counts"]["buckets"]
                    ]
                if "keywords_counts" in aggs_data:
                    aggregation_results["keywords"] = [
                        {"value": bucket["key"], "count": bucket["doc_count"]}
                        for bucket in aggs_data["keywords_counts"]["buckets"]
                    ]

            formatted_results = []
            for hit in hits.get("hits", []):
                source = hit.get("_source", {})
                
                # Handle sharedBy field - it might be stored as a single string or array
                shared_by_raw = source.get("sharedBy", "")
                shared_by = []
                if isinstance(shared_by_raw, list):
                    shared_by = shared_by_raw
                elif isinstance(shared_by_raw, str) and shared_by_raw.strip():
                    shared_by = [shared_by_raw.strip()]
                
                result_entity = {
                    "score": hit.get("_score", 0),
                    "name": source.get("name", ""),
                    "mlTask": source.get("mlTask", []),
                    "sharedBy": shared_by,
                    "db_identifier": source.get("db_identifier", ""),
                    "keywords": source.get("keywords", []),
                    "baseModels": source.get("baseModels", []),
                    "relatedDatasets": source.get("relatedDatasets", []),
                    "license": source.get("license", []),
                    "description": source.get("description", ""),
                }

                if extended:
                    result_entity.update(self.entityController.get_entity_details(result_entity["db_identifier"]))

                formatted_results.append(result_entity)
            result_models = formatted_results

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error searching indices {target_indices_str} with pagination: {e}")
            print(f"Detailed error traceback: {error_details}")
            result_models = []  # Initialize with empty list on error
            total_hits = 0 # Ensure total is 0 on error
        
        return {"models": result_models, "total": total_hits, "filter_counts": aggregation_results}

    def search_models_with_pagination_and_filters_with_pit(
        self,
        query: str = "",
        filters: Dict[str, List[str]] = None,
        extended: bool = False,
        limit: int = 50,
        pit_id: str = None,
        search_after_values: List[Any] = None
    ) -> Dict[str, Any]:
        """
        Search for models with text query and property filters, with pagination support using PIT and search_after.
        
        Args:
            query (str): Optional text search query.
            filters (Dict[str, List[str]]): Dictionary of property names and their allowed values.
            extended (bool): Whether to include extended information.
            limit (int): Maximum number of results per page.
            pit_id (str): The Point in Time ID for pagination. If None, a new one is created.
            search_after_values (List[Any]): Values from the previous page's last hit to start the search from.
            
        Returns:
            Dict[str, Any]: Dictionary with keys:
                - 'models': List of matching models for the current page.
                - 'total': Total number of models matching the query and filters.
                - 'pit_id': The Point in Time ID to use for the next page.
                - 'search_after_values': The search_after values for the next page.
                - 'filter_counts': Aggregation counts for 'mlTask', 'license', 'keywords'.
        """
        all_indices = self.indexHandler.list_indexes()
        model_indices = [idx for idx in all_indices if idx.endswith("_models")]

        if not model_indices:
            return {"models": [], "total": 0, "filter_counts": {}, "pit_id": None, "search_after_values": None}

        target_indices_str = ",".join(model_indices)

        # Open a new PIT if one is not provided (first request)
        if pit_id is None:
            pit_id = self.indexHandler.open_pit(index_name=target_indices_str)

        must_conditions = []
        if query:
            must_conditions.append({
                "multi_match": {
                    "query": query,
                    "fields": ["name^3", "releaseNotes^2", "mlTask", "sharedBy"],
                    "fuzziness": "AUTO"
                }
            })
        
        if filters:
            for prop, values in filters.items():
                if values:
                    if isinstance(values, list):
                        prop_keyword = prop if prop.endswith(".keyword") else prop + ".keyword"
                        must_conditions.append({"terms": {prop_keyword: values}})
                    else:
                        must_conditions.append({"match": {prop: values}})
        
        search_query = {
            "size": limit,
            "query": {
                "bool": {
                    "must": must_conditions if must_conditions else [{"match_all": {}}]
                }
            },
            "pit": {
                "id": pit_id,
                "keep_alive": "1m"
            },
            "sort": [
                {"_score": {"order": "desc"}},
                {"_doc": {"order": "asc"}} # Tie-breaker
            ],
            "aggs": {
                "mlTask_counts": {"terms": {"field": "mlTask.keyword", "size": 100}},
                "license_counts": {"terms": {"field": "license.keyword", "size": 100}},
                "keywords_counts": {"terms": {"field": "keywords.keyword", "size": 300}}
            },
            "track_total_hits": True
        }

        if search_after_values:
            search_query["search_after"] = search_after_values
        
        total_hits = 0
        aggregation_results = {}
        result_models = []
        last_hit_sort = None

        try:
            es_response = self.indexHandler.search_complete_response(target_indices_str, search_query)
            
            hits_data = es_response.get("hits", {})
            total = hits_data.get("total", {})
            total_hits = total.get("value", 0) if isinstance(total, dict) else total

            # Process aggregations
            if "aggregations" in es_response:
                aggs_data = es_response["aggregations"]
                aggregation_results["mlTask"] = [{"value": b["key"], "count": b["doc_count"]} for b in aggs_data.get("mlTask_counts", {}).get("buckets", [])]
                aggregation_results["license"] = [{"value": b["key"], "count": b["doc_count"]} for b in aggs_data.get("license_counts", {}).get("buckets", [])]
                aggregation_results["keywords"] = [{"value": b["key"], "count": b["doc_count"]} for b in aggs_data.get("keywords_counts", {}).get("buckets", [])]

            hits = hits_data.get("hits", [])
            if hits:
                last_hit_sort = hits[-1].get("sort")

            for hit in hits:
                source = hit.get("_source", {})
                
                # Handle sharedBy field - it might be stored as a single string or array
                shared_by_raw = source.get("sharedBy", "")
                shared_by = []
                if isinstance(shared_by_raw, list):
                    shared_by = shared_by_raw
                elif isinstance(shared_by_raw, str) and shared_by_raw.strip():
                    shared_by = [shared_by_raw.strip()]
                
                result_entity = {
                    "score": hit.get("_score", 0),
                    "name": source.get("name", ""),
                    "mlTask": source.get("mlTask", []),
                    "sharedBy": shared_by,
                    "db_identifier": source.get("db_identifier", ""),
                    "keywords": source.get("keywords", []),
                    "baseModels": source.get("baseModels", []),
                    "relatedDatasets": source.get("relatedDatasets", []),
                    "license": source.get("license", []),
                    "description": source.get("description", ""),
                }

                if extended:
                    result_entity.update(self.entityController.get_entity_details(result_entity["db_identifier"]))
                
                result_models.append(result_entity)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error searching indices {target_indices_str} with pagination: {e}")
            print(f"Detailed error traceback: {error_details}")
            # Reset results on error
            result_models = []
            total_hits = 0
            pit_id = None
            last_hit_sort = None
        
        return {
            "models": result_models, 
            "total": total_hits, 
            "pit_id": pit_id,
            "search_after_values": last_hit_sort,
            "filter_counts": aggregation_results
        }


    # def get_search_filters(self, property_names: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    #     """
        
    #     Creates the filter information for each property in the list.
        
    #     Args:
    #         property_names (List[str]): List of property names to get filter values for (e.g., ['mlTask', 'license']).

    #     Returns:
    #         Dict[str, List[Dict[str, Any]]]: A dictionary where keys are property names and values are lists of the different entity values for that property,
    #         if an entity has information beyond its name it will be included in the response.
    #     """
        
    
    def handle_search_conversation(
        self, 
        user_message: str, 
        conversation_history: List[Dict[str, str]],
        extended: bool = False, 
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Handles a turn in the conversational search process.

        Uses the LLMController to understand the user query in context, 
        refine it, suggest filters, and potentially execute a search.

        Args:
            user_message (str): The latest message from the user.
            conversation_history (List[Dict[str, str]]): The history of the 
                conversation (list of {'role': 'user'/'assistant', 'content': ...}).
            extended (bool): Whether to include extended information in search results.
            limit (int): Maximum number of search results to return if a search is performed.

        Returns:
            Dict[str, Any]: A dictionary containing the LLM's response, suggestions,
                           state, and potentially search results.
                           Keys: "llm_response", "suggested_filters", "refined_query", 
                                 "conversation_state", "search_results".
        """
        
        # --- Fetch available filter values --- 
        available_filters = {}
        # try:
        #     # Fetch and format mlTask values
        #     # Extract user-friendly names or the values themselves
        #     mltask_details = self.entityController.get_distinct_property_values_with_entity_details("mlTask")[0]
        #     available_filters["mlTask"] = [
        #         str(details.get("name", value)).lower().replace("_", " ") # Use 'name' if available, else the raw value
        #         for value, details in mltask_details.items()
        #     ]
            
        #     # Fetch and format keywords values
        #     keywords_details = self.entityController.get_distinct_property_values_with_entity_details("keywords")[0]
        #     available_filters["keywords"] = [
        #         str(details.get("name", value)).lower().replace("_", " ")
        #         for value, details in keywords_details.items()
        #     ]
            
        #     # Fetch and format license values
        #     license_details = self.entityController.get_distinct_property_values_with_entity_details("license")[0]
        #     available_filters["license"] = [
        #         str(details.get("name", value)).lower().replace("_", " ")
        #         for value, details in license_details.items()
        #     ]
            
        #     # You could add more filters here, e.g., "license"
        #     # license_details = self.entityController.get_distinct_property_values_with_entity_details("license")
        #     # available_filters["license"] = [details.get("name", value) for value, details in license_details.items()]

        #     print(f"Providing available filters to LLM: {available_filters}") # Debug print

        # except Exception as e:
        #     print(f"Warning: Could not fetch distinct property values for LLM filters: {e}")
        #     available_filters = None # Proceed without filters if fetching fails
        # # --- End Fetch available filter values ---

        
        llm_analysis = self.llmController.process_search_conversation_turn(
            user_message=user_message,
            conversation_history=conversation_history,
            available_filters=available_filters
        )

        search_results = None
        refined_query = llm_analysis.get("refined_query", "")
        suggested_filters = llm_analysis.get("suggested_filters", {})
        conversation_state = llm_analysis.get("state", "unknown")

        # Decide whether to perform a search based on LLM state and refined query
        if conversation_state == "ready_to_search" and refined_query:
            try:
                # Note: This currently uses the suggested_filters directly. 
                # A more complex flow might involve user confirmation of filters first.
                search_results = self.search_models_with_filters(
                    query=refined_query,
                    filters=suggested_filters, 
                    extended=extended,
                    limit=3
                )
            except Exception as e:
                print(f"Error performing search after LLM analysis: {e}")
                # Optionally inform the user via llm_response or state
                llm_analysis["response"] += "\n(Note: I tried searching based on our conversation, but encountered an error.)"
                conversation_state = "search_error"


        # Construct the final response for the API layer
        return {
            "llm_response": llm_analysis.get("response", "Sorry, I couldn't process that."),
            "suggested_filters": suggested_filters,
            "refined_query": refined_query,
            "conversation_state": conversation_state,
            "search_results": search_results if search_results is not None else [],
        }

    def get_facets_config(self) -> Dict[str, Any]:
        """
        Get configuration for all available facets.
        
        Returns:
            Dict[str, Any]: Configuration for each facet including metadata like:
                - field: The elasticsearch field name
                - label: Human-readable label
                - type: Data type (keyword, boolean, number, date)
                - icon: UI icon identifier
                - is_high_cardinality: Whether this facet has many values
                - default_size: Default number of values to fetch
                - supports_search: Whether facet supports search within values
                - pinned: Whether facet should be visible by default
        
        Example:
            >>> controller.get_facets_config()
            {
                "mlTask": {
                    "field": "mlTask",
                    "label": "ML Tasks",
                    "type": "keyword",
                    "icon": "mdi-brain",
                    "is_high_cardinality": False,
                    "default_size": 20,
                    "supports_search": True,
                    "pinned": True
                }
            }
        """
        return {
            "mlTask": {
                "field": "mlTask",
                "label": "ML Tasks",
                "type": "keyword",
                "icon": "mdi-brain",
                "is_high_cardinality": False,
                "default_size": 10,
                "supports_search": True,
                "pinned": True
            },
            "license": {
                "field": "license", 
                "label": "Licenses",
                "type": "keyword",
                "icon": "mdi-license",
                "is_high_cardinality": False,
                "default_size": 10,
                "supports_search": True,
                "pinned": True
            },
            "keywords": {
                "field": "keywords",
                "label": "Keywords", 
                "type": "keyword",
                "icon": "mdi-tag",
                "is_high_cardinality": True,
                "default_size": 20,
                "supports_search": True,
                "pinned": True
            },
            "sharedBy": {
                "field": "sharedBy",
                "label": "Shared By",
                "type": "keyword", 
                "icon": "mdi-account-group",
                "is_high_cardinality": True,
                "default_size": 10,
                "supports_search": True,
                "pinned": False
            },
            "baseModels": {
                "field": "baseModels",
                "label": "Base Models",
                "type": "text",
                "icon": "mdi-source-branch",
                "is_high_cardinality": True,
                "default_size": 10,
                "supports_search": True,
                "pinned": False
            },
            "relatedDatasets": {
                "field": "relatedDatasets", 
                "label": "Related Datasets",
                "type": "keyword",
                "icon": "mdi-database",
                "is_high_cardinality": True,
                "default_size": 10,
                "supports_search": True,
                "pinned": False
            },
            "platform": {
                "field": "platform",
                "label": "Platform",
                "type": "keyword",
                "icon": "mdi-cloud",
                "is_high_cardinality": True,
                "supports_search": False,
                "pinned": True
            },
            "dateCreated": {
                "field": "dateCreated",
                "label": "Date Created",
                "type": "date",
                "icon": "mdi-calendar",
                "is_high_cardinality": False,
                "default_size": 10,
                "supports_search": False,
                "pinned": True
            }
        }

    def _build_text_search_query(self, query: str) -> Dict[str, Any]:
        """Builds the text search part of the Elasticsearch query."""
        if not query:
            return None

        # Split into individual words
        individual_words = re.split(r'[ \-_\.]', query)
        individual_words.extend(re.split(r'[ \-_\.]', query.lower()))

        # Create pairs of consecutive words
        paired_words = []
        for i in range(len(individual_words)-1):
            paired_words.append(f"{individual_words[i]} {individual_words[i+1]}")
        
        # Combine individual words and pairs
        query_words = paired_words
        query_words.append(query)
        
        # Remove duplicates and empty strings
        query_words = list(set([word.strip() for word in query_words if word.strip()]))
        should_conditions = []
        
        print(f"\n\n\n\n\n Query words : {query_words}\n\n\n\n\n")
        
        
        for word in query_words:
            # 2. Cross-field matching (words can be in different fields)
            should_conditions.append({
                "multi_match": {
                    "query": word,
                    "fields": [
                        "name^2", "keywords^5", "description^2.5",
                        "mlTask^1", "sharedBy^1"
                    ],
                    "type": "cross_fields",
                    "operator": "or",
                    "analyzer": "standard"
                }
            })
            
            # 3. Best fields matching with OR operator (most flexible)
            should_conditions.append({
                "multi_match": {
                    "query": word,
                    "fields": [
                        "name^2", "keywords^4", "description^2.5",
                        "mlTask^1", "sharedBy^1"
                    ],
                    "type": "best_fields",  
                    "operator": "or",
                    "analyzer": "standard",
                    "boost": 0.8
                }
            })
        
             # 4. Partial keyword matching for each word in the query
            if len(word) >= 2:
                should_conditions.append({"wildcard": {"keywords": f"*{word}*"}})
                should_conditions.append({"wildcard": {"mlTask": f"*{word}*"}})
                # should_conditions.append({"wildcard": {"name": f"*{word}*"}})
                # should_conditions.append({"wildcard": {"description": f"*{word}*"}})
        
        # # 5. Partial keyword matching for the whole query (compound terms)
        # if len(query) >= 3:
        #     should_conditions.append({"wildcard": {"keywords": f"*{query.lower().replace(' ', '*')}*"}})
        #     should_conditions.append({"wildcard": {"mlTask": f"*{query.lower().replace(' ', '*')}*"}})
        #     should_conditions.append({"wildcard": {"name": f"*{query.lower().replace(' ', '*')}*"}})
        #     should_conditions.append({"wildcard": {"description": f"*{query.lower().replace(' ', '*')}*"}})`
        
        
        return {
            "bool": {
                "should": should_conditions,
                "minimum_should_match": 1
            }
        }

    def _build_filter_conditions(self, filters: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """Builds the filter conditions for the Elasticsearch query."""
        must_conditions = []
        if not filters:
            return must_conditions

        for prop, values in filters.items():
            if not values:
                continue

            config = self.get_facets_config().get(prop, {})
            field_type = config.get("type", "text")

            if field_type == "date":
                date_values = values if isinstance(values, list) else [values]
                for date_filter in date_values:
                    if "," in str(date_filter):
                        parts = str(date_filter).split(",")
                        from_date, to_date = (parts[0].strip() or None), (parts[1].strip() if len(parts) > 1 else None)
                        
                        range_query = {"range": {prop: {}}}
                        if from_date:
                            range_query["range"][prop]["gte"] = int(datetime.strptime(from_date, "%Y-%m-%d").timestamp() * 1000)
                        if to_date:
                            range_query["range"][prop]["lte"] = int(datetime.strptime(f"{to_date} 23:59:59", "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
                        must_conditions.append(range_query)
                    else:
                        timestamp = int(datetime.strptime(str(date_filter), "%Y-%m-%d").timestamp() * 1000)
                        must_conditions.append({"term": {prop: timestamp}})
            else:
                if isinstance(values, list):
                    prop_keyword = prop if field_type == "keyword" else (prop if prop.endswith(".keyword") else f"{prop}.keyword")
                    for value in values:
                        must_conditions.append({"term": {prop_keyword: value}})
                else:
                    must_conditions.append({"match": {prop: values}})
        
        return must_conditions

    def _build_facet_aggregations(self, facets: List[str], facet_size: int, facet_query: Dict[str, str]) -> Dict[str, Any]:
        """Builds the facet aggregations for the Elasticsearch query."""
        aggs = {}
        facet_config = self.get_facets_config()
        
        for facet in facets:
            config = facet_config.get(facet, {})
            field_name = config.get("field", facet)
            field_type = config.get("type", "text")
            
            if field_type == "date":
                aggs[f"{facet}_facet"] = {
                    "date_histogram": {
                        "field": field_name,
                        "calendar_interval": "month",
                        "format": "yyyy-MM-dd",
                        "order": {"_key": "desc"}
                    }
                }
            else:
                field_keyword = field_name if field_type == "keyword" else (field_name if field_name.endswith(".keyword") else f"{field_name}.keyword")
                
                terms_agg = {
                    "field": field_keyword,
                    "size": facet_size,
                    "order": {"_count": "desc"}
                }
                
                search_term = facet_query.get(facet)
                if search_term:
                    escaped_term = re.escape(search_term.lower())
                    terms_agg["include"] = f".*{escaped_term}.*"
                
                aggs[f"{facet}_facet"] = {"terms": terms_agg}
                
        return aggs

    def search_models_with_facets(
                                    self,
                                    query: str = "",
                                    filters: Dict[str, List[str]] = None,
                                    extended: bool = False,
                                    limit: int = 50,
                                    page: int = 1,
                                    facets: List[str] = None,
                                    facet_size: int = 20,
                                    facet_query: Dict[str, str] = None
                                ) -> Dict[str, Any]:
        """
        Search for models with enhanced multi-word support and dynamic facets.
        
        This method implements advanced text search with multiple flexible matching strategies:
        - Exact phrase matching across all fields (highest priority)
        - Cross-field matching (words can be in different fields)
        - Best-field matching with flexible OR operators
        - Partial keyword and mlTask matching for each word
        - Individual word matching with fuzzy tolerance
        - Special emphasis on mlTask field for task-related queries
        
        The search is designed for high recall - it will find matches even for terms
        like "Image segmentation" or "Vision Models" by using multiple search approaches.
        All matching is case-insensitive and supports dynamic facets.
        
        Args:
            query (str): Text search query (supports multi-word phrases)
            filters (Dict[str, List[str]]): Property filters to apply to the search
            extended (bool): Whether to include extended information for results
            limit (int): Maximum number of results per page
            page (int): Page number (1-indexed)
            facets (List[str]): List of facet field names to aggregate
            facet_size (int): Maximum number of values per facet
            facet_query (Dict[str, str]): Search queries for specific facets
            
        Returns:
            Dict[str, Any]: Dictionary with keys:
                - 'models': List of models for current page
                - 'total': Total number of matching models
                - 'facets': Dynamic facet aggregations with counts
                - 'facet_config': Configuration metadata for requested facets
        
        Raises:
            Exception: If Elasticsearch query fails or indices are unavailable
            
        Example:
            >>> controller.search_models_with_facets(
            ...     query="image classification",
            ...     filters={"license": ["MIT"]},
            ...     facets=["mlTask", "keywords"],
            ...     facet_query={"keywords": "medical"}
            ... )
            {
                "models": [...],
                "total": 150,
                "facets": {
                    "mlTask": [{"value": "image-classification", "count": 120}],
                    "keywords": [{"value": "medical", "count": 45}]
                },
                "facet_config": {...}
            }
        """
        all_indices = self.indexHandler.list_indexes()
        model_indices = [idx for idx in all_indices if idx.endswith("_models")]

        if not model_indices:
            return {
                "models": [], 
                "total": 0, 
                "facets": {},
                "facet_config": self.get_facets_config()
            }

        target_indices_str = ",".join(model_indices)
        from_offset = (page - 1) * limit
        

        # Default facets if none specified
        if facets is None:
            facets = ["mlTask", "license", "keywords", "platform", "dateCreated"]
        
        facet_query = facet_query or {}

        # Build query conditions using helper methods
        must_conditions = []
        if query:
            must_conditions.append(self._build_text_search_query(query))
        
        if filters:
            must_conditions.extend(self._build_filter_conditions(filters))

        # Build dynamic aggregations for facets
        aggs = self._build_facet_aggregations(facets, facet_size, facet_query)
        facet_config = self.get_facets_config()

        # Construct the final Elasticsearch query
        search_query = {
            "from": from_offset,
            "size": limit,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": must_conditions if must_conditions else [{"match_all": {}}]
                }
            },
            "aggs": aggs,
            "_source": [
                "name", "mlTask", "sharedBy", "db_identifier", "keywords",
                "baseModels", "relatedDatasets", "license", "description","dateCreated"
            ]
        }
        
        total_hits = 0
        facet_results = {}
        result_models = []

        try:
            # Execute the search query
            es_response = self.indexHandler.search_complete_response(target_indices_str, search_query)
            
            # Extract hits and total count
            hits_data = es_response.get("hits", {})
            total = hits_data.get("total", 0)
            total_hits = total.get("value", 0) if isinstance(total, dict) else total

            # Process search result models
            for hit in hits_data.get("hits", []):
                source = hit.get("_source", {})
                result_entity = {
                    "score": hit.get("_score", 0),
                    "name": source.get("name", ""),
                    "mlTask": source.get("mlTask", []),
                    "sharedBy": source.get("sharedBy", []),
                    "db_identifier": source.get("db_identifier", ""),
                    "keywords": source.get("keywords", []),
                    "platform": source.get("platform", []),
                    "baseModels": source.get("baseModels", []),
                    "relatedDatasets": source.get("relatedDatasets", []),
                    "license": source.get("license", []),
                    "description": source.get("description", ""),
                    "dateCreated": source.get("dateCreated", "")
                }

                # Add extended information if requested
                if extended:
                    try:
                        extended_info = self.entityController.get_entity_details(result_entity["db_identifier"])
                        result_entity.update(extended_info)
                    except Exception as e:
                        print(f"Warning: Failed to get extended info for {result_entity['db_identifier']}: {e}")

                result_models.append(result_entity)

            # Process facet aggregations
            if "aggregations" in es_response:
                aggs_data = es_response["aggregations"]
                for facet in facets:
                    agg_key = f"{facet}_facet"
                    if agg_key in aggs_data:
                        facet_results[facet] = [
                            {"value": bucket["key"], "count": bucket["doc_count"]}
                            for bucket in aggs_data[agg_key]["buckets"]
                        ]

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in faceted search for indices {target_indices_str}: {e}")
            print(f"Detailed error traceback: {error_details}")
            # Return empty results on error but maintain structure
            result_models = []
            total_hits = 0
            facet_results = {}
        
        return {
            "models": result_models,
            "total": total_hits,
            "facets": facet_results,
            "facet_config": {k: v for k, v in facet_config.items() if k in facets}
        }

    def fetch_facet_values(
                                self,
                                field: str,
                                search_query: str = "",
                                after_key: str = "",
                                limit: int = 50,
                                current_filters: Dict[str, List[str]] = None
                            ) -> Dict[str, Any]:
        """
        Fetch additional values for a specific facet with optional search and pagination.
        
        This method supports high-cardinality facets by using composite aggregations
        for pagination and includes/regex for facet value search.
        
        Args:
            field (str): The field name to get facet values for
            search_query (str): Optional search term to filter facet values
            after_key (str): Pagination cursor for composite aggregations
            limit (int): Maximum number of values to return
            current_filters (Dict[str, List[str]]): Current filters to apply for context
            
        Returns:
            Dict[str, Any]: Dictionary with keys:
                - 'values': List of facet values with counts
                - 'after_key': Next pagination cursor (for composite aggs)
                - 'has_more': Whether there are more values available
                
        Raises:
            Exception: If Elasticsearch query fails or field is invalid
            
        Example:
            >>> controller.fetch_facet_values(
            ...     field="keywords",
            ...     search_query="medical",
            ...     limit=20,
            ...     current_filters={"license": ["MIT"]}
            ... )
            {
                "values": [{"value": "medical-imaging", "count": 15}],
                "after_key": "medical-imaging",
                "has_more": True
            }
        """
        all_indices = self.indexHandler.list_indexes()
        model_indices = [idx for idx in all_indices if idx.endswith("_models")]

        if not model_indices:
            return {"values": [], "after_key": None, "has_more": False}

        target_indices_str = ",".join(model_indices)
        
        # Apply current filters to get contextual facet values (excluding self-filter)
        must_conditions = []
        if current_filters:
            for prop, values in current_filters.items():
                if values and prop != field:  # Exclude self-filter for accurate counts
                    # Use facet configuration to determine field mapping
                    config = self.get_facets_config().get(prop, {})
                    field_type = config.get("type", "text")  # Default to text type if not specified
                    
                    # For keyword fields, use the field as-is. For text fields, append .keyword
                    if field_type == "keyword":
                        prop_keyword = prop
                    else:
                        prop_keyword = prop if prop.endswith(".keyword") else prop + ".keyword"
                    
                    must_conditions.append({
                        "terms": {prop_keyword: values}
                    })

        # Use facet configuration to determine field mapping
        config = self.get_facets_config().get(field, {})
        field_type = config.get("type", "text")  # Default to text type if not specified
        
        if field_type == "date":
            # For date fields, use date_histogram aggregation
            # Note: Date facets typically don't support text search, so we ignore search_query
            # Since the field contains timestamps in milliseconds, we need to handle it properly
            agg_config = {
                "date_histogram": {
                    "field": field,
                    "calendar_interval": "month",
                    "format": "yyyy-MM-dd",
                    "order": {"_key": "desc"}
                }
            }
            agg_key = "facet_values"
            
        else:
            # For keyword/text fields, use the original logic
            # For keyword fields, use the field as-is. For text fields, append .keyword
            if field_type == "keyword":
                field_keyword = field
            else:
                # For text fields, try .keyword first
                field_keyword = field if field.endswith(".keyword") else f"{field}.keyword"
            
            # Choose aggregation type based on whether search filtering is needed
            if search_query:
                # Use terms aggregation with include parameter for search filtering
                import re
                escaped_term = re.escape(search_query.lower())
                
                agg_config = {
                    "terms": {
                        "field": field_keyword,
                        "size": limit,
                        "order": {"_count": "desc"},
                        "include": f".*{escaped_term}.*"
                    }
                }
                agg_key = "facet_values"
                
            else:
                # Use composite aggregation for pagination support with high-cardinality facets
                composite_agg = {
                    "size": limit,
                    "sources": [
                        {field: {"terms": {"field": field_keyword, "order": "asc"}}}
                    ]
                }
                
                # Add pagination cursor if provided
                if after_key:
                    composite_agg["after"] = {field: after_key}
                
                agg_config = {"composite": composite_agg}
                agg_key = "facet_values"

        search_body = {
            "size": 0,  # We only want aggregations, not search hits
            "query": {
                "bool": {
                    "must": must_conditions if must_conditions else [{"match_all": {}}]
                }
            },
            "aggs": {
                agg_key: agg_config
            }
        }

        try:
            es_response = self.indexHandler.search_complete_response(target_indices_str, search_body)
            
            aggs_data = es_response.get("aggregations", {})
            facet_data = aggs_data.get("facet_values", {})
            
            buckets = facet_data.get("buckets", [])
            
            # Handle different aggregation response formats
            config = self.get_facets_config().get(field, {})
            field_type = config.get("type", "text")
            
            if field_type == "date":
                # Date histogram aggregation response: bucket["key_as_string"] contains formatted date
                values = [
                    {"value": bucket.get("key_as_string", bucket["key"]), "count": bucket["doc_count"]}
                    for bucket in buckets
                ]
                # Date histogram doesn't use pagination in our current implementation
                next_after_key = None
                has_more = False
            elif search_query:
                # Terms aggregation response: bucket["key"] is the direct value
                values = [
                    {"value": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in buckets
                ]
                # Terms aggregation doesn't support pagination
                next_after_key = None
                has_more = False
            else:
                # Composite aggregation response: bucket["key"] is an object with field name as key
                values = [
                    {"value": bucket["key"][field], "count": bucket["doc_count"]}
                    for bucket in buckets
                ]
                # Check if there are more results available for composite aggregation
                next_after_key = facet_data.get("after_key", {}).get(field)
                has_more = next_after_key is not None
            
            return {
                "values": values,
                "after_key": next_after_key,
                "has_more": has_more
            }
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error fetching facet values for field {field}: {e}")
            print(f"Detailed error traceback: {error_details}")
            return {"values": [], "after_key": None, "has_more": False}