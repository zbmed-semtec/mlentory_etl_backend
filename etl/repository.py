"""
Dagster repository definition.

This is the main entrypoint for the Dagster instance.
"""

from dagster import repository, load_assets_from_modules

from etl.assets import hf_extraction as hf_extraction_module
from etl.assets import hf_transformation as hf_transformation_module
from etl.assets import hf_loading as hf_loading_module
from etl.assets import openml_extraction as openml_assets_module
from etl.assets import openml_transformation as openml_transformation_module
from etl.assets import openml_loading as openml_loading_module
from etl.assets import ai4life_extraction as ai4life_assets_module

@repository
def mlentory_etl_repository():
    """
    The main Dagster repository for MLentory ETL.
    
    Returns:
        list: List of jobs and schedules
    """
    hf_extraction_assets = load_assets_from_modules([hf_extraction_module])
    hf_transformation_assets = load_assets_from_modules([hf_transformation_module])
    hf_loading_assets = load_assets_from_modules([hf_loading_module])
    openml_extraction_assets = load_assets_from_modules([openml_assets_module])
    openml_transformation_assets = load_assets_from_modules([openml_transformation_module])
    openml_loading_assets = load_assets_from_modules([openml_loading_module])
    ai4life_extraction_assets = load_assets_from_modules([ai4life_assets_module])
    return [
        *hf_extraction_assets,
        *hf_transformation_assets,
        *hf_loading_assets,
        *openml_extraction_assets,
        *openml_transformation_assets,
        *openml_loading_assets,
        *ai4life_extraction_assets,
    ]

