"""
Dagster repository definition.

This is the main entrypoint for the Dagster instance.
"""

from dagster import repository, load_assets_from_modules

from etl.assets import hf_extraction as hf_assets_module


@repository
def mlentory_etl_repository():
    """
    The main Dagster repository for MLentory ETL.
    
    Returns:
        list: List of jobs and schedules
    """
    hf_assets = load_assets_from_modules([hf_assets_module])
    return [*hf_assets]

