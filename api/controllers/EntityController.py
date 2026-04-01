import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from api.dbHandler.SQLHandler import SQLHandler
from api.utils.utils import Utils
from api.utils.cache_manager import get_entity_cache_manager


class EntityController:

    def __init__(self, sqlHandler: SQLHandler):
        self.sqlHandler = sqlHandler
        self.cache_manager = get_entity_cache_manager()

    def get_entity_details(self, entity_uri: str) -> Dict[str, Any]:
        """
        Retrieves information about an entity based on its URI with caching support.
        
        Args:
            entity_uri (str): The URI of the entity to retrieve information about.
            
        Returns:
            Dict[str, Any]: A dictionary containing the entity information.
            
        Raises:
            Exception: If there's an error querying the database
            
        Example:
            >>> controller = EntityController(sql_handler)
            >>> entity = controller.get_entity_details("<https://example.org/entity/123>")
            >>> print(entity.get('name', ['Unknown'])[0])
        """
        entity_info = {}
        
        if not entity_uri or not entity_uri.strip():
            return entity_info
            
        entity_uri = entity_uri.strip()
        
        
        # Try to get from cache first
        cached_entity = self.cache_manager.get(entity_uri)
        if cached_entity is not None:
            return cached_entity
        
        # Cache miss - query database
        try:
            query = """SELECT t.subject,t.predicate,t.object
                                        FROM "Triplet" t 
                                            JOIN "Version_Range" vr 
                                            ON t.id = vr.triplet_id
                                            WHERE t.subject = %s
                                            AND vr.deprecated = False
                                        """
            sql_result = self.sqlHandler.query(query, (entity_uri,))
            entity_info = self.format_entity_info_from_sql_result(sql_result)
            
            # Cache the result (even if empty to avoid repeated failed queries)
            self.cache_manager.set(entity_uri, entity_info)
            
        except Exception as e:
            # Log error but don't cache failed results except for empty ones
            print(f"Error querying entity details for {entity_uri}: {str(e)}")
            raise e

        return entity_info
    
    def get_entity_details_in_batch(self, entity_uris: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Retrieves information about an entity based on its URI with caching support.
        
        Args:
            entity_uri (str): The URI of the entity to retrieve information about.
            
        Returns:
            Dict[str, Dict[str, Any]]: A dictionary containing the entity information. 
                                        First key is the entity URI, second key is the predicate, value is the list of objects.
            
        Raises:
            Exception: If there's an error querying the database
        """
        
        entities_info = {}
        
        try:
            query = """SELECT t.subject,t.predicate,t.object
                                        FROM "Triplet" t 
                                            JOIN "Version_Range" vr 
                                            ON t.id = vr.triplet_id
                                            WHERE t.subject = ANY(%s)
                                            AND vr.deprecated = False
                                        """
            sql_result = self.sqlHandler.query(query, (entity_uris,))
            
            entities_info = self.format_entity_info_from_sql_result_batch(sql_result)
                
            # Cache the result (even if empty to avoid repeated failed queries)
            for entity_uri in entity_uris:
                if entity_uri not in entities_info:
                    entities_info[entity_uri] = {}
                self.cache_manager.set(entity_uri, entities_info[entity_uri])
            
        except Exception as e:
            # Log error but don't cache failed results except for empty ones
            print(f"Error querying entity details for {entity_uri}: {str(e)}")
            raise e
        
        return entities_info
    
    def invalidate_entity_cache(self, entity_uri: str) -> bool:
        """
        Invalidate a specific entity from the cache.
        
        Args:
            entity_uri: The URI of the entity to remove from cache
            
        Returns:
            bool: True if entity was removed from cache, False if not found
        """
        return self.cache_manager.invalidate(entity_uri)
    
    def clear_entity_cache(self) -> None:
        """Clear all cached entity data."""
        self.cache_manager.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get entity cache statistics.
        
        Returns:
            Dict[str, Any]: Cache performance metrics
        """
        return self.cache_manager.get_stats()
    
    def get_entity_history_by_date(self, entity_uri: str, version_date: datetime):
        """
        Retrieves the history of a model based on a given model ID and version date.
        Args:
            entity_uri (str): The URI of the entity to search for.
            version_date (str): The version date of the entity to search for.
        Returns:
            List[Dict[str, Any]]: A json object containing the list of entities.
        """

        # Get the earliest date of the entity
        query = """ SELECT MIN(vr.use_start), MAX(vr.use_end) 
                     FROM "Triplet" t
                     JOIN "Version_Range" vr
                     ON t.id = vr.triplet_id
                     WHERE t.subject = %s
        """
        sql_result = self.sqlHandler.query(query, (entity_uri,))

        if sql_result.empty:
            return None

        earliest_date = pd.to_datetime(sql_result.iloc[0, 0])

        latest_date = pd.to_datetime(sql_result.iloc[0, 1])

        if version_date < earliest_date:
            query = """ SELECT t.subject,t.predicate,t.object
            FROM "Triplet" t
            JOIN "Version_Range" vr
            ON t.id = vr.triplet_id
            WHERE 
            t.subject = %s and
            vr.use_start = %s
            """
            sql_result = self.sqlHandler.query(query, (entity_uri, earliest_date))
        elif version_date > latest_date:
            query = """ SELECT t.subject,t.predicate,t.object
            FROM "Triplet" t
            JOIN "Version_Range" vr
            ON t.id = vr.triplet_id
            WHERE
            t.subject = %s and
            vr.use_end = %s
            """
            sql_result = self.sqlHandler.query(query, (entity_uri, latest_date))
        else:
            query = """ SELECT t.subject,t.predicate,t.object
                        FROM "Triplet" t
                        JOIN "Version_Range" vr
                        ON t.id = vr.triplet_id
                        WHERE 
                        t.subject = %s and
                        vr.use_start <= %s and
                        vr.use_end > %s
                    """
            sql_result = self.sqlHandler.query(query, (entity_uri, version_date, version_date))

        entity_info = self.format_entity_info_from_sql_result(sql_result)

        return entity_info

    def get_full_entity_history(self, entity_uri: str):
        """
        Retrieves a list of all versions of a model based on a given model ID.
        Args:
            entity_uri (str): The URI of the entity to search for.
        Returns:
            List[Dict[str, Any]]: A list of json object containing a particular version of a models.
        """
        # Get all unique start dates
        query = """ SELECT DISTINCT(vr.use_start)
                    FROM "Triplet" t
                    JOIN "Version_Range" vr
                    ON t.id = vr.triplet_id
                    WHERE t.subject = %s
        """
        unique_start_dates = self.sqlHandler.query(query, (entity_uri,))
        entity_history = []

        for _, row in unique_start_dates.iterrows():
            version_date = row["use_start"]
            entity_info = self.get_entity_history_by_date(entity_uri, version_date)
            if entity_info is None or len(entity_info) == 0:
                continue
            entity_history.append(entity_info)

        return entity_history

    def get_entity_details_with_extraction_info(self, entity_uri: str) -> Dict[str, Any]:
        """
        Retrieves the current entity metadata along with extraction information.

        Args:
            model_id (str): The ID of the model to search for.

        Returns:
            Dict[str, Any]: A dictionary containing model metadata and extraction info.
        """
        query = """
            SELECT 
                t.predicate,
                t.object,
                tei.method_description,
                tei.extraction_confidence,
                vr.use_start,
                vr.use_end
            FROM "Triplet" t
            JOIN "Version_Range" vr ON t.id = vr.triplet_id
            JOIN "Triplet_Extraction_Info" tei ON vr.extraction_info_id = tei.id
            WHERE t.subject = %s
            AND vr.deprecated = FALSE
        """
        sql_result = self.sqlHandler.query(query, (entity_uri,))
        
        model_info = {
            "details": {},
            "extraction_metadata": {}
        }

        for _, row in sql_result.iterrows():
            predicate = Utils.n3_to_term(row["predicate"])
            if "#type" in predicate:
                predicate = predicate.split("#")[-1]
            else:
                predicate = predicate.split("/")[-1]
                
            object_value = Utils.n3_to_term(row["object"])
            
            if predicate in model_info["details"]:
                model_info["details"][predicate].append(object_value)
            else:
                model_info["details"][predicate] = [object_value]
            
            model_info["extraction_metadata"][predicate] = {
                "method_description": row["method_description"],
                "confidence": float(row["extraction_confidence"]),
                "valid_period": {
                    "from": row["use_start"].isoformat(),
                    "until": row["use_end"].isoformat()
                }
            }

        return model_info

    def get_entity_history_with_extraction_info(
        self, entity_uri: str, version_date: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves entity history with extraction metadata for a specific date.

        Args:
            entity_uri (str): The URI of the entity to search for.
            version_date (datetime): The version date to retrieve history for.

        Returns:
            Optional[Dict[str, Any]]: Entity history with extraction metadata, or None if not found.
        """
        # Get the date range
        date_range_query = """
            SELECT MIN(vr.use_start), MAX(vr.use_end) 
            FROM "Triplet" t
            JOIN "Version_Range" vr ON t.id = vr.triplet_id
            WHERE t.subject = %s
        """
        date_range = self.sqlHandler.query(date_range_query, (entity_uri,))
        
        if date_range.empty:
            return None

        earliest_date = pd.to_datetime(date_range.iloc[0, 0])
        latest_date = pd.to_datetime(date_range.iloc[0, 1])

        # Build the appropriate query based on the date
        if version_date < earliest_date:
            target_date = earliest_date
        elif version_date > latest_date:
            target_date = latest_date
        else:
            target_date = version_date

        history_query = """
            SELECT 
                t.predicate,
                t.object,
                tei.method_description,
                tei.extraction_confidence,
                vr.use_start,
                vr.use_end
            FROM "Triplet" t
            JOIN "Version_Range" vr ON t.id = vr.triplet_id
            JOIN "Triplet_Extraction_Info" tei ON vr.extraction_info_id = tei.id
            WHERE t.subject = %s
            AND vr.use_start <= %s
            AND vr.use_end > %s
        """
        sql_result = self.sqlHandler.query(history_query, (entity_uri, target_date, target_date))

        if sql_result.empty:
            return None

        history_info = {
            "details": {},
            "extraction_metadata": {}
        }

        for _, row in sql_result.iterrows():
            predicate = Utils.n3_to_term(row["predicate"])
            if "#type" in predicate:
                predicate = predicate.split("#")[-1]
            else:
                predicate = predicate.split("/")[-1]
            
            object_value = ""
            if row["object"].startswith("<"+Utils.MLENTORY_GRAPH):
                object_value = row["object"]
            else:
                object_value = Utils.n3_to_term(row["object"])
            
            if predicate in history_info["details"]:
                history_info["details"][predicate].append(object_value)
            else:
                history_info["details"][predicate] = [object_value]
            
            history_info["extraction_metadata"][predicate] = {
                "method_description": row["method_description"],
                "confidence": float(row["extraction_confidence"]),
                "valid_period": {
                    "from": row["use_start"].isoformat(),
                    "until": row["use_end"].isoformat()
                }
            }

        return history_info

    def get_full_entity_history_with_extraction_info(
        self, entity_uri: str
    ) -> List[Dict[str, Any]]:
        """
        Retrieves complete entity version history with extraction metadata.

        Args:
            entity_uri (str): The URI of the entity to search for.

        Returns:
            List[Dict[str, Any]]: List of entity versions with their metadata and extraction info.
        """
        query = """
            SELECT DISTINCT vr.use_start
            FROM "Triplet" t
            JOIN "Version_Range" vr ON t.id = vr.triplet_id
            WHERE t.subject = %s
            ORDER BY vr.use_start ASC
        """
        version_dates = self.sqlHandler.query(query, (entity_uri,))
        
        history = []
        for _, row in version_dates.iterrows():
            version_date = pd.to_datetime(row["use_start"])
            version_info = self.get_entity_history_with_extraction_info(
                entity_uri, version_date
            )
            if version_info:
                history.append(version_info)

        return history

    def get_distinct_property_values(self, property_name: str) -> List[Any]:
        """
        Retrieves distinct values for a specific property across all model entities.
        
        Args:
            property_name (str): The name of the property to get values for (e.g. 'license')
            
        Returns:
            List[Any]: Sorted list of unique values for the specified property
            
        Raises:
            ValueError: If property_name is empty or invalid
        """
        if not property_name or not isinstance(property_name, str):
            raise ValueError("Property name must be a non-empty string")
            
        query = '''
            SELECT DISTINCT t.object
            FROM "Triplet" t
            JOIN "Version_Range" vr ON t.id = vr.triplet_id
            WHERE t.predicate LIKE %s
            AND vr.deprecated = False
            ORDER BY t.object
        '''
        
        # Construct the LIKE pattern for the property
        pattern = f"%{property_name}%"
        result = self.sqlHandler.query(query, (pattern,))
        result = self.sqlHandler.query(query, (pattern,))
        values = [Utils.n3_to_term(row["object"]) for _, row in result.iterrows()]
        
        # Filter out None/null values and return sorted unique values
        return sorted(list({v for v in values if v is not None}))
    
    
    def get_distinct_property_values_new_query(self, property_name: str) -> List[Any]:
        """
        Retrieves distinct values for a specific property across all model entities.
        
        Args:
            property_name (str): The name of the property to get values for (e.g. 'license')
            
        Returns:
            List[Any]: Sorted list of unique values for the specified property
            
        Raises:
            ValueError: If property_name is empty or invalid
        """
        if not property_name or not isinstance(property_name, str):
            raise ValueError("Property name must be a non-empty string")
        
        # Lets find all the predicates that include the property name
        predicates_query = """
            SELECT DISTINCT t.predicate
            FROM "Triplet" t
            WHERE t.predicate LIKE %s
        """
        predicates_raw = self.sqlHandler.query(predicates_query, (f'<%{property_name}>',))
        
        predicates = [row["predicate"] for _, row in predicates_raw.iterrows()]
        
        print(predicates)
        
        if not predicates:
            return []
            
        # Create placeholders for the IN clause
        placeholders = ",".join(["%s"] * len(predicates))
        query = f'''
            SELECT DISTINCT t.object
            FROM "Triplet" t
            JOIN "Version_Range" vr ON t.id = vr.triplet_id
            WHERE t.predicate IN ({placeholders})
            AND vr.deprecated = False
            ORDER BY t.object
        '''
        
        result = self.sqlHandler.query(query, tuple(predicates))
        values = [Utils.n3_to_term(row["object"]) for _, row in result.iterrows()]
        
        # Filter out None/null values and return sorted unique values
        return list({v for v in values if v is not None})

    def get_distinct_property_values_with_entity_details(self, property_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieves distinct values for a specific property across all model entities, along with their entity details.
        
        Args:
            property_name (str): The name of the property to get values for (e.g. 'license','mlTask')
            limit (int): Maximum number of results to return
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing distinct property values and their entity details
            
        Raises:
            ValueError: If property_name is empty or invalid
        """
        
        values = self.get_distinct_property_values(property_name)
        values = values[:limit]
        entities_dict = {}
        for value in values:
            # Check the value is a valid URI
            if not value.startswith(Utils.MLENTORY_GRAPH):
                entities_dict[value] = {"name": value}
            else:
                entities_dict[value] = self.get_entity_details("<"+value+">")
        
            
        return entities_dict

    def get_related_entities_by_prefix(self, entities_uris: List[str], prefix: str) -> Dict[str, Dict[str, Any]]:
        """
        Retrieves entities related to specified entities that match a given URI prefix.
        
        Args:
            entities_uris (List[str]): List of entity URIs to find related entities for
            prefix (str): URI prefix to filter related entities (e.g., "https://w3id.org/mlentory/mlentory_graph/")
            
        Returns:
            Dict[str, Dict[str, Any]]: Dictionary mapping entity URIs to their details
            
        Raises:
            ValueError: If entities_uris is empty or prefix is invalid
        """
        if not entities_uris:
            raise ValueError("Entities URIs list cannot be empty")
        if not prefix or not isinstance(prefix, str):
            raise ValueError("Prefix must be a non-empty string")
        
        # Process each model URI individually
        entities_dict = {}
        for entity_uri in entities_uris:
            # Query to find related entity URIs for this specific model that match the prefix
            query = """
                SELECT DISTINCT t.object AS entity_uri, t.predicate
                FROM "Triplet" t
                JOIN "Version_Range" vr ON t.id = vr.triplet_id
                WHERE t.subject = %s
                AND t.object LIKE %s
                AND vr.deprecated = False
            """
            
            # Execute query for this model URI with parameters
            result = self.sqlHandler.query(query, (entity_uri, prefix + '%'))
            
            # Extract entity URIs for this model
            for _, row in result.iterrows():
                entity_uri = row["entity_uri"]
                    
                # Only process if we haven't seen this entity before
                if entity_uri not in entities_dict:
                    entity_details = self.get_entity_details(entity_uri)
                    if entity_details:  # Only include entities with details
                        entity_details["db_identifier"] = entity_uri
                        entities_dict[entity_uri] = entity_details
                    else:
                        # If no details found, just store the identifier
                        entities_dict[entity_uri] = {"db_identifier": entity_uri}
        
        return entities_dict

    def get_entities_by_type(self, entity_type: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Retrieves entities of a specific type.
        
        Args:
            entity_type (str): The type of entities to retrieve (e.g., 'Person', 'Organization', 'MLModel')
            limit (int): Maximum number of entities to return
            offset (int): Number of entities to skip for pagination
            
        Returns:
            List[Dict[str, Any]]: List of entities of the specified type
            
        Raises:
            ValueError: If entity_type is empty or invalid
        """
        if not entity_type or not isinstance(entity_type, str):
            raise ValueError("Entity type must be a non-empty string")
        
        # First, find entities with the specified type
        type_query = """
            SELECT DISTINCT t.subject
            FROM "Triplet" t
            JOIN "Version_Range" vr ON t.id = vr.triplet_id
            WHERE t.predicate LIKE '%type%'
            AND t.object LIKE %s
            AND vr.deprecated = False
            ORDER BY t.subject
            LIMIT %s OFFSET %s
        """
        
        type_results = self.sqlHandler.query(type_query,("%"+entity_type+"%", str(limit), str(offset)))
        
        if type_results.empty:
            return []
        
        # Get details for each entity
        entities = []
        for _, row in type_results.iterrows():
            entity_uri = row["subject"]
            entity_details = self.get_entity_details(entity_uri)
            
            # Add the entity URI as db_identifier if not already present
            if "db_identifier" not in entity_details:
                entity_details["db_identifier"] = entity_uri
                
            entities.append(entity_details)
        
        return entities

    def get_available_entity_types(self) -> List[str]:
        """
        Retrieves a list of all available entity types in the database.
        
        Returns:
            List[str]: List of distinct entity types
        """
        query = """
            SELECT DISTINCT t.object
            FROM "Triplet" t
            JOIN "Version_Range" vr ON t.id = vr.triplet_id
            WHERE t.predicate LIKE '%type%'
            AND vr.deprecated = False
            ORDER BY t.object
        """
        
        result = self.sqlHandler.query(query)
        types = [Utils.n3_to_term(row["object"]) for _, row in result.iterrows()]
        
        # Extract the type name from URIs or full type strings
        clean_types = []
        for type_value in types:
            if type_value:
                # Handle different formats of type values
                if "#" in type_value:
                    # For URIs with fragment identifiers like http://schema.org/#Person
                    clean_types.append(type_value.split("#")[-1])
                elif "/" in type_value:
                    # For URIs without fragment identifiers
                    clean_types.append(type_value.split("/")[-1])
                else:
                    clean_types.append(type_value)
        
        # Return unique, non-empty types
        return sorted(list({t for t in clean_types if t}))

    def format_entity_info_from_sql_result(self, sql_result: pd.DataFrame) -> Dict[str, Any]:
        entity_info = {}
        # predica
        for _, row in sql_result.iterrows():

            predicate = Utils.n3_to_term(row["predicate"])
            if "#type" in predicate:
                predicate = predicate.split("#")[-1]
            else:
                predicate = predicate.split("/")[-1]
            # object = ""
            triplet_object = Utils.n3_to_term(row["object"])
            if predicate in entity_info:
                entity_info[predicate].append(triplet_object)
            else:
                entity_info[predicate] = [triplet_object]
                
        return entity_info
    
    def format_entity_info_from_sql_result_batch(self, sql_result: pd.DataFrame) -> Dict[str, Any]:
        """
        Formats entity information from SQL result for batch processing.
        
        Args:
            sql_result (pd.DataFrame): DataFrame containing the SQL result
        
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing entity information
        """
        
        entities_dict = {}
        
        for _, row in sql_result.iterrows():
            
            triplet_subject = row["subject"]
            
            if triplet_subject not in entities_dict:
                entities_dict[triplet_subject] = {}

            predicate = Utils.n3_to_term(row["predicate"])
            if "#type" in predicate:
                predicate = predicate.split("#")[-1]
            else:
                predicate = predicate.split("/")[-1]
                
            triplet_object = Utils.n3_to_term(row["object"])
            if triplet_subject in entities_dict[triplet_subject]:
                entities_dict[triplet_subject][predicate].append(triplet_object)
            else:
                entities_dict[triplet_subject][predicate] = [triplet_object]
        
        print("////////////////////////////////////////////////////////////")
        print("sql_result")
        print(sql_result.head())
        print(len(sql_result))
        print(len(entities_dict))
        print("////////////////////////////////////////////////////////////")
        
        # i = 0
        # print("entities_dict")
        # for entity_uri in entities_dict:
        #     print(entity_uri)
        #     print(entities_dict[entity_uri])
        #     i += 1
        #     if i > 10:
        #         break
        
        return entities_dict