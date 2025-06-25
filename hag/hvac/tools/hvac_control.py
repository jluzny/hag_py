"""
LangChain tool for HVAC control operations.

Enhanced version of Elixir HvacControl action with AI decision support.
"""

from typing import Dict, Any, List, Optional, Type
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
import structlog

from ...home_assistant.client import HomeAssistantClient
from ...home_assistant.models import HassServiceCall
from ...config.settings import HvacOptions
from ..state_machine import HVACMode, HVACStateMachine

logger = structlog.get_logger(__name__)

class HVACControlInput(BaseModel):
    """Input schema for HVAC control tool."""

    action: str = Field(
        description="HVAC action: 'heat', 'cool', 'off', or 'auto_evaluate'"
    )
    target_temperature: Optional[float] = Field(
        default=None, description="Target temperature (optional)"
    )
    preset_mode: Optional[str] = Field(
        default=None, description="Preset mode override (optional)"
    )
    entities: Optional[List[str]] = Field(
        default=None, description="Specific entities to control (optional)"
    )
    force: bool = Field(
        default=False, description="Force action even if state machine disagrees"
    )

class HVACControlTool(BaseTool):
    """
    LangChain tool for controlling HVAC entities.

    
    """

    name: str = "hvac_control"
    description: str = """Control HVAC entities (heating, cooling, or turning off).
    
    This tool:
    - Controls climate entities in Home Assistant
    - Validates actions against current conditions and thresholds
    - Updates state machine to reflect changes
    - Provides comprehensive feedback on actions taken
    - Can override state machine decisions when forced
    
    Actions:
    - 'heat': Switch to heating mode
    - 'cool': Switch to cooling mode  
    - 'off': Turn off HVAC system
    - 'auto_evaluate': Let state machine decide based on current conditions
    
    Use this tool when you need to change HVAC operation or implement AI-driven decisions."""

    args_schema: Type[BaseModel] = HVACControlInput
    ha_client: HomeAssistantClient = Field(exclude=True)
    hvac_options: HvacOptions = Field(exclude=True)
    state_machine: HVACStateMachine = Field(exclude=True)

    def __init__(
        self,
        ha_client: HomeAssistantClient,
        hvac_options: HvacOptions,
        state_machine: HVACStateMachine,
    ):
        super().__init__(ha_client=ha_client, hvac_options=hvac_options, state_machine=state_machine)

    async def _arun(
        self,
        action: str,
        target_temperature: Optional[float] = None,
        preset_mode: Optional[str] = None,
        entities: Optional[List[str]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Async implementation of HVAC control."""

        logger.info(
            "Starting HVAC control",
            action=action,
            target_temperature=target_temperature,
            preset_mode=preset_mode,
            entities=entities,
            force=force,
        )

        try:
            # Validate action
            valid_actions = ["heat", "cool", "off", "auto_evaluate"]
            if action not in valid_actions:
                raise ValueError(
                    f"Invalid action '{action}'. Must be one of: {valid_actions}"
                )

            # Get entities to control
            target_entities = self._get_target_entities(entities)
            if not target_entities:
                raise ValueError("No enabled HVAC entities found")

            # Handle auto_evaluate action
            if action == "auto_evaluate":
                return await self._handle_auto_evaluate()

            # Validate action against current conditions (unless forced)
            if not force:
                validation_result = self._validate_action(action, target_temperature)
                if not validation_result["valid"]:
                    return {
                        "success": False,
                        "action": action,
                        "validation_failed": True,
                        "reason": validation_result["reason"],
                        "recommendations": validation_result.get("recommendations", []),
                        "force_hint": "Add 'force: true' to override validation",
                    }

            # Execute the action
            result = await self._execute_hvac_action(
                action=action,
                target_temperature=target_temperature,
                preset_mode=preset_mode,
                entities=target_entities,
            )

            # Update state machine if successful
            if result["success"]:
                self._update_state_machine_for_action(action)

            logger.info(
                "HVAC control completed",
                action=action,
                success=result["success"],
                entities_controlled=len(target_entities),
            )

            return result

        except Exception as e:
            logger.error("HVAC control failed", action=action, error=str(e))
            return {
                "success": False,
                "action": action,
                "error": str(e),
                "timestamp": self._get_timestamp(),
            }

    def _run(self, **kwargs) -> str:
        """Sync wrapper - not implemented for async tool."""
        raise NotImplementedError("This tool requires async execution")

    def _get_target_entities(self, entities: Optional[List[str]]) -> List[str]:
        """Get list of entities to control."""
        if entities:
            # Use provided entities
            return entities

        # Use enabled entities from configuration
        return [
            entity.entity_id
            for entity in self.hvac_options.hvac_entities
            if entity.enabled
        ]

    def _validate_action(
        self, action: str, target_temperature: Optional[float]
    ) -> Dict[str, Any]:
        """Validate action against current conditions and configuration."""

        conditions = self.state_machine.state_data

        # Check if we have valid conditions
        if not conditions.current_temp or not conditions.outdoor_temp:
            return {
                "valid": False,
                "reason": "Missing temperature data for validation",
                "recommendations": [
                    "Ensure temperature sensors are working and data is current"
                ],
            }

        indoor_temp = conditions.current_temp
        outdoor_temp = conditions.outdoor_temp

        validation = {"valid": True, "reason": "", "recommendations": []}

        # Validate heating action
        if action == "heat":
            heating_thresholds = self.hvac_options.heating.temperature_thresholds

            # Check if outdoor conditions allow heating
            if not (
                heating_thresholds.outdoor_min
                <= outdoor_temp
                <= heating_thresholds.outdoor_max
            ):
                validation.update(
                    {
                        "valid": False,
                        "reason": f"Outdoor temperature {outdoor_temp:.1f}°C is outside heating range ({heating_thresholds.outdoor_min}°C to {heating_thresholds.outdoor_max}°C)",
                        "recommendations": [
                            "Wait for better outdoor conditions",
                            "Check heating threshold configuration",
                        ],
                    }
                )
                return validation

            # Check if heating is actually needed
            if indoor_temp >= heating_thresholds.indoor_max:
                validation["recommendations"].append(
                    f"Indoor temperature {indoor_temp:.1f}°C is already above heating target range"
                )

            # Validate target temperature
            if target_temperature and target_temperature > 30:
                validation["recommendations"].append(
                    f"Target temperature {target_temperature}°C seems high for heating"
                )

        # Validate cooling action
        elif action == "cool":
            cooling_thresholds = self.hvac_options.cooling.temperature_thresholds

            # Check if outdoor conditions allow cooling
            if not (
                cooling_thresholds.outdoor_min
                <= outdoor_temp
                <= cooling_thresholds.outdoor_max
            ):
                validation.update(
                    {
                        "valid": False,
                        "reason": f"Outdoor temperature {outdoor_temp:.1f}°C is outside cooling range ({cooling_thresholds.outdoor_min}°C to {cooling_thresholds.outdoor_max}°C)",
                        "recommendations": [
                            "Wait for better outdoor conditions",
                            "Check cooling threshold configuration",
                        ],
                    }
                )
                return validation

            # Check if cooling is actually needed
            if indoor_temp <= cooling_thresholds.indoor_min:
                validation["recommendations"].append(
                    f"Indoor temperature {indoor_temp:.1f}°C is already below cooling target range"
                )

            # Validate target temperature
            if target_temperature and target_temperature < 18:
                validation["recommendations"].append(
                    f"Target temperature {target_temperature}°C seems low for cooling"
                )

        # Check active hours
        if not conditions.should_be_active() and action != "off":
            validation["recommendations"].append(
                "HVAC action requested outside configured active hours"
            )

        return validation

    async def _handle_auto_evaluate(self) -> Dict[str, Any]:
        """Handle auto_evaluate action by letting state machine decide."""

        logger.info("Performing automatic HVAC evaluation")

        # Trigger state machine evaluation
        previous_state = self.state_machine.current_state.name
        hvac_mode = self.state_machine.evaluate_conditions()
        current_state = self.state_machine.current_state.name

        if hvac_mode is None:
            return {
                "success": False,
                "action": "auto_evaluate",
                "reason": "Cannot evaluate - missing sensor data",
                "recommendations": [
                    "Check temperature sensors",
                    "Ensure sensors are reporting current data",
                ],
            }

        # Execute the determined action
        action_map = {HVACMode.HEAT: "heat", HVACMode.COOL: "cool", HVACMode.OFF: "off"}

        determined_action = action_map[hvac_mode]

        if previous_state != current_state:
            # State changed - execute the action
            entities = self._get_target_entities(None)
            result = await self._execute_hvac_action(
                action=determined_action,
                target_temperature=None,  # Use defaults
                preset_mode=None,
                entities=entities,
            )

            result.update(
                {
                    "action": "auto_evaluate",
                    "determined_action": determined_action,
                    "state_changed": True,
                    "previous_state": previous_state,
                    "current_state": current_state,
                }
            )
        else:
            # No state change needed
            result = {
                "success": True,
                "action": "auto_evaluate",
                "determined_action": determined_action,
                "state_changed": False,
                "current_state": current_state,
                "message": f"No change needed - already in optimal state ({current_state})",
            }

        return result

    async def _execute_hvac_action(
        self,
        action: str,
        target_temperature: Optional[float],
        preset_mode: Optional[str],
        entities: List[str],
    ) -> Dict[str, Any]:
        """Execute the actual HVAC control actions."""

        from datetime import datetime

        results = []
        errors = []

        for entity_id in entities:
            entity_result = {
                "entity_id": entity_id,
                "actions_taken": [],
                "success": True,
                "errors": [],
            }

            try:
                # Set HVAC mode
                hvac_mode_map = {"heat": "heat", "cool": "cool", "off": "off"}

                mode = hvac_mode_map[action]

                # Call set_hvac_mode service
                service_call = HassServiceCall(
                    domain="climate",
                    service="set_hvac_mode",
                    service_data={"entity_id": entity_id, "hvac_mode": mode},
                )

                await self.ha_client.call_service(service_call)
                entity_result["actions_taken"].append(f"Set HVAC mode to {mode}")

                # Set temperature if provided or use defaults
                if action in ["heat", "cool"]:
                    if target_temperature is None:
                        target_temperature = (
                            self.hvac_options.heating.temperature
                            if action == "heat"
                            else self.hvac_options.cooling.temperature
                        )

                    temp_service = HassServiceCall(
                        domain="climate",
                        service="set_temperature",
                        service_data={
                            "entity_id": entity_id,
                            "temperature": target_temperature,
                        },
                    )

                    await self.ha_client.call_service(temp_service)
                    entity_result["actions_taken"].append(
                        f"Set temperature to {target_temperature}°C"
                    )

                    # Set preset mode if provided or use defaults
                    if preset_mode is None:
                        preset_mode = (
                            self.hvac_options.heating.preset_mode
                            if action == "heat"
                            else self.hvac_options.cooling.preset_mode
                        )

                    preset_service = HassServiceCall(
                        domain="climate",
                        service="set_preset_mode",
                        service_data={
                            "entity_id": entity_id,
                            "preset_mode": preset_mode,
                        },
                    )

                    await self.ha_client.call_service(preset_service)
                    entity_result["actions_taken"].append(
                        f"Set preset mode to {preset_mode}"
                    )

            except Exception as e:
                entity_result["success"] = False
                entity_result["errors"].append(str(e))
                errors.append(f"{entity_id}: {str(e)}")
                logger.error(
                    "Failed to control HVAC entity", entity_id=entity_id, error=str(e)
                )

            results.append(entity_result)

        # Compile overall result
        overall_success = all(r["success"] for r in results)

        return {
            "success": overall_success,
            "action": action,
            "timestamp": datetime.now().isoformat(),
            "entities_controlled": len(entities),
            "entities_successful": sum(1 for r in results if r["success"]),
            "target_temperature": target_temperature,
            "preset_mode": preset_mode,
            "detailed_results": results,
            "errors": errors if errors else None,
        }

    def _update_state_machine_for_action(self, action: str) -> None:
        """Update state machine to reflect manual action."""
        # Note: In a full implementation, you might want to
        # manually trigger state transitions here if the action
        # was forced and doesn't match the state machine's decision
        logger.debug(
            "HVAC action completed, state machine will update on next evaluation",
            action=action,
        )

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime

        return datetime.now().isoformat()

