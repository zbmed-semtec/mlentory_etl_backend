"""
ModelContextService module for handling ML model context processing for LLM queries.

This module provides functionality to format model information for LLM context,
create specialized prompt templates, and handle model comparison operations.
"""

from typing import Dict, List, Any, Optional, Union
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelContextService:
    """
    Service for ML model context formatting and prompt template creation.
    
    This class handles the transformation of model details into structured formats
    suitable for LLM processing, and creates specialized prompt templates for
    different types of model queries.
    """
    
    def __init__(self):
        """
        Initialize the ModelContextService.
        
        Args:
            None
            
        Returns:
            None
        """
        # Define aspect mappings for specialized queries
        self.aspect_mapping = {
            "performance": {
                "properties": ["metrics", "accuracy", "f1", "precision", "recall", "perplexity", "loss"],
                "description": "performance metrics, benchmark results, and evaluation scores"
            },
            "architecture": {
                "properties": ["architecture", "parameters", "size", "layers", "framework", "structure"],
                "description": "model architecture, size, parameters, and structural design"
            },
            "licensing": {
                "properties": ["license", "usage", "restrictions", "commercial", "rights"],
                "description": "licensing terms, usage restrictions, and rights"
            },
            "training": {
                "properties": ["training", "dataset", "data", "epochs", "optimizer", "learning rate"],
                "description": "training process, datasets, and methodology"
            },
            "applications": {
                "properties": ["task", "application", "use case", "domain", "capability"],
                "description": "applications, tasks, use cases, and capabilities"
            },
            "versions": {
                "properties": ["version", "history", "release", "update", "changelog"],
                "description": "version history, updates, and changes over time"
            }
        }
        
        # Define priority properties for formatting
        self.priority_props = ["MLtask", "license", "keywords"]
        
        logger.info("ModelContextService initialized")
    
    def format_model_details(self, model_details: Dict[str, Any], include_raw_json: bool = False) -> str:
        """
        Format model details into a structured, readable text format for LLM context.
        
        Args:
            model_details: Dictionary containing model details
            include_raw_json: Whether to include raw JSON in the formatted output
            
        Returns:
            Formatted string with model information
            
        Raises:
            ValueError: If model_details is None or empty
        """
        if not model_details:
            raise ValueError("Model details cannot be None or empty")
            
        # Start with basic model information
        formatted_text = []
        
        # Add model name and ID if available
        if model_details.name:
            formatted_text.append(f"Model Name: {model_details.name}")
        
        # if "id" in model_details:
        #     formatted_text.append(f"Model ID: {model_details['id'][0]}")
        
        # Add description if available
        if model_details.description:
            formatted_text.append(f"\nDescription: {model_details.description}")
        
        # Add key model properties in sections
        formatted_text.append("\n== Model Properties ==")
        
        # Process priority properties first
        for prop in self.priority_props:
            if prop in model_details and model_details[prop]:
                if isinstance(model_details[prop], list):
                    formatted_text.append(f"{prop.capitalize()}: {', '.join(str(item) for item in model_details[prop])}")
                else:
                    formatted_text.append(f"{prop.capitalize()}: {model_details[prop]}")
        
        # Process remaining properties
        # for key, value in model_details.items():
        #     # Skip already processed properties and empty values
        #     if key in self.priority_props or key in ["name", "id", "description"] or not value:
        #         continue
                
        #     # Format based on value type
        #     if isinstance(value, list):
        #         if all(isinstance(item, dict) for item in value):
        #             # Handle list of dictionaries
        #             formatted_text.append(f"\n{key.capitalize()}:")
        #             for item in value:
        #                 for k, v in item.items():
        #                     formatted_text.append(f"  - {k}: {v}")
        #         else:
        #             # Handle simple lists
        #             formatted_text.append(f"{key.capitalize()}: {', '.join(str(item) for item in value)}")
        #     elif isinstance(value, dict):
        #         # Handle dictionaries
        #         formatted_text.append(f"\n{key.capitalize()}:")
        #         for k, v in value.items():
        #             formatted_text.append(f"  - {k}: {v}")
        #     else:
        #         # Handle simple values
        #         formatted_text.append(f"{key.capitalize()}: {value}")
        
        # Add performance metrics if available
        # if "metrics" in model_details and model_details["metrics"]:
        #     formatted_text.append("\n== Performance Metrics ==")
        #     metrics = model_details["metrics"]
        #     if isinstance(metrics, dict):
        #         for metric_name, metric_value in metrics.items():
        #             formatted_text.append(f"{metric_name}: {metric_value}")
        #     elif isinstance(metrics, list):
        #         for metric in metrics:
        #             if isinstance(metric, dict):
        #                 for k, v in metric.items():
        #                     formatted_text.append(f"{k}: {v}")
        
        result = "\n".join(formatted_text)
        
        # Optionally include raw JSON if requested
        if include_raw_json:
            raw_json = json.dumps(model_details, indent=2)
            result += f"\n\nRaw JSON representation:\n{raw_json}"
            
        return result
    
    def create_single_model_prompt(self) -> str:
        """
        Create a prompt template for querying a single model.
        
        Args:
            None
            
        Returns:
            String containing the prompt template
        """
        return """
        You are an AI assistant specialized in machine learning models.
        You have been provided with detailed information about a specific machine learning model.
        Use this information to answer the user's question accurately and concisely.
        
        If the question cannot be answered using the provided information, state this clearly
        and suggest what additional information might be needed.
        
        When discussing model properties, cite the specific property values from the context.
        
        Ouput should be in markdown format.
        Keep the response concise.
        
        MODEL INFORMATION:
        {context}
        
        Question:
        {question}
        
        Answer:
        """
    
    def create_model_aspect_prompt(self, aspect: str) -> str:
        """
        Create a prompt template focused on a specific aspect of a model.
        
        Args:
            aspect: The aspect to focus on (e.g., 'performance', 'architecture')
            
        Returns:
            String containing the aspect-focused prompt template
        """
        # Get aspect details or use generic if not found
        aspect_info = self.aspect_mapping.get(aspect.lower(), {
            "properties": [aspect],
            "description": f"information related to {aspect}"
        })
        
        return f"""
        You are an AI assistant specialized in machine learning models.
        You have been provided with detailed information about a specific machine learning model.
        
        The user is asking specifically about the {aspect} of this model.
        Focus your answer on {aspect_info['description']}.
        
        Use the provided information to answer the user's question accurately and concisely.
        If the question cannot be answered using the provided information, state this clearly
        and suggest what additional information might be needed.
        
        When discussing model properties, cite the specific property values from the context.
        
        MODEL INFORMATION:
        {{context}}
        
        Question about {aspect}:
        {{question}}
        
        Answer focused on {aspect}:
        """
    
    def create_model_comparison_prompt(self, num_models: int) -> str:
        """
        Create a prompt template for comparing multiple models.
        
        Args:
            num_models: Number of models being compared
            
        Returns:
            String containing the comparison prompt template
        """
        return f"""
        You are an AI assistant specialized in comparing machine learning models.
        You have been provided with detailed information about {num_models} different machine learning models.
        
        Use this information to compare the models and answer the user's question.
        When comparing models, focus on their key differences and similarities in:
        - Architecture and size
        - Performance metrics
        - Tasks and capabilities
        - Licensing and usage restrictions
        - Version history and development
        
        If the question cannot be answered using the provided information, state this clearly
        and suggest what additional information might be needed.
        
        When discussing model properties, cite the specific property values from the context
        and clearly indicate which model you are referring to.
        
        MODELS INFORMATION:
        {{context}}
        
        Question for comparison:
        {{question}}
        
        Comparative Analysis:
        """
    
    def format_models_for_comparison(
        self, 
        model_details_list: List[Dict[str, Any]], 
        model_names: List[str],
        include_raw_json: bool = False
    ) -> str:
        """
        Format multiple models for comparison.
        
        Args:
            model_details_list: List of dictionaries containing model details
            model_names: List of model names corresponding to the details
            include_raw_json: Whether to include raw JSON in the formatted output
            
        Returns:
            Formatted string with all models' information
            
        Raises:
            ValueError: If lists are empty or of different lengths
        """
        if not model_details_list:
            raise ValueError("Model details list cannot be empty")
        

        print(model_names)

        if len(model_details_list) != len(model_names):
            raise ValueError("Model details list and names list must be the same length")
            
        # Format all models into a structured context
        structured_contexts = []
        
        for i, model_details in enumerate(model_details_list):
            model_context = f"=== MODEL {i+1}: {model_names[i]} ===\n"
            model_context += self.format_model_details(model_details, False)  # Don't include JSON here
            
            # if include_raw_json:
            #     raw_json = json.dumps(model_details, indent=2)
            #     model_context += f"\n\nRaw JSON for {model_names[i]}:\n{raw_json}"
                
            structured_contexts.append(model_context)
        
        # Combine all contexts
        return "\n\n".join(structured_contexts)
    
    def get_available_aspects(self) -> Dict[str, str]:
        """
        Get available model aspects that can be queried.
        
        Args:
            None
            
        Returns:
            Dictionary of aspect names and descriptions
        """
        return {
            aspect: info["description"]
            for aspect, info in self.aspect_mapping.items()
        } 