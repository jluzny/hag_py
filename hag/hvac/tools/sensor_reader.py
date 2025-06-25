"""
LangChain tool for reading Home Assistant sensors.

General-purpose sensor reading tool for AI decision making.
"""

from typing import Dict, Any, List, Optional, Union, Type
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
import structlog

from ...home_assistant.client import HomeAssistantClient

logger = structlog.get_logger(__name__)

class SensorReaderInput(BaseModel):
    """Input schema for sensor reader tool."""

    entity_ids: Union[str, List[str]] = Field(
        description="Single entity ID or list of entity IDs to read"
    )
    include_attributes: bool = Field(
        default=False, description="Include entity attributes in response"
    )
    filter_numeric: bool = Field(
        default=False, description="Only return numeric sensor values"
    )

class SensorReaderTool(BaseTool):
    """
    LangChain tool for reading sensor data from Home Assistant.

    General-purpose tool for AI agents to gather environmental data.
    """

    name: str = "sensor_reader"
    description: str = """Read current state and values from Home Assistant sensors.
    
    This tool:
    - Reads current state from any Home Assistant entity
    - Can read single sensors or multiple sensors at once
    - Optionally includes entity attributes (like units, device info)
    - Can filter to only numeric values for calculations
    - Provides timestamp and data freshness information
    
    Use this tool when you need to:
    - Check current sensor values for decision making
    - Gather environmental data (temperature, humidity, etc.)
    - Read status of devices or systems
    - Get multiple sensor readings for analysis"""

    args_schema: Union[Type[BaseModel], Dict[str, Any], None] = SensorReaderInput
    ha_client: HomeAssistantClient = Field(exclude=True)

    def __init__(self, ha_client: HomeAssistantClient):
        super().__init__(ha_client=ha_client)

    async def _arun(
        self,
        entity_ids: Union[str, List[str]],
        include_attributes: bool = False,
        filter_numeric: bool = False,
    ) -> Dict[str, Any]:
        """Async implementation of sensor reading."""

        # Normalize entity_ids to list
        if isinstance(entity_ids, str):
            entity_list = [entity_ids]
        else:
            entity_list = entity_ids

        logger.info(
            "Reading sensors",
            entity_count=len(entity_list),
            include_attributes=include_attributes,
            filter_numeric=filter_numeric,
        )

        results = {}
        errors = {}
        numeric_values = {}

        for entity_id in entity_list:
            try:
                # Read entity state
                state = await self.ha_client.get_state(entity_id)

                # Prepare basic result
                entity_result = {
                    "entity_id": entity_id,
                    "state": state.state,
                    "last_updated": state.last_updated.isoformat(),
                    "last_changed": state.last_changed.isoformat(),
                }

                # Add attributes if requested
                if include_attributes:
                    entity_result["attributes"] = str(state.attributes)

                # Try to get numeric value
                numeric_value = state.get_numeric_state()
                if numeric_value is not None:
                    entity_result["numeric_value"] = str(numeric_value)
                    entity_result["is_numeric"] = "true"
                    numeric_values[entity_id] = numeric_value

                    # Add unit from attributes if available
                    unit = state.attributes.get("unit_of_measurement")
                    if unit:
                        entity_result["unit"] = unit
                else:
                    entity_result["is_numeric"] = "false"

                # Add to results if not filtering or if numeric when filtering
                if not filter_numeric or entity_result["is_numeric"]:
                    results[entity_id] = entity_result

            except Exception as e:
                error_msg = str(e)
                errors[entity_id] = error_msg
                logger.error(
                    "Failed to read sensor", entity_id=entity_id, error=error_msg
                )

        # Compile response
        from datetime import datetime

        response = {
            "success": len(results) > 0,
            "timestamp": datetime.now().isoformat(),
            "requested_entities": len(entity_list),
            "successful_reads": len(results),
            "failed_reads": len(errors),
            "sensors": results,
        }

        # Add numeric analysis if we have numeric values
        if numeric_values:
            response["numeric_analysis"] = {
                "count": len(numeric_values),
                "values": numeric_values,
                "min_value": min(numeric_values.values()),
                "max_value": max(numeric_values.values()),
                "average": sum(numeric_values.values()) / len(numeric_values),
            }

        # Add errors if any
        if errors:
            response["errors"] = errors

        # Add helpful summary
        if len(entity_list) == 1:
            entity_id = entity_list[0]
            if entity_id in results:
                sensor_data = results[entity_id]
                response["summary"] = f"Sensor {entity_id}: {sensor_data['state']}"
                if sensor_data.get("unit"):
                    response["summary"] += f" {sensor_data['unit']}"
            else:
                response["summary"] = f"Failed to read sensor {entity_id}"
        else:
            response["summary"] = (
                f"Read {len(results)}/{len(entity_list)} sensors successfully"
            )

        logger.info(
            "Sensor reading completed",
            successful=len(results),
            failed=len(errors),
            numeric_count=len(numeric_values),
        )

        return response

    def _run(self, **kwargs) -> str:
        """Sync wrapper - not implemented for async tool."""
        raise NotImplementedError("This tool requires async execution")

    async def read_temperature_sensors(
        self, indoor_sensor: str, outdoor_sensor: str
    ) -> Dict[str, Any]:
        """Convenience method for reading temperature sensors specifically."""
        return await self._arun(
            entity_ids=[indoor_sensor, outdoor_sensor],
            include_attributes=True,
            filter_numeric=True,
        )

    async def read_climate_entity(self, climate_entity: str) -> Dict[str, Any]:
        """Convenience method for reading climate entity status."""
        return await self._arun(
            entity_ids=climate_entity, include_attributes=True, filter_numeric=False
        )

