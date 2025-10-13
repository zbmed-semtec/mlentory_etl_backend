"""
Dagster repository definition.

This is the main entrypoint for the Dagster instance.
"""

from dagster import repository


@repository
def mlentory_etl_repository():
    """
    The main Dagster repository for MLentory ETL.
    
    Returns:
        list: List of jobs and schedules
    """
    # TODO: Import and register jobs, assets, and schedules here
    return []

