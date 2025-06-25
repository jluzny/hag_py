"""
HVAC Controller - Main orchestrator for HVAC operations.

"""

import asyncio
from typing import Dict, Any, Optional, Callable
import structlog

from hag.home_assistant.client import HomeAssistantClient
from hag.home_assistant.models import HassEvent, HassServiceCall
from hag.config.settings import HvacOptions
from hag.hvac.state_machine import HVACStateMachine
from hag.hvac.agent import HVACAgent
from hag.core.exceptions import HAGError, StateError

logger = structlog.get_logger(__name__)


class HVACController:
    """
    Main HVAC controller - orchestrates all HVAC operations.


    """

    def __init__(
        self,
        ha_client: HomeAssistantClient,
        hvac_options: HvacOptions,
        state_machine: HVACStateMachine,
        hvac_agent: Optional[HVACAgent] = None,
        use_ai: bool = False,
    ):
        self.ha_client = ha_client
        self.hvac_options = hvac_options
        self.state_machine = state_machine
        self.hvac_agent = hvac_agent
        self.use_ai = use_ai and hvac_agent is not None

        self.running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._event_handlers: Dict[str, Callable] = {}

        logger.info(
            "HVAC Controller initialized",
            temp_sensor=hvac_options.temp_sensor,
            system_mode=hvac_options.system_mode,
            entities_count=len(hvac_options.hvac_entities),
            ai_enabled=self.use_ai,
        )

    async def start(self) -> None:
        """
        Start the HVAC controller.

        start functionality.
        """

        if self.running:
            logger.warning("HVAC controller already running")
            return

        logger.info("Starting HVAC controller")

        try:
            # Connect to Home Assistant
            await self.ha_client.connect()

            # Subscribe to temperature sensor events
            await self._setup_event_subscriptions()

            # Start monitoring task
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())

            # Trigger initial evaluation
            await self._trigger_initial_evaluation()

            self.running = True
            logger.info("HVAC controller started successfully")

        except Exception as e:
            logger.error("Failed to start HVAC controller", error=str(e))
            await self.stop()
            raise HAGError(f"Failed to start HVAC controller: {e}")

    async def stop(self) -> None:
        """
        Stop the HVAC controller.

        stop functionality.
        """

        logger.info("Stopping HVAC controller")

        self.running = False

        # Cancel monitoring task
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        # Disconnect from Home Assistant
        try:
            await self.ha_client.disconnect()
        except Exception as e:
            logger.warning("Error disconnecting from Home Assistant", error=str(e))

        logger.info("HVAC controller stopped")

    async def _setup_event_subscriptions(self) -> None:
        """Setup Home Assistant event subscriptions."""

        # Subscribe to state change events
        await self.ha_client.subscribe_events("state_changed")

        # Add event handler for temperature sensor changes
        self.ha_client.add_event_handler("state_changed", self._handle_state_change)

        logger.debug(
            "Event subscriptions configured", temp_sensor=self.hvac_options.temp_sensor
        )

    async def _handle_state_change(self, event: HassEvent) -> None:
        """
        Handle Home Assistant state change events.


        """

        logger.debug(
            "Received state change event",
            event_type=event.event_type,
            event_data=str(event),
        )

        if not event.is_state_changed():
            logger.debug("Event is not a state change, ignoring")
            return

        state_change = event.get_state_change_data()
        if not state_change:
            logger.debug("No state change data available")
            return

        # Log all state changes for debugging
        logger.debug(
            "State change detected",
            entity_id=state_change.entity_id,
            target_sensor=self.hvac_options.temp_sensor,
            is_target=state_change.entity_id == self.hvac_options.temp_sensor,
        )

        # Only process our temperature sensor
        if state_change.entity_id != self.hvac_options.temp_sensor:
            return

        if not state_change.new_state:
            logger.warning(
                "Temperature sensor state change with no new state",
                entity_id=state_change.entity_id,
            )
            return

        logger.debug(
            "Processing temperature sensor change",
            entity_id=state_change.entity_id,
            old_state=state_change.old_state.state if state_change.old_state else None,
            new_state=state_change.new_state.state,
        )

        try:
            if self.use_ai:
                # Prepare event data for AI agent
                event_data = {
                    "entity_id": state_change.entity_id,
                    "new_state": state_change.new_state.state,
                    "old_state": state_change.old_state.state
                    if state_change.old_state
                    else None,
                    "timestamp": event.time_fired.isoformat(),
                    "attributes": state_change.new_state.attributes,
                }

                # Process through AI agent
                if self.hvac_agent:
                    await self.hvac_agent.process_temperature_change(event_data)
            else:
                # Use direct state machine logic
                await self._process_state_change_direct(state_change)

        except Exception as e:
            logger.error(
                "Failed to process temperature change",
                entity_id=state_change.entity_id,
                error=str(e),
            )

    async def _monitoring_loop(self) -> None:
        """
        Main monitoring loop.


        """

        logger.info("Starting HVAC monitoring loop")

        # Default monitoring interval (5 minutes)
        monitoring_interval = 300

        try:
            while self.running:
                try:
                    # Perform periodic AI evaluation
                    await self._periodic_evaluation()

                    # Wait for next cycle
                    await asyncio.sleep(monitoring_interval)

                except asyncio.CancelledError:
                    logger.info("Monitoring loop cancelled")
                    break
                except Exception as e:
                    logger.error("Error in monitoring loop", error=str(e))
                    # Continue running but wait before retry
                    await asyncio.sleep(60)

        except Exception as e:
            logger.error("Monitoring loop failed", error=str(e))
        finally:
            logger.info("Monitoring loop stopped")

    async def _periodic_evaluation(self) -> None:
        """Perform periodic HVAC evaluation."""

        logger.debug("Performing periodic HVAC evaluation", ai_enabled=self.use_ai)

        try:
            if self.use_ai and self.hvac_agent:
                # Get status summary from AI agent
                status = await self.hvac_agent.get_status_summary()

                if status["success"]:
                    ai_summary = status.get("ai_summary", "")
                    ai_insights_count = (
                        len(ai_summary) if isinstance(ai_summary, str) else 0
                    )
                    logger.debug(
                        "Periodic evaluation completed", ai_insights=ai_insights_count
                    )
                else:
                    logger.warning(
                        "Periodic evaluation failed", error=status.get("error")
                    )
            else:
                # Use direct state machine evaluation
                await self._evaluate_state_machine_direct()

        except Exception as e:
            logger.error("Periodic evaluation error", error=str(e))

    async def _trigger_initial_evaluation(self) -> None:
        """Trigger initial HVAC evaluation on startup."""

        logger.info("Triggering initial HVAC evaluation", ai_enabled=self.use_ai)

        try:
            if self.use_ai:
                # Force sensor update and evaluation
                from datetime import datetime

                initial_event = {
                    "entity_id": self.hvac_options.temp_sensor,
                    "new_state": "initial_check",
                    "old_state": None,
                    "timestamp": datetime.now().isoformat(),
                }

                if self.hvac_agent:
                    await self.hvac_agent.process_temperature_change(initial_event)
            else:
                # Trigger direct state machine evaluation
                await self._evaluate_state_machine_direct()

        except Exception as e:
            logger.warning("Initial evaluation failed", error=str(e))

    async def _process_state_change_direct(self, state_change) -> None:
        """Process temperature change using direct state machine logic."""

        logger.debug(
            "Processing state change directly", entity_id=state_change.entity_id
        )

        # Parse temperature value
        try:
            new_temp = float(state_change.new_state.state)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid temperature value",
                entity_id=state_change.entity_id,
                state=state_change.new_state.state,
            )
            return

        # Get outdoor temperature (for full evaluation)
        outdoor_temp = None
        if self.hvac_options.outdoor_sensor:
            try:
                outdoor_state = await self.ha_client.get_state(
                    self.hvac_options.outdoor_sensor
                )
                outdoor_temp = outdoor_state.get_numeric_state()
            except Exception as e:
                logger.warning("Failed to get outdoor temperature", error=str(e))

        # Update state machine with conditions
        from datetime import datetime

        now = datetime.now()
        current_hour = now.hour
        is_weekday = now.weekday() < 5

        # Update state machine conditions
        self.state_machine.update_conditions(
            indoor_temp=new_temp,
            outdoor_temp=outdoor_temp or 20.0,  # Default if not available
            hour=current_hour,
            is_weekday=is_weekday,
        )

        # Evaluate and execute actions
        await self._evaluate_and_execute()

    async def _evaluate_state_machine_direct(self) -> None:
        """Perform direct state machine evaluation without AI."""

        logger.debug("Performing direct state machine evaluation")

        try:
            # Get current temperatures
            indoor_temp = None
            outdoor_temp = None

            # Get indoor temperature
            try:
                indoor_state = await self.ha_client.get_state(
                    self.hvac_options.temp_sensor
                )
                indoor_temp = indoor_state.get_numeric_state()
            except Exception as e:
                logger.warning("Failed to get indoor temperature", error=str(e))
                return

            # Get outdoor temperature
            if self.hvac_options.outdoor_sensor:
                try:
                    outdoor_state = await self.ha_client.get_state(
                        self.hvac_options.outdoor_sensor
                    )
                    outdoor_temp = outdoor_state.get_numeric_state()
                except Exception as e:
                    logger.warning("Failed to get outdoor temperature", error=str(e))

            if indoor_temp is None:
                logger.warning("No indoor temperature available for evaluation")
                return

            # Update state machine with current conditions
            from datetime import datetime

            now = datetime.now()
            current_hour = now.hour
            is_weekday = now.weekday() < 5

            self.state_machine.update_conditions(
                indoor_temp=indoor_temp,
                outdoor_temp=outdoor_temp or 20.0,  # Default if not available
                hour=current_hour,
                is_weekday=is_weekday,
            )

            # Evaluate and execute actions
            await self._evaluate_and_execute()

        except Exception as e:
            logger.error("Direct state machine evaluation failed", error=str(e))

    async def _evaluate_and_execute(self) -> None:
        """Evaluate state machine and execute HVAC actions."""

        # Get previous state for comparison
        previous_state = self.state_machine.current_state.name

        # Evaluate conditions and get recommended mode
        hvac_mode = self.state_machine.evaluate_conditions()

        current_state = self.state_machine.current_state.name

        logger.info(
            "State machine evaluation completed",
            previous_state=previous_state,
            current_state=current_state,
            recommended_mode=hvac_mode.name if hvac_mode else None,
            state_changed=previous_state != current_state,
        )

        # Execute HVAC actions if we have a valid mode recommendation
        if hvac_mode:
            logger.info(
                "Executing HVAC command",
                mode=hvac_mode.name,
                state_changed=previous_state != current_state,
                reason="state machine recommendation",
            )
            await self._execute_hvac_mode(hvac_mode)
        else:
            logger.debug("No HVAC mode recommendation, skipping execution")

    async def _execute_hvac_mode(self, hvac_mode) -> None:
        """Execute HVAC mode changes on actual devices."""

        from .state_machine import HVACMode

        # Map HVAC modes to Home Assistant climate modes
        mode_map = {HVACMode.HEAT: "heat", HVACMode.COOL: "cool", HVACMode.OFF: "off"}

        ha_mode = mode_map.get(hvac_mode)
        if not ha_mode:
            logger.warning("Unknown HVAC mode", mode=hvac_mode)
            return

        logger.info("Executing HVAC mode change", mode=ha_mode)

        # Get enabled entities
        enabled_entities = [
            entity.entity_id
            for entity in self.hvac_options.hvac_entities
            if entity.enabled
        ]

        if not enabled_entities:
            logger.warning("No enabled HVAC entities found")
            return

        # Execute mode change for each entity
        for entity_id in enabled_entities:
            try:
                # Set HVAC mode
                service_call = HassServiceCall(
                    domain="climate",
                    service="set_hvac_mode",
                    service_data={"entity_id": entity_id, "hvac_mode": ha_mode},
                )
                await self.ha_client.call_service(service_call)

                # Set temperature and preset if not turning off
                if ha_mode != "off":
                    # Set temperature
                    target_temp = (
                        self.hvac_options.heating.temperature
                        if hvac_mode == HVACMode.HEAT
                        else self.hvac_options.cooling.temperature
                    )

                    temp_service = HassServiceCall(
                        domain="climate",
                        service="set_temperature",
                        service_data={
                            "entity_id": entity_id,
                            "temperature": target_temp,
                        },
                    )
                    await self.ha_client.call_service(temp_service)

                    # Set preset mode
                    preset_mode = (
                        self.hvac_options.heating.preset_mode
                        if hvac_mode == HVACMode.HEAT
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

                    logger.info(
                        "HVAC entity configured",
                        entity_id=entity_id,
                        mode=ha_mode,
                        temperature=target_temp,
                        preset=preset_mode,
                    )
                else:
                    logger.info("HVAC entity turned off", entity_id=entity_id)

            except Exception as e:
                logger.error(
                    "Failed to control HVAC entity",
                    entity_id=entity_id,
                    mode=ha_mode,
                    error=str(e),
                )

    # Public API methods

    async def manual_override(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        Handle manual HVAC override.

        Allows external control with or without AI validation.
        """

        logger.info(
            "Manual override requested",
            action=action,
            kwargs=kwargs,
            ai_enabled=self.use_ai,
        )

        if not self.running:
            raise StateError("HVAC controller is not running")

        try:
            if self.use_ai and self.hvac_agent:
                return await self.hvac_agent.manual_override(action, **kwargs)
            else:
                # Direct manual override without AI
                from .state_machine import HVACMode

                mode_map = {
                    "heat": HVACMode.HEAT,
                    "cool": HVACMode.COOL,
                    "off": HVACMode.OFF,
                }

                hvac_mode = mode_map.get(action.lower())
                if not hvac_mode:
                    raise ValueError(f"Invalid action: {action}")

                await self._execute_hvac_mode(hvac_mode)

                return {
                    "success": True,
                    "action": action,
                    "mode": hvac_mode.name,
                    "timestamp": self._get_timestamp(),
                }
        except Exception as e:
            logger.error("Manual override failed", action=action, error=str(e))
            raise HAGError(f"Manual override failed: {e}")

    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive HVAC system status."""

        try:
            # Get machine status
            machine_status = self.state_machine.get_status()

            # Combine with controller status
            status = {
                "controller": {
                    "running": self.running,
                    "ha_connected": self.ha_client.connected,
                    "temp_sensor": self.hvac_options.temp_sensor,
                    "system_mode": self.hvac_options.system_mode.value,
                    "ai_enabled": self.use_ai,
                },
                "state_machine": machine_status,
                "timestamp": self._get_timestamp(),
            }

            # Add AI analysis if available
            if self.use_ai and self.hvac_agent:
                try:
                    ai_status = await self.hvac_agent.get_status_summary()
                    status["ai_analysis"] = (
                        ai_status.get("ai_summary", "")
                        if ai_status["success"]
                        else None
                    )
                except Exception as e:
                    logger.warning("Failed to get AI status", error=str(e))
                    status["ai_analysis"] = f"AI analysis failed: {e}"

            return status

        except Exception as e:
            logger.error("Failed to get status", error=str(e))
            return {
                "controller": {
                    "running": self.running,
                    "error": str(e),
                    "ai_enabled": self.use_ai,
                },
                "timestamp": self._get_timestamp(),
            }

    async def evaluate_efficiency(self) -> Dict[str, Any]:
        """Perform efficiency analysis."""

        if not self.running:
            raise StateError("HVAC controller is not running")

        try:
            if self.use_ai and self.hvac_agent:
                return await self.hvac_agent.evaluate_efficiency()
            else:
                # Simple efficiency analysis without AI
                status = self.state_machine.get_status()
                return {
                    "success": True,
                    "analysis": f"State machine mode: {status.get('current_state', 'unknown')}",
                    "timestamp": self._get_timestamp(),
                }
        except Exception as e:
            logger.error("Efficiency evaluation failed", error=str(e))
            raise HAGError(f"Efficiency evaluation failed: {e}")

    async def trigger_evaluation(self) -> Dict[str, Any]:
        """Manually trigger HVAC evaluation."""

        logger.info("Manual evaluation triggered", ai_enabled=self.use_ai)

        if not self.running:
            raise StateError("HVAC controller is not running")

        try:
            # Trigger immediate evaluation
            await self._periodic_evaluation()

            return {
                "success": True,
                "message": f"Evaluation triggered successfully ({'AI' if self.use_ai else 'State machine'} mode)",
                "timestamp": self._get_timestamp(),
            }

        except Exception as e:
            logger.error("Manual evaluation failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "timestamp": self._get_timestamp(),
            }

    def add_event_handler(self, event_type: str, handler: Callable) -> None:
        """Add custom event handler."""
        self._event_handlers[event_type] = handler
        logger.debug("Added custom event handler", event_type=event_type)

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime

        return datetime.now().isoformat()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self):
        """Async context manager exit."""
        await self.stop()
