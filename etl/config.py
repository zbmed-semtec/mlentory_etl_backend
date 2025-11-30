"""
Configuration loader for MLentory ETL runs.

This module provides type-safe access to YAML-based configuration for extraction pipelines.
Secrets (Neo4j, Elasticsearch credentials) remain in .env files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ========== Configuration Models ==========


class GeneralConfig(BaseModel):
    """General configuration shared across platforms."""

    default_threads: int = Field(default=4, ge=1)
    data_root: str = Field(default="/data")


class HuggingFaceConfig(BaseModel):
    """Configuration for HuggingFace extraction."""

    num_models: int = Field(default=2000, ge=0)
    update_recent: bool = Field(default=True)
    threads: int = Field(default=4, ge=1)
    models_file_path: str = Field(default="/data/refs/hf_model_ids.txt")
    base_model_iterations: int = Field(default=1, ge=0)
    enrichment_threads: int = Field(default=4, ge=1)
    offset: int = Field(default=0, ge=0)


class OpenMLConfig(BaseModel):
    """Configuration for OpenML extraction."""

    num_instances: int = Field(default=50, ge=0)
    offset: int = Field(default=0, ge=0)
    threads: int = Field(default=4, ge=1)
    enrichment_threads: int = Field(default=4, ge=1)
    enable_scraping: bool = Field(default=False)


class AI4LifeConfig(BaseModel):
    """Configuration for AI4Life extraction."""

    num_models: int = Field(default=50, ge=0)
    base_url: str = Field(default="https://hypha.aicell.io")
    parent_id: str = Field(default="bioimage-io/bioimage.io")


class PlatformsConfig(BaseModel):
    """Container for all platform-specific configurations."""

    huggingface: HuggingFaceConfig = Field(default_factory=HuggingFaceConfig)
    openml: OpenMLConfig = Field(default_factory=OpenMLConfig)
    ai4life: AI4LifeConfig = Field(default_factory=AI4LifeConfig)


class RunConfig(BaseModel):
    """Root configuration model for ETL runs."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    platforms: PlatformsConfig = Field(default_factory=PlatformsConfig)


# ========== Configuration Loader ==========


class ConfigLoader:
    """
    Singleton loader for ETL run configuration.

    Loads and validates YAML configuration on first access, then caches the result.
    """

    _instance: Optional[RunConfig] = None
    _config_path: Optional[Path] = None

    @classmethod
    def load(
        cls, config_path: Optional[Path] = None, force_reload: bool = False
    ) -> RunConfig:
        """
        Load and return the ETL run configuration.

        Args:
            config_path: Path to the YAML config file. If None, uses default location.
            force_reload: If True, reload config even if already cached.

        Returns:
            RunConfig instance with validated configuration.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If config file is invalid.
        """
        if cls._instance is not None and not force_reload:
            return cls._instance

        if config_path is None:
            # Default location relative to project root
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "etl" / "run_config.yaml"

        config_path = Path(config_path)
        cls._config_path = config_path

        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            raise FileNotFoundError(
                f"ETL configuration file not found at {config_path}. "
                "Please create config/etl/run_config.yaml or specify a valid path."
            )

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)

            if raw_config is None:
                raw_config = {}

            cls._instance = RunConfig(**raw_config)
            logger.info(f"Loaded ETL configuration from {config_path}")
            return cls._instance

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML configuration: {e}")
            raise ValueError(f"Invalid YAML in {config_path}: {e}") from e
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise ValueError(f"Configuration validation failed: {e}") from e

    @classmethod
    def get_config(cls) -> RunConfig:
        """
        Get the cached configuration, loading it if necessary.

        Returns:
            RunConfig instance.
        """
        if cls._instance is None:
            return cls.load()
        return cls._instance

    @classmethod
    def reload(cls, config_path: Optional[Path] = None) -> RunConfig:
        """
        Force reload the configuration from disk.

        Args:
            config_path: Optional path to config file.

        Returns:
            Newly loaded RunConfig instance.
        """
        return cls.load(config_path=config_path, force_reload=True)


# ========== Convenience Functions ==========


def get_hf_config() -> HuggingFaceConfig:
    """Get HuggingFace platform configuration."""
    return ConfigLoader.get_config().platforms.huggingface


def get_openml_config() -> OpenMLConfig:
    """Get OpenML platform configuration."""
    return ConfigLoader.get_config().platforms.openml


def get_ai4life_config() -> AI4LifeConfig:
    """Get AI4Life platform configuration."""
    return ConfigLoader.get_config().platforms.ai4life


def get_general_config() -> GeneralConfig:
    """Get general configuration."""
    return ConfigLoader.get_config().general

