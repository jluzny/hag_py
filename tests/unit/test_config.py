"""
Tests for configuration system.

Port of Elixir config tests to Python.
"""

import pytest
from pathlib import Path
import tempfile
import yaml

from hag.config.settings import Settings, HassOptions, HvacOptions, SystemMode
from hag.config.loader import ConfigLoader

class TestConfigLoader:
    """Test configuration loading functionality."""
    
    def test_load_yaml_valid_config(self):
        """Test loading valid YAML configuration."""
        
        config_data = {
            "hass_options": {
                "ws_url": "ws://localhost:8123/api/websocket",
                "rest_url": "http://localhost:8123",
                "token": "test_token"
            },
            "hvac_options": {
                "temp_sensor": "sensor.test_temperature",
                "hvac_entities": []
            }
        }
        
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        try:
            # Load and verify
            loaded_data = ConfigLoader.load_yaml(temp_path)
            assert loaded_data == config_data
        finally:
            Path(temp_path).unlink()
    
    def test_load_yaml_file_not_found(self):
        """Test loading non-existent YAML file."""
        
        with pytest.raises(FileNotFoundError):
            ConfigLoader.load_yaml("nonexistent.yaml")
    
    def test_apply_env_overrides(self, monkeypatch):
        """Test environment variable substitution."""
        
        # Set environment variable
        monkeypatch.setenv("TEST_TOKEN", "env_token_value")
        
        config_data = {
            "hass_options": {
                "token": "${TEST_TOKEN}",
                "ws_url": "ws://localhost:8123/api/websocket"
            }
        }
        
        result = ConfigLoader.apply_env_overrides(config_data)
        
        assert result["hass_options"]["token"] == "env_token_value"
        assert result["hass_options"]["ws_url"] == "ws://localhost:8123/api/websocket"
    
    def test_apply_env_overrides_missing_var(self):
        """Test behavior when environment variable is missing."""
        
        config_data = {
            "hass_options": {
                "token": "${MISSING_VAR}"
            }
        }
        
        result = ConfigLoader.apply_env_overrides(config_data)
        
        # Should leave the placeholder unchanged when env var is missing
        assert result["hass_options"]["token"] == "${MISSING_VAR}"

class TestSettings:
    """Test Pydantic settings validation."""
    
    def test_valid_settings_creation(self):
        """Test creating valid settings."""
        
        config_data = {
            "hass_options": {
                "ws_url": "ws://localhost:8123/api/websocket",
                "rest_url": "http://localhost:8123",
                "token": "test_token"
            },
            "hvac_options": {
                "temp_sensor": "sensor.test_temperature",
                "hvac_entities": [],
                "heating": {
                    "temperature": 21.0,
                    "preset_mode": "comfort",
                    "temperature_thresholds": {
                        "indoor_min": 19.0,
                        "indoor_max": 20.0,
                        "outdoor_min": -10.0,
                        "outdoor_max": 15.0
                    }
                },
                "cooling": {
                    "temperature": 24.0,
                    "preset_mode": "eco",
                    "temperature_thresholds": {
                        "indoor_min": 23.0,
                        "indoor_max": 25.0,
                        "outdoor_min": 10.0,
                        "outdoor_max": 40.0
                    }
                }
            }
        }
        
        settings = Settings(**config_data)
        
        # Verify HASS options
        assert settings.hass_options.ws_url == "ws://localhost:8123/api/websocket"
        assert settings.hass_options.token == "test_token"
        assert settings.hass_options.max_retries == 5  # Default value
        
        # Verify HVAC options
        assert settings.hvac_options.temp_sensor == "sensor.test_temperature"
        assert settings.hvac_options.system_mode == SystemMode.AUTO  # Default value
        assert settings.hvac_options.heating.temperature == 21.0
        assert settings.hvac_options.cooling.temperature == 24.0
    
    def test_system_mode_enum_validation(self):
        """Test system mode enum validation."""
        
        base_config = {
            "hass_options": {
                "ws_url": "ws://localhost:8123/api/websocket",
                "rest_url": "http://localhost:8123",
                "token": "test_token"
            },
            "hvac_options": {
                "temp_sensor": "sensor.test_temperature",
                "hvac_entities": [],
                "heating": {
                    "temperature": 21.0,
                    "temperature_thresholds": {
                        "indoor_min": 19.0,
                        "indoor_max": 20.0,
                        "outdoor_min": -10.0,
                        "outdoor_max": 15.0
                    }
                },
                "cooling": {
                    "temperature": 24.0,
                    "temperature_thresholds": {
                        "indoor_min": 23.0,
                        "indoor_max": 25.0,
                        "outdoor_min": 10.0,
                        "outdoor_max": 40.0
                    }
                }
            }
        }
        
        # Test valid system modes
        valid_modes = ["auto", "heat_only", "cool_only", "off"]
        
        for mode in valid_modes:
            config = base_config.copy()
            config["hvac_options"]["system_mode"] = mode
            
            settings = Settings(**config)
            assert settings.hvac_options.system_mode.value == mode
    
    def test_temperature_validation(self):
        """Test temperature threshold validation."""
        
        base_config = {
            "hass_options": {
                "ws_url": "ws://localhost:8123/api/websocket",
                "rest_url": "http://localhost:8123",
                "token": "test_token"
            },
            "hvac_options": {
                "temp_sensor": "sensor.test_temperature",
                "hvac_entities": [],
                "heating": {
                    "temperature": 21.0,
                    "temperature_thresholds": {
                        "indoor_min": 19.0,
                        "indoor_max": 20.0,
                        "outdoor_min": -10.0,
                        "outdoor_max": 15.0
                    }
                },
                "cooling": {
                    "temperature": 24.0,
                    "temperature_thresholds": {
                        "indoor_min": 23.0,
                        "indoor_max": 25.0,
                        "outdoor_min": 10.0,
                        "outdoor_max": 40.0
                    }
                }
            }
        }
        
        # Valid configuration should work
        settings = Settings(**base_config)
        assert settings.hvac_options.heating.temperature == 21.0
        
        # Test extreme temperature validation
        with pytest.raises(ValueError):
            config = base_config.copy()
            config["hvac_options"]["heating"]["temperature"] = 100.0  # Too high
            Settings(**config)
    
    def test_entity_id_validation(self):
        """Test entity ID format validation."""
        
        base_config = {
            "hass_options": {
                "ws_url": "ws://localhost:8123/api/websocket", 
                "rest_url": "http://localhost:8123",
                "token": "test_token"
            },
            "hvac_options": {
                "temp_sensor": "sensor.test_temperature",
                "hvac_entities": [
                    {
                        "entity_id": "climate.test_ac",
                        "enabled": True
                    }
                ],
                "heating": {
                    "temperature": 21.0,
                    "temperature_thresholds": {
                        "indoor_min": 19.0,
                        "indoor_max": 20.0,
                        "outdoor_min": -10.0,
                        "outdoor_max": 15.0
                    }
                },
                "cooling": {
                    "temperature": 24.0,
                    "temperature_thresholds": {
                        "indoor_min": 23.0,
                        "indoor_max": 25.0,
                        "outdoor_min": 10.0,
                        "outdoor_max": 40.0
                    }
                }
            }
        }
        
        # Valid entity ID should work
        settings = Settings(**base_config)
        assert len(settings.hvac_options.hvac_entities) == 1
        assert settings.hvac_options.hvac_entities[0].entity_id == "climate.test_ac"
        
        # Invalid entity ID should fail
        with pytest.raises(ValueError):
            config = base_config.copy()
            config["hvac_options"]["hvac_entities"][0]["entity_id"] = "invalid_entity_id"
            Settings(**config)

    def test_invalid_configuration_combinations(self):
        """Test behavior with conflicting configuration values."""
        
        # Test overlapping temperature ranges (heating max > cooling min)
        invalid_temp_config = {
            "hass_options": {
                "ws_url": "ws://localhost:8123/api/websocket", 
                "rest_url": "http://localhost:8123",
                "token": "test_token"
            },
            "hvac_options": {
                "temp_sensor": "sensor.test_temperature",
                "hvac_entities": [],
                "heating": {
                    "temperature": 25.0,  # Heating target higher than cooling
                    "temperature_thresholds": {
                        "indoor_min": 19.0,
                        "indoor_max": 26.0,  # Overlaps with cooling range
                        "outdoor_min": -10.0,
                        "outdoor_max": 15.0
                    }
                },
                "cooling": {
                    "temperature": 20.0,  # Cooling target lower than heating
                    "temperature_thresholds": {
                        "indoor_min": 24.0,  # Overlaps with heating range
                        "indoor_max": 28.0,
                        "outdoor_min": 10.0,
                        "outdoor_max": 45.0
                    }
                }
            }
        }
        
        # Should still create valid settings (no validation error)
        # The system should handle logical conflicts at runtime
        settings = Settings(**invalid_temp_config)
        assert settings.hvac_options.heating.temperature == 25.0
        assert settings.hvac_options.cooling.temperature == 20.0
        
        # Test invalid active hours (end before start)
        invalid_hours_config = {
            "hass_options": {
                "ws_url": "ws://localhost:8123/api/websocket",
                "rest_url": "http://localhost:8123", 
                "token": "test_token"
            },
            "hvac_options": {
                "temp_sensor": "sensor.test_temperature",
                "hvac_entities": [],
                "heating": {
                    "temperature": 21.0,
                    "temperature_thresholds": {
                        "indoor_min": 19.0,
                        "indoor_max": 20.0,
                        "outdoor_min": -10.0,
                        "outdoor_max": 15.0
                    }
                },
                "cooling": {
                    "temperature": 24.0,
                    "temperature_thresholds": {
                        "indoor_min": 23.0,
                        "indoor_max": 25.0,
                        "outdoor_min": 10.0,
                        "outdoor_max": 40.0
                    }
                },
                "active_hours": {
                    "start": 20,  # Start at 8 PM
                    "end": 6      # End at 6 AM (next day - valid for overnight)
                }
            }
        }
        
        # Should create valid settings (overnight ranges are valid)
        settings = Settings(**invalid_hours_config)
        assert settings.hvac_options.active_hours and settings.hvac_options.active_hours.start == 20
        assert settings.hvac_options.active_hours and settings.hvac_options.active_hours.end == 6
        
        # Test extreme temperature thresholds
        extreme_config = {
            "hass_options": {
                "ws_url": "ws://localhost:8123/api/websocket",
                "rest_url": "http://localhost:8123",
                "token": "test_token"
            },
            "hvac_options": {
                "temp_sensor": "sensor.test_temperature",
                "hvac_entities": [],
                "heating": {
                    "temperature": 35.0,  # Very high heating target
                    "temperature_thresholds": {
                        "indoor_min": -50.0,  # Extreme range
                        "indoor_max": 100.0,
                        "outdoor_min": -50.0,
                        "outdoor_max": 100.0
                    }
                }
            }
        }
        
        # Should fail validation for extreme temperatures
        with pytest.raises(ValueError):
            Settings(**extreme_config)