"""
Dagster repository definition.

This is the main entrypoint for the Dagster instance.
"""

from dagster import Definitions, repository, load_assets_from_modules

from etl.assets import hf_extraction as hf_extraction_module
from etl.assets import hf_schema_extraction as hf_schema_extraction_module
from etl.assets import hf_transformation as hf_transformation_module
from etl.assets import hf_loading as hf_loading_module
from etl.assets import ai4life_loading as ai4life_loading_module
from etl.assets import openml_extraction as openml_assets_module
from etl.assets import ai4life_extraction as ai4life_assets_module
from etl.assets import ai4life_transformation as ai4life_transformation_module
from etl.assets import vector_indexing as vector_indexing_module

_ASSET_MODULES = [
    hf_extraction_module,
    hf_schema_extraction_module,
    hf_transformation_module,
    hf_loading_module,
    ai4life_loading_module,
    openml_assets_module,
    ai4life_assets_module,
    ai4life_transformation_module,
    vector_indexing_module,
]

_all_assets = load_assets_from_modules(_ASSET_MODULES)

defs = Definitions(assets=_all_assets)


@repository
def mlentory_etl_repository():
    """
    The main Dagster repository for MLentory ETL (legacy ``@repository`` entry).

    Prefer loading ``defs`` (``Definitions``) from this module for Dagster 1.4+.
    """
    return list(_all_assets)

