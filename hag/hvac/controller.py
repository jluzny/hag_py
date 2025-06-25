"""
HVAC Controller - Main orchestrator for HVAC operations.

"""

import asyncio
from typing import Dict, Any, Optional, Callable
import structlog

from ..home_assistant.client import HomeAssistantClient
from ..home_assistant.models import HassEvent
from ..config.settings import HvacOptions
from .state_machine import HVACStateMachine
from .agent import HVACAgent
from ..core.exceptions import HAGError, StateError

logger = structlog.get_logger(__name__)

class HVACController:
    """
    Main HVAC controller - orchestrates all HVAC operations.
    
    
    """
    
    def __init__(self,
                 ha_client: HomeAssistantClient,
                 hvac_options: HvacOptions,
                 state_machine: HVACStateMachine,
                 hvac_agent: HVACAgent):
        
        self.ha_client = ha_client
        self.hvac_options = hvac_options
        self.state_machine = state_machine
        self.hvac_agent = hvac_agent
        
        self.running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._event_handlers: Dict[str, Callable] = {}
        
        logger.info("HVAC Controller initialized",
                   temp_sensor=hvac_options.temp_sensor,
                   system_mode=hvac_options.system_mode,
                   entities_count=len(hvac_options.hvac_entities))

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
        
        logger.debug("Event subscriptions configured",
                    temp_sensor=self.hvac_options.temp_sensor)

    async def _handle_state_change(self, event: HassEvent) -> None:
        """
        Handle Home Assistant state change events.
        
        
        """
        
        if not event.is_state_changed():
            return
        
        state_change = event.get_state_change_data()
        if not state_change:
            return
        
        # Only process our temperature sensor
        if state_change.entity_id != self.hvac_options.temp_sensor:
            return
        
        if not state_change.new_state:
            logger.warning("Temperature sensor state change with no new state",
                          entity_id=state_change.entity_id)
            return
        
        logger.debug("Processing temperature sensor change",
                    entity_id=state_change.entity_id,
                    old_state=state_change.old_state.state if state_change.old_state else None,
                    new_state=state_change.new_state.state)
        
        try:
            # Prepare event data for AI agent
            event_data = {
                "entity_id": state_change.entity_id,
                "new_state": state_change.new_state.state,
                "old_state": state_change.old_state.state if state_change.old_state else None,
                "timestamp": event.time_fired.isoformat(),
                "attributes": state_change.new_state.attributes
            }
            
            # Process through AI agent
            await self.hvac_agent.process_temperature_change(event_data)
            
        except Exception as e:
            logger.error("Failed to process temperature change",
                        entity_id=state_change.entity_id,
                        error=str(e))

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
        """Perform periodic HVAC evaluation using AI agent."""
        
        logger.debug("Performing periodic HVAC evaluation")
        
        try:
            # Get status summary from AI agent
            status = await self.hvac_agent.get_status_summary()
            
            if status["success"]:
                ai_summary = status.get("ai_summary", "")
                ai_insights_count = len(ai_summary) if isinstance(ai_summary, str) else 0
                logger.debug("Periodic evaluation completed",
                           ai_insights=ai_insights_count)
            else:
                logger.warning("Periodic evaluation failed", 
                             error=status.get("error"))
                
        except Exception as e:
            logger.error("Periodic evaluation error", error=str(e))

    async def _trigger_initial_evaluation(self) -> None:
        """Trigger initial HVAC evaluation on startup."""
        
        logger.info("Triggering initial HVAC evaluation")
        
        try:
            # Force sensor update and evaluation
            from datetime import datetime
            
            initial_event = {
                "entity_id": self.hvac_options.temp_sensor,
                "new_state": "initial_check",
                "old_state": None,
                "timestamp": datetime.now().isoformat()
            }
            
            await self.hvac_agent.process_temperature_change(initial_event)
            
        except Exception as e:
            logger.warning("Initial evaluation failed", error=str(e))

    # Public API methods

    async def manual_override(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        Handle manual HVAC override.
        
        Allows external control while leveraging AI validation.
        """
        
        logger.info("Manual override requested", action=action, kwargs=kwargs)
        
        if not self.running:
            raise StateError("HVAC controller is not running")
        
        try:
            return await self.hvac_agent.manual_override(action, **kwargs)
        except Exception as e:
            logger.error("Manual override failed", action=action, error=str(e))
            raise HAGError(f"Manual override failed: {e}")

    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive HVAC system status."""
        
        try:
            # Get AI-powered status summary
            ai_status = await self.hvac_agent.get_status_summary()
            
            # Get machine status
            machine_status = self.state_machine.get_status()
            
            # Combine with controller status
            status = {
                "controller": {
                    "running": self.running,
                    "ha_connected": self.ha_client.connected,
                    "temp_sensor": self.hvac_options.temp_sensor,
                    "system_mode": self.hvac_options.system_mode.value
                },
                "state_machine": machine_status,
                "ai_analysis": ai_status.get("ai_summary", "") if ai_status["success"] else None,
                "timestamp": self._get_timestamp()
            }
            
            return status
            
        except Exception as e:
            logger.error("Failed to get status", error=str(e))
            return {
                "controller": {
                    "running": self.running,
                    "error": str(e)
                },
                "timestamp": self._get_timestamp()
            }

    async def evaluate_efficiency(self) -> Dict[str, Any]:
        """Perform AI-powered efficiency analysis."""
        
        if not self.running:
            raise StateError("HVAC controller is not running")
        
        try:
            return await self.hvac_agent.evaluate_efficiency()
        except Exception as e:
            logger.error("Efficiency evaluation failed", error=str(e))
            raise HAGError(f"Efficiency evaluation failed: {e}")

    async def trigger_evaluation(self) -> Dict[str, Any]:
        """Manually trigger HVAC evaluation."""
        
        logger.info("Manual evaluation triggered")
        
        if not self.running:
            raise StateError("HVAC controller is not running")
        
        try:
            # Trigger immediate evaluation
            await self._periodic_evaluation()
            
            return {
                "success": True,
                "message": "Evaluation triggered successfully",
                "timestamp": self._get_timestamp()
            }
            
        except Exception as e:
            logger.error("Manual evaluation failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "timestamp": self._get_timestamp()
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

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()