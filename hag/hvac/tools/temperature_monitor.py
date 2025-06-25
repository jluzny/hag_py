"""
LangChain tool for temperature monitoring.

Enhanced version of Jido Action with LangChain integration.
"""

from typing import Dict, Any, Type
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
import structlog
from datetime import datetime

from ...home_assistant.client import HomeAssistantClient
from ...home_assistant.models import HassServiceCall
from ..state_machine import HVACStateMachine

logger = structlog.get_logger(__name__)


class TemperatureMonitorInput(BaseModel):
    """Input schema for temperature monitoring tool."""

    indoor_sensor: str = Field(description="Indoor temperature sensor entity ID")
    outdoor_sensor: str = Field(description="Outdoor temperature sensor entity ID")
    force_update: bool = Field(default=False, description="Force sensor state update")


class TemperatureMonitorTool(BaseTool):
    """
    LangChain tool for monitoring temperature sensors and updating HVAC state.

    """

    name: str = "temperature_monitor"
    description: str = """Monitor indoor and outdoor temperature sensors and update HVAC system state.
    
    This tool:
    - Reads current temperature from specified sensors
    - Updates the HVAC state machine with current conditions
    - Returns comprehensive temperature and system status
    - Can optionally force sensor updates before reading
    
    Use this tool when you need current temperature data or want to trigger HVAC evaluation."""

    args_schema: Type[BaseModel] | None = TemperatureMonitorInput

    def __init__(self, ha_client: HomeAssistantClient, state_machine: HVACStateMachine):
        super().__init__()
        self.ha_client = ha_client
        self.state_machine = state_machine

    async def _arun(
        self, indoor_sensor: str, outdoor_sensor: str, force_update: bool = False
    ) -> Dict[str, Any]:
        """Async implementation of temperature monitoring."""

        logger.info(
            "Starting temperature monitoring",
            indoor_sensor=indoor_sensor,
            outdoor_sensor=outdoor_sensor,
            force_update=force_update,
        )

        try:
            # Force sensor update if requested
            if force_update:
                await self._force_sensor_updates([indoor_sensor, outdoor_sensor])

            # Read temperature sensors
            indoor_state = await self.ha_client.get_state(indoor_sensor)
            outdoor_state = await self.ha_client.get_state(outdoor_sensor)

            # Parse temperatures
            indoor_temp = indoor_state.get_numeric_state()
            outdoor_temp = outdoor_state.get_numeric_state()

            if indoor_temp is None:
                raise ValueError(
                    f"Indoor sensor {indoor_sensor} has non-numeric state: {indoor_state.state}"
                )

            if outdoor_temp is None:
                raise ValueError(
                    f"Outdoor sensor {outdoor_sensor} has non-numeric state: {outdoor_state.state}"
                )

            now = datetime.now()
            current_hour = now.hour
            is_weekday = now.weekday() < 5  # Monday=0, Sunday=6

            # Update state machine with new conditions
            previous_state = self.state_machine.current_state.name
            self.state_machine.update_conditions(
                indoor_temp=indoor_temp,
                outdoor_temp=outdoor_temp,
                hour=current_hour,
                is_weekday=is_weekday,
            )
            current_state = self.state_machine.current_state.name

            # Get comprehensive status
            status = self.state_machine.get_status()

            result = {
                "success": True,
                "timestamp": now.isoformat(),
                "temperatures": {
                    "indoor": {
                        "value": indoor_temp,
                        "unit": "°C",
                        "sensor": indoor_sensor,
                        "last_updated": indoor_state.last_updated.isoformat(),
                    },
                    "outdoor": {
                        "value": outdoor_temp,
                        "unit": "°C",
                        "sensor": outdoor_sensor,
                        "last_updated": outdoor_state.last_updated.isoformat(),
                    },
                },
                "time_info": {"hour": current_hour, "is_weekday": is_weekday},
                "state_machine": {
                    "previous_state": previous_state,
                    "current_state": current_state,
                    "state_changed": previous_state != current_state,
                    "full_status": status,
                },
                "conditions_analysis": self._analyze_conditions(
                    indoor_temp, outdoor_temp
                ),
            }

            logger.info(
                "Temperature monitoring completed",
                indoor_temp=indoor_temp,
                outdoor_temp=outdoor_temp,
                state_change=previous_state != current_state,
                current_state=current_state,
            )

            return result

        except Exception as e:
            logger.error("Temperature monitoring failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def _run(self) -> str:
        """Sync wrapper - not implemented for async tool."""
        raise NotImplementedError("This tool requires async execution")

    async def _force_sensor_updates(self, sensor_entities: list) -> None:
        """Force update of sensor entities."""
        logger.debug("Forcing sensor updates", sensors=sensor_entities)

        for sensor in sensor_entities:
            try:
                # Call homeassistant.update_entity service
                service_call = HassServiceCall(
                    domain="homeassistant",
                    service="update_entity",
                    service_data={"entity_id": sensor},
                )
                await self.ha_client.call_service(service_call)

            except Exception as e:
                logger.warning(
                    "Failed to force update sensor", sensor=sensor, error=str(e)
                )

    def _analyze_conditions(
        self, indoor_temp: float, outdoor_temp: float
    ) -> Dict[str, Any]:
        """Analyze current conditions and provide insights."""

        config = self.state_machine.state_data.hvac_options
        heating_thresholds = config.heating.temperature_thresholds
        cooling_thresholds = config.cooling.temperature_thresholds

        analysis = {
            "comfort_status": "unknown",
            "efficiency_notes": [],
            "recommendations": [],
            "thresholds_status": {},
        }

        # Comfort analysis
        if indoor_temp < heating_thresholds.indoor_min:
            analysis["comfort_status"] = "too_cold"
            analysis["recommendations"].append(
                f"Indoor temperature {indoor_temp:.1f}°C is below comfort minimum {heating_thresholds.indoor_min}°C"
            )
        elif indoor_temp > cooling_thresholds.indoor_max:
            analysis["comfort_status"] = "too_hot"
            analysis["recommendations"].append(
                f"Indoor temperature {indoor_temp:.1f}°C is above comfort maximum {cooling_thresholds.indoor_max}°C"
            )
        elif (
            heating_thresholds.indoor_max
            <= indoor_temp
            <= cooling_thresholds.indoor_min
        ):
            analysis["comfort_status"] = "comfortable"
        else:
            analysis["comfort_status"] = "marginal"

        # Efficiency analysis
        temp_diff = abs(indoor_temp - outdoor_temp)
        if config.system_mode.value == "auto":
            if temp_diff < 5:
                analysis["efficiency_notes"].append(
                    "Small indoor/outdoor temperature difference - good efficiency conditions"
                )
            elif temp_diff > 20:
                analysis["efficiency_notes"].append(
                    "Large temperature difference - HVAC will work harder"
                )

        # Threshold status
        analysis["thresholds_status"] = {
            "heating_can_operate": heating_thresholds.outdoor_min
            <= outdoor_temp
            <= heating_thresholds.outdoor_max,
            "cooling_can_operate": cooling_thresholds.outdoor_min
            <= outdoor_temp
            <= cooling_thresholds.outdoor_max,
            "within_heating_range": heating_thresholds.indoor_min
            <= indoor_temp
            <= heating_thresholds.indoor_max,
            "within_cooling_range": cooling_thresholds.indoor_min
            <= indoor_temp
            <= cooling_thresholds.indoor_max,
        }

        return analysis
