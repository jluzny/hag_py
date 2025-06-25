"""
Configuration models for HAG system.

Type-safe configuration structures with Pydantic validation.
"""

from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

class SystemMode(str, Enum):
    """HVAC system operation modes."""
    AUTO = "auto"
    HEAT_ONLY = "heat_only"
    COOL_ONLY = "cool_only"
    OFF = "off"

class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

class HassOptions(BaseModel):
    """Home Assistant connection options."""
    ws_url: str = Field(..., description="WebSocket URL for Home Assistant")
    rest_url: str = Field(..., description="REST API URL for Home Assistant")
    token: str = Field(..., description="Long-lived access token")
    max_retries: int = Field(default=5, description="Maximum connection retry attempts")
    retry_delay_ms: int = Field(default=1000, description="Delay between retries in milliseconds")
    state_check_interval: int = Field(default=300000, description="State check interval in milliseconds")

    @field_validator('ws_url', 'rest_url')
    @classmethod
    def validate_urls(cls, v):
        """Validate URL format."""
        if not v.startswith(('ws://', 'wss://', 'http://', 'https://')):
            raise ValueError('Invalid URL format')
        return v

class TemperatureThresholds(BaseModel):
    """Temperature threshold configuration."""
    indoor_min: float = Field(..., description="Minimum indoor temperature")
    indoor_max: float = Field(..., description="Maximum indoor temperature")
    outdoor_min: float = Field(..., description="Minimum outdoor temperature for operation")
    outdoor_max: float = Field(..., description="Maximum outdoor temperature for operation")

    @field_validator('indoor_min', 'indoor_max', 'outdoor_min', 'outdoor_max')
    @classmethod
    def validate_temperatures(cls, v):
        """Validate temperature ranges."""
        if v < -50 or v > 60:
            raise ValueError('Temperature must be between -50°C and 60°C')
        return v

class DefrostOptions(BaseModel):
    """Defrost cycle configuration."""
    temperature_threshold: float = Field(default=0.0, description="Temperature below which defrost is needed")
    period_seconds: int = Field(default=3600, description="Defrost cycle period in seconds")
    duration_seconds: int = Field(default=300, description="Defrost cycle duration in seconds")

class HeatingOptions(BaseModel):
    """Heating configuration."""
    temperature: float = Field(default=21.0, description="Target heating temperature")
    preset_mode: str = Field(default="comfort", description="Heating preset mode")
    temperature_thresholds: TemperatureThresholds
    defrost: Optional[DefrostOptions] = None

    @field_validator('temperature')
    @classmethod
    def validate_heating_temp(cls, v):
        """Validate heating temperature range."""
        if v < 10 or v > 35:
            raise ValueError('Heating temperature must be between 10°C and 35°C')
        return v

class CoolingOptions(BaseModel):
    """Cooling configuration."""
    temperature: float = Field(default=24.0, description="Target cooling temperature")
    preset_mode: str = Field(default="eco", description="Cooling preset mode")
    temperature_thresholds: TemperatureThresholds

    @field_validator('temperature')
    @classmethod
    def validate_cooling_temp(cls, v):
        """Validate cooling temperature range."""
        if v < 15 or v > 35:
            raise ValueError('Cooling temperature must be between 15°C and 35°C')
        return v

class ActiveHours(BaseModel):
    """Active hours configuration."""
    start: int = Field(default=8, description="Start hour (24h format)")
    start_weekday: int = Field(default=7, description="Weekday start hour")
    end: int = Field(default=22, description="End hour (24h format)")

    @field_validator('start', 'start_weekday', 'end')
    @classmethod
    def validate_hours(cls, v):
        """Validate hour ranges."""
        if v < 0 or v > 23:
            raise ValueError('Hour must be between 0 and 23')
        return v

class HvacEntity(BaseModel):
    """HVAC entity configuration."""
    entity_id: str = Field(..., description="Home Assistant entity ID")
    enabled: bool = Field(default=True, description="Whether entity is enabled")
    defrost: bool = Field(default=False, description="Whether entity supports defrost")

    @field_validator('entity_id')
    @classmethod
    def validate_entity_id(cls, v):
        """Validate entity ID format."""
        if '.' not in v or len(v.split('.')) != 2:
            raise ValueError('Entity ID must be in format "domain.entity"')
        return v

class HvacOptions(BaseModel):
    """HVAC system configuration."""
    temp_sensor: str = Field(..., description="Temperature sensor entity ID")
    outdoor_sensor: str = Field(default="sensor.openweathermap_temperature", description="Outdoor temperature sensor")
    system_mode: SystemMode = Field(default=SystemMode.AUTO, description="System operation mode")
    hvac_entities: List[HvacEntity] = Field(default_factory=list, description="HVAC entities to control")
    heating: HeatingOptions
    cooling: CoolingOptions
    active_hours: Optional[ActiveHours] = None

    @field_validator('temp_sensor', 'outdoor_sensor')
    @classmethod
    def validate_sensor_ids(cls, v):
        """Validate sensor entity ID format."""
        if '.' not in v or not v.startswith('sensor.'):
            raise ValueError('Sensor ID must be in format "sensor.entity_name"')
        return v

class ApplicationOptions(BaseModel):
    """Application-level configuration options."""
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")
    use_ai: bool = Field(default=False, description="Enable AI agent for HVAC decisions")
    ai_model: str = Field(default="gpt-3.5-turbo", description="AI model to use")
    ai_temperature: float = Field(default=0.1, description="AI model temperature")

class Settings(BaseSettings):
    """Main application settings."""
    app_options: ApplicationOptions = Field(default_factory=ApplicationOptions)
    hass_options: HassOptions
    hvac_options: HvacOptions

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="allow",  # Allow extra environment variables (e.g. LangSmith telemetry)
    )
        
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Customize settings sources to prioritize environment variables."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )