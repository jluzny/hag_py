"""
Integration tests for HVAC system.

rs with comprehensive integration scenarios.
"""

import pytest
from unittest.mock import AsyncMock

from hag.config.settings import (
    HvacOptions,
    HassOptions,
    SystemMode,
    TemperatureThresholds,
    HeatingOptions,
    CoolingOptions,
    HvacEntity,
    DefrostOptions,
    ActiveHours,
)
from hag.home_assistant.client import HomeAssistantClient
from hag.home_assistant.models import HassState, HassEvent, HassStateChangeData
from hag.hvac.controller import HVACController
from hag.hvac.state_machine import HVACStateMachine
from hag.hvac.agent import HVACAgent

class TestHVACIntegration:
    """Integration tests .rs."""

    @pytest.fixture
    def test_config(self):
        """Test configuration matching Rust config_test.yaml."""
        return {
            "hass_options": HassOptions(
                ws_url="ws://localhost:8123/api/websocket",
                rest_url="http://localhost:8123",
                token="test_token",
                max_retries=3,
                retry_delay_ms=500,
            ),
            "hvac_options": HvacOptions(
                temp_sensor="sensor.test_temperature",
                outdoor_sensor="sensor.test_outdoor_temperature",
                system_mode=SystemMode.AUTO,
                hvac_entities=[
                    HvacEntity(
                        entity_id="climate.living_room_ac", enabled=True, defrost=True
                    ),
                    HvacEntity(
                        entity_id="climate.bedroom_ac", enabled=True, defrost=False
                    ),
                ],
                heating=HeatingOptions(
                    temperature=21.0,
                    preset_mode="comfort",
                    temperature_thresholds=TemperatureThresholds(
                        indoor_min=19.7,
                        indoor_max=20.2,
                        outdoor_min=-10.0,
                        outdoor_max=15.0,
                    ),
                    defrost=DefrostOptions(
                        temperature_threshold=0.0,
                        period_seconds=3600,
                        duration_seconds=300,
                    ),
                ),
                cooling=CoolingOptions(
                    temperature=24.0,
                    preset_mode="windFree",
                    temperature_thresholds=TemperatureThresholds(
                        indoor_min=23.5,
                        indoor_max=25.0,
                        outdoor_min=10.0,
                        outdoor_max=45.0,
                    ),
                ),
                active_hours=ActiveHours(start=0, start_weekday=0, end=23),
            ),
        }

    @pytest.fixture
    def mock_ha_client(self):
        """Mock Home Assistant client."""
        client = AsyncMock(spec=HomeAssistantClient)
        client.connected = True

        # Mock get_state responses
        async def mock_get_state(entity_id: str):
            if entity_id == "sensor.test_temperature":
                return HassState.from_dict(
                    {
                        "entity_id": entity_id,
                        "state": "20.5",
                        "attributes": {"unit_of_measurement": "°C"},
                        "last_changed": "2024-01-01T12:00:00Z",
                        "last_updated": "2024-01-01T12:00:00Z",
                    }
                )
            elif entity_id == "sensor.test_outdoor_temperature":
                return HassState.from_dict(
                    {
                        "entity_id": entity_id,
                        "state": "15.0",
                        "attributes": {"unit_of_measurement": "°C"},
                        "last_changed": "2024-01-01T12:00:00Z",
                        "last_updated": "2024-01-01T12:00:00Z",
                    }
                )
            else:
                raise ValueError(f"Unknown entity: {entity_id}")

        client.get_state.side_effect = mock_get_state
        client.call_service.return_value = {"success": True}

        return client

    @pytest.mark.asyncio
    async def test_hvac_controller_basic_operation(self, test_config, mock_ha_client):
        """
        Test basic HVAC controller operation.

        
        """

        hvac_options = test_config["hvac_options"]

        # Create components
        state_machine = HVACStateMachine(hvac_options)

        # Mock HVACAgent to avoid LLM dependencies in tests
        mock_agent = AsyncMock(spec=HVACAgent)
        mock_agent.process_temperature_change.return_value = {
            "success": True,
            "action_taken": "heating",
        }
        mock_agent.get_status_summary.return_value = {
            "success": True,
            "ai_summary": "System operating normally",
        }

        controller = HVACController(
            ha_client=mock_ha_client,
            hvac_options=hvac_options,
            state_machine=state_machine,
            hvac_agent=mock_agent,
        )

        # Test controller lifecycle
        await controller.start()
        assert controller.running

        # Test status retrieval
        status = await controller.get_status()
        assert status["controller"]["running"]
        assert status["controller"]["ha_connected"]
        assert status["controller"]["temp_sensor"] == "sensor.test_temperature"

        # Test manual evaluation trigger
        result = await controller.trigger_evaluation()
        assert result["success"]

        # Cleanup
        await controller.stop()
        assert not controller.running

    @pytest.mark.asyncio
    async def test_temperature_change_handling(self, test_config, mock_ha_client):
        """Test handling of temperature sensor changes."""

        hvac_options = test_config["hvac_options"]
        state_machine = HVACStateMachine(hvac_options)

        # Mock agent
        mock_agent = AsyncMock(spec=HVACAgent)
        mock_agent.process_temperature_change.return_value = {
            "success": True,
            "action_taken": "heating",
            "new_state": "heating",
        }

        controller = HVACController(
            ha_client=mock_ha_client,
            hvac_options=hvac_options,
            state_machine=state_machine,
            hvac_agent=mock_agent,
            use_ai=True,
        )

        # Create mock temperature change event
        event_data = HassStateChangeData.from_dict(
            {
                "entity_id": "sensor.test_temperature",
                "new_state": {
                    "entity_id": "sensor.test_temperature",
                    "state": "18.5",  # Below heating threshold
                    "attributes": {"unit_of_measurement": "°C"},
                    "last_changed": "2024-01-01T12:00:00Z",
                    "last_updated": "2024-01-01T12:00:00Z",
                },
                "old_state": {
                    "entity_id": "sensor.test_temperature",
                    "state": "20.0",
                    "attributes": {"unit_of_measurement": "°C"},
                    "last_changed": "2024-01-01T11:00:00Z",
                    "last_updated": "2024-01-01T11:00:00Z",
                },
            }
        )

        event = HassEvent.from_dict(
            {
                "event_type": "state_changed",
                "data": {
                    "entity_id": "sensor.test_temperature",
                    "new_state": {
                        "entity_id": "sensor.test_temperature",
                        "state": "18.5",
                        "attributes": {"unit_of_measurement": "°C"},
                        "last_changed": "2024-01-01T12:00:00Z",
                        "last_updated": "2024-01-01T12:00:00Z",
                    },
                    "old_state": {
                        "entity_id": "sensor.test_temperature",
                        "state": "20.0",
                        "attributes": {"unit_of_measurement": "°C"},
                        "last_changed": "2024-01-01T11:00:00Z",
                        "last_updated": "2024-01-01T11:00:00Z",
                    },
                },
                "origin": "LOCAL",
                "time_fired": "2024-01-01T12:00:00Z",
            }
        )

        await controller.start()

        # Process the event
        await controller._handle_state_change(event)

        # Verify agent was called (initial evaluation + actual temperature change)
        assert mock_agent.process_temperature_change.call_count == 2
        
        # Check the actual temperature change call (last call)
        call_args = mock_agent.process_temperature_change.call_args[0][0]
        assert call_args["entity_id"] == "sensor.test_temperature"
        assert call_args["new_state"] == "18.5"

        await controller.stop()

    @pytest.mark.asyncio
    async def test_manual_override_functionality(self, test_config, mock_ha_client):
        """Test manual override functionality."""

        hvac_options = test_config["hvac_options"]
        state_machine = HVACStateMachine(hvac_options)

        # Mock agent with override support
        mock_agent = AsyncMock(spec=HVACAgent)
        mock_agent.manual_override.return_value = {
            "success": True,
            "action": "heat",
            "agent_response": "Manual heating activated",
        }

        controller = HVACController(
            ha_client=mock_ha_client,
            hvac_options=hvac_options,
            state_machine=state_machine,
            hvac_agent=mock_agent,
            use_ai=True,
        )

        await controller.start()

        # Test manual override
        result = await controller.manual_override("heat", target_temperature=22.0)

        assert result["success"] == True
        assert result["action"] == "heat"

        # Verify agent was called with correct parameters
        mock_agent.manual_override.assert_called_once_with(
            "heat", target_temperature=22.0
        )

        await controller.stop()

    @pytest.mark.asyncio
    async def test_efficiency_evaluation(self, test_config, mock_ha_client):
        """Test efficiency evaluation functionality."""

        hvac_options = test_config["hvac_options"]
        state_machine = HVACStateMachine(hvac_options)

        # Mock agent with efficiency analysis
        mock_agent = AsyncMock(spec=HVACAgent)
        mock_agent.evaluate_efficiency.return_value = {
            "success": True,
            "analysis": "System is operating efficiently",
            "recommendations": ["Maintain current settings"],
        }

        controller = HVACController(
            ha_client=mock_ha_client,
            hvac_options=hvac_options,
            state_machine=state_machine,
            hvac_agent=mock_agent,
            use_ai=True,
        )

        await controller.start()

        # Test efficiency evaluation
        result = await controller.evaluate_efficiency()

        assert result["success"] == True
        assert "analysis" in result

        # Verify agent was called
        mock_agent.evaluate_efficiency.assert_called_once()

        await controller.stop()

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, test_config, mock_ha_client):
        """Test error handling and recovery scenarios."""

        hvac_options = test_config["hvac_options"]
        state_machine = HVACStateMachine(hvac_options)

        # Mock agent that fails then recovers
        mock_agent = AsyncMock(spec=HVACAgent)
        mock_agent.process_temperature_change.side_effect = [
            Exception("Temporary failure"),  # First call fails
            {"success": True, "action_taken": "recovered"},  # Second call succeeds
        ]
        mock_agent.get_status_summary.return_value = {
            "success": True,
            "ai_summary": "System recovered",
        }

        controller = HVACController(
            ha_client=mock_ha_client,
            hvac_options=hvac_options,
            state_machine=state_machine,
            hvac_agent=mock_agent,
            use_ai=True,
        )

        await controller.start()

        # Create temperature change event
        event = HassEvent.from_dict(
            {
                "event_type": "state_changed",
                "data": {
                    "entity_id": "sensor.test_temperature",
                    "new_state": {
                        "entity_id": "sensor.test_temperature",
                        "state": "18.5",
                        "attributes": {},
                        "last_changed": "2024-01-01T12:00:00Z",
                        "last_updated": "2024-01-01T12:00:00Z",
                    },
                },
                "origin": "LOCAL",
                "time_fired": "2024-01-01T12:00:00Z",
            }
        )

        # First call should handle the error gracefully
        await controller._handle_state_change(event)

        # Controller should still be running despite the error
        assert controller.running == True

        # Second call should succeed
        await controller._handle_state_change(event)

        # Verify all calls were made (initial evaluation + 2 temperature changes)
        assert mock_agent.process_temperature_change.call_count == 3

        await controller.stop()

    def test_configuration_validation(self, test_config):
        """Test configuration validation and entity setup."""

        hvac_options = test_config["hvac_options"]

        # Test HVAC entities configuration
        assert len(hvac_options.hvac_entities) == 2

        living_room = hvac_options.hvac_entities[0]
        assert living_room.entity_id == "climate.living_room_ac"
        assert living_room.enabled == True
        assert living_room.defrost == True

        bedroom = hvac_options.hvac_entities[1]
        assert bedroom.entity_id == "climate.bedroom_ac"
        assert bedroom.enabled == True
        assert bedroom.defrost == False

        # Test temperature thresholds
        heating = hvac_options.heating
        assert heating.temperature == 21.0
        assert heating.preset_mode == "comfort"
        assert heating.temperature_thresholds.indoor_min == 19.7
        assert heating.temperature_thresholds.indoor_max == 20.2

        cooling = hvac_options.cooling
        assert cooling.temperature == 24.0
        assert cooling.preset_mode == "windFree"
        assert cooling.temperature_thresholds.indoor_min == 23.5
        assert cooling.temperature_thresholds.indoor_max == 25.0

        # Test defrost configuration
        defrost = heating.defrost
        assert defrost.temperature_threshold == 0.0
        assert defrost.period_seconds == 3600
        assert defrost.duration_seconds == 300

        # Test active hours
        active_hours = hvac_options.active_hours
        assert active_hours.start == 0
        assert active_hours.start_weekday == 0
        assert active_hours.end == 23

    @pytest.mark.asyncio
    async def test_state_machine_integration(self, test_config):
        """Test state machine integration with strategies."""

        hvac_options = test_config["hvac_options"]
        state_machine = HVACStateMachine(hvac_options)

        # Test initialization
        assert state_machine.current_state.name == "Idle"
        assert state_machine.heating_strategy is not None
        assert state_machine.cooling_strategy is not None

        # Test heating scenario
        state_machine.update_conditions(
            indoor_temp=18.5,  # Below heating threshold
            outdoor_temp=10.0,  # Within range
            hour=14,  # Active hours
            is_weekday=True,
        )

        mode = state_machine.evaluate_conditions()
        assert mode is not None
        assert mode.value == "heat"
        assert state_machine.current_state.name == "Heating"

        # Test cooling scenario
        state_machine.update_conditions(
            indoor_temp=26.0,  # Above cooling threshold
            outdoor_temp=30.0,  # Within range
            hour=14,  # Active hours
            is_weekday=True,
        )

        mode = state_machine.evaluate_conditions()
        assert mode is not None
        assert mode.value == "cool"
        assert state_machine.current_state.name == "Cooling"

        # Test comprehensive status
        status = state_machine.get_status()
        assert status["current_state"] == "Cooling"
        assert status["hvac_mode"] == "cool"
        assert status["conditions"]["indoor_temp"] == 26.0
        assert status["conditions"]["outdoor_temp"] == 30.0
        assert status["configuration"]["system_mode"] == "auto"

