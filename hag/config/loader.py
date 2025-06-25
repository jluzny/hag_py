"""
Configuration loader for HAG system.

Handles YAML configuration loading with environment variable overrides.
"""

import os
import yaml
from typing import Dict, Any
from pathlib import Path
import structlog
from hag.config.settings import Settings

logger = structlog.get_logger(__name__)

class ConfigLoader:
    """Configuration loader with YAML support and environment overrides."""

    @staticmethod
    def load_yaml(file_path: str) -> Dict[str, Any]:
        """Load YAML configuration file."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        logger.info("Loading configuration", file_path=file_path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            if config_data is None:
                raise ValueError(f"Empty configuration file: {file_path}")

            logger.debug(
                "Configuration loaded successfully",
                keys=list(config_data.keys()),
                file_path=file_path,
            )

            return config_data

        except yaml.YAMLError as e:
            logger.error(
                "Failed to parse YAML configuration", file_path=file_path, error=str(e)
            )
            raise ValueError(f"Invalid YAML configuration: {e}")

    @staticmethod
    def apply_env_overrides(config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration."""

        def _substitute_env_vars(obj) -> Any:
            """Recursively substitute environment variables in config."""
            if isinstance(obj, dict):
                return {k: _substitute_env_vars(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_substitute_env_vars(item) for item in obj]
            elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
                # Handle ${ENV_VAR} syntax
                env_var = obj[2:-1]
                value = os.getenv(env_var)
                if value is None:
                    logger.warning(
                        "Environment variable not found",
                        env_var=env_var,
                        original_value=obj,
                    )
                    return obj
                logger.debug(
                    "Applied environment override",
                    env_var=env_var,
                    value="***" if "token" in env_var.lower() else value,
                )
                return value
            else:
                return obj

        return _substitute_env_vars(config_data)

    @classmethod
    def load_settings(cls, config_file: str, apply_env: bool = True) -> Settings:
        """Load and validate settings from YAML file."""
        logger.info("Loading HAG configuration", config_file=config_file)

        try:
            # Load YAML configuration
            config_data = cls.load_yaml(config_file)

            # Apply environment variable overrides
            if apply_env:
                config_data = cls.apply_env_overrides(config_data)

            # Create and validate settings
            settings = Settings(**config_data)

            logger.info(
                "Configuration loaded and validated successfully",
                temp_sensor=settings.hvac_options.temp_sensor,
                system_mode=settings.hvac_options.system_mode,
                hvac_entities_count=len(settings.hvac_options.hvac_entities),
            )

            return settings

        except Exception as e:
            logger.error(
                "Failed to load configuration", config_file=config_file, error=str(e)
            )
            raise

    @staticmethod
    def get_default_config_path() -> str:
        """Get default configuration file path."""
        # Check for environment variable first
        config_path = os.getenv("HAG_CONFIG_FILE")
        if config_path:
            return config_path

        # Check for config files in order of preference
        possible_paths = [
            "config/hvac_config.yaml",
            "hvac_config.yaml",
            "/etc/hag/hvac_config.yaml",
        ]

        for path in possible_paths:
            if Path(path).exists():
                return path

        # Return default path even if it doesn't exist
        return "config/hvac_config.yaml"

