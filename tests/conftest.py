"""
Pytest configuration and fixtures for HAG tests.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock
from typing import Dict, Any

from hag.config.settings import HvacOptions, HassOptions, TemperatureThresholds, HeatingOptions, CoolingOptions, HvacEntity
from hag.home_assistant.client import HomeAssistantClient
from hag.hvac.state_machine import HVACStateMachine

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_hass_options():
    """Mock Home Assistant options."""
    return HassOptions(
        ws_url="ws://localhost:8123/api/websocket",
        rest_url="http://localhost:8123",
        token="test_token",
        max_retries=3,
        retry_delay_ms=500
    )

@pytest.fixture
def mock_hvac_options():
    """Mock HVAC options."""
    return HvacOptions(
        temp_sensor="sensor.test_temperature",
        outdoor_sensor="sensor.test_outdoor_temperature",
        system_mode="auto",
        hvac_entities=[
            HvacEntity(entity_id="climate.test_ac", enabled=True, defrost=False)
        ],
        heating=HeatingOptions(
            temperature=21.0,
            preset_mode="comfort",
            temperature_thresholds=TemperatureThresholds(
                indoor_min=19.0,
                indoor_max=20.0,
                outdoor_min=-10.0,
                outdoor_max=15.0
            )
        ),
        cooling=CoolingOptions(
            temperature=24.0,
            preset_mode="eco",
            temperature_thresholds=TemperatureThresholds(
                indoor_min=23.0,
                indoor_max=25.0,
                outdoor_min=10.0,
                outdoor_max=40.0
            )
        )
    )

@pytest.fixture
def mock_ha_client():
    """Mock Home Assistant client."""
    client = AsyncMock(spec=HomeAssistantClient)
    client.connected = True
    return client

@pytest.fixture
def mock_state_machine(mock_hvac_options):
    """Mock HVAC state machine."""
    return HVACStateMachine(mock_hvac_options)

@pytest.fixture
def sample_temperature_data():
    """Sample temperature data for testing."""
    return {
        "indoor_temp": 20.5,
        "outdoor_temp": 15.0,
        "hour": 14,
        "is_weekday": True
    }