"""
HVAC state machine implementation.

"""

from statemachine import StateMachine, State
from statemachine.mixins import MachineMixin
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass
import structlog

from ..config.settings import HvacOptions, SystemMode

logger = structlog.get_logger(__name__)

@dataclass
class StateChangeData:
    """
    State change data container.
    
    
    """
    current_temp: float
    weather_temp: float
    hour: int
    is_weekday: bool

class HVACMode(str, Enum):
    """HVAC operational modes ."""
    HEAT = "heat"
    COOL = "cool"
    OFF = "off"

class HVACState:
    """State data container for HVAC state machine."""
    
    def __init__(self, hvac_options: HvacOptions):
        self.hvac_options = hvac_options
        self.current_temp: Optional[float] = None
        self.outdoor_temp: Optional[float] = None
        self.current_hour: Optional[int] = None
        self.is_weekday: Optional[bool] = None
        self.last_decision: Optional[Dict[str, Any]] = None
        self.defrost_needed: bool = False

    def update_conditions(self, indoor_temp: float, outdoor_temp: float, 
                         hour: int, is_weekday: bool) -> None:
        """Update current conditions ."""
        self.current_temp = indoor_temp
        self.outdoor_temp = outdoor_temp
        self.current_hour = hour
        self.is_weekday = is_weekday
        
        # Check if defrost is needed
        if (self.hvac_options.heating.defrost and 
            outdoor_temp <= self.hvac_options.heating.defrost.temperature_threshold):
            self.defrost_needed = True
        
        logger.debug("Updated HVAC conditions",
                    indoor_temp=indoor_temp,
                    outdoor_temp=outdoor_temp,
                    hour=hour,
                    is_weekday=is_weekday,
                    defrost_needed=self.defrost_needed)

    def should_be_active(self) -> bool:
        """Check if HVAC should be active based on time schedule."""
        if not self.hvac_options.active_hours or self.current_hour is None:
            return True
        
        active_hours = self.hvac_options.active_hours
        # Note: despite the name, start_weekday is actually the weekend start hour
        start_hour = active_hours.start if self.is_weekday else active_hours.start_weekday
        
        
        # Simple time range check (doesn't handle overnight ranges)
        return start_hour <= self.current_hour <= active_hours.end

class HVACStateMachine(StateMachine):
    """
    HVAC state machine - direct port of Rust smlang state machine.
    
    
    """
    
    # States
    idle = State("Idle", initial=True)
    heating = State("Heating") 
    cooling = State("Cooling")
    defrost = State("Defrost")
    
    # Transitions
    start_heating = idle.to(heating)
    start_cooling = idle.to(cooling)
    start_defrost = heating.to(defrost) | idle.to(defrost)
    stop_heating = heating.to(idle)
    stop_cooling = cooling.to(idle)
    end_defrost = defrost.to(idle)
    switch_to_cooling = heating.to(cooling)
    switch_to_heating = cooling.to(heating)
    
    def __init__(self, hvac_options: HvacOptions):
        self.state_data = HVACState(hvac_options)
        
        # Initialize separate strategies
        from .strategies.heating_strategy import HeatingStrategy
        from .strategies.cooling_strategy import CoolingStrategy
        
        self.heating_strategy = HeatingStrategy(hvac_options)
        self.cooling_strategy = CoolingStrategy(hvac_options)
        
        super().__init__()
        logger.info("HVAC state machine initialized", 
                   system_mode=hvac_options.system_mode,
                   initial_state=self.current_state.name,
                   strategies_enabled=True)

    def update_conditions(self, indoor_temp: float, outdoor_temp: float,
                         hour: int, is_weekday: bool) -> None:
        """Update conditions and trigger evaluation."""
        self.state_data.update_conditions(indoor_temp, outdoor_temp, hour, is_weekday)
        
        # Trigger state evaluation
        self.evaluate_conditions()

    def evaluate_conditions(self) -> Optional[HVACMode]:
        """
        Evaluate conditions using separate heating/cooling strategies.
        
        Enhanced version using separate state machines.
        """
        logger.info("🔍 HVAC State Machine: Starting condition evaluation", 
                   current_state=self.current_state.name,
                   indoor_temp=self.state_data.current_temp,
                   outdoor_temp=self.state_data.outdoor_temp,
                   hour=self.state_data.current_hour,
                   system_mode=self.state_data.hvac_options.system_mode.value)
        
        if not self._has_valid_conditions():
            logger.warning("❌ HVAC State Machine: Cannot evaluate - missing temperature data")
            return None
        
        # Check if system should be active
        if not self.state_data.should_be_active():
            if self.current_state != self.idle:
                logger.info("⏰ HVAC State Machine: Outside active hours, stopping HVAC",
                           current_hour=self.state_data.current_hour,
                           active_start=self.state_data.hvac_options.active_hours.start if self.state_data.hvac_options.active_hours else None,
                           active_end=self.state_data.hvac_options.active_hours.end if self.state_data.hvac_options.active_hours else None)
                self._transition_to_idle()
            else:
                logger.info("⏰ HVAC State Machine: Outside active hours, staying idle")
            return HVACMode.OFF
        
        # Create state change data for strategies
        state_change_data = StateChangeData(
            current_temp=self.state_data.current_temp or 20.0,
            weather_temp=self.state_data.outdoor_temp or 20.0,
            hour=self.state_data.current_hour or 12,
            is_weekday=self.state_data.is_weekday if self.state_data.is_weekday is not None else True
        )
        
        # Determine target mode based on system configuration
        target_mode = self._determine_target_mode()
        logger.info("🎯 HVAC State Machine: Target mode determined", 
                   target_mode=target_mode.value,
                   reasoning="based on system configuration and conditions")
        
        # Execute transition based on target mode using strategies
        result_mode = self._execute_mode_transition_with_strategies(target_mode, state_change_data)
        
        logger.info("✅ HVAC State Machine: Evaluation complete",
                   final_mode=result_mode.value,
                   new_state=self.current_state.name,
                   indoor_temp=self.state_data.current_temp,
                   outdoor_temp=self.state_data.outdoor_temp)
        
        return result_mode

    def _has_valid_conditions(self) -> bool:
        """Check if we have valid temperature and time data."""
        return (self.state_data.current_temp is not None and
                self.state_data.outdoor_temp is not None and
                self.state_data.current_hour is not None)

    def _determine_target_mode(self) -> SystemMode:
        """
        Determine target system mode based on conditions.
        
        
        """
        options = self.state_data.hvac_options
        indoor_temp = self.state_data.current_temp
        outdoor_temp = self.state_data.outdoor_temp
        
        logger.info("🧠 HVAC Mode Decision: Analyzing conditions",
                   system_mode=options.system_mode.value,
                   indoor_temp=indoor_temp,
                   outdoor_temp=outdoor_temp)
        
        # Manual modes
        if options.system_mode in [SystemMode.HEAT_ONLY, SystemMode.COOL_ONLY, SystemMode.OFF]:
            logger.info("🎮 HVAC Mode Decision: Manual mode selected",
                       mode=options.system_mode.value,
                       reason="configured as manual mode")
            return options.system_mode
        
        # Auto mode logic
        heating_thresholds = options.heating.temperature_thresholds
        cooling_thresholds = options.cooling.temperature_thresholds
        
        logger.info("🤖 HVAC Mode Decision: Auto mode analysis",
                   heating_thresholds=f"{heating_thresholds.indoor_min}-{heating_thresholds.indoor_max}°C indoor, {heating_thresholds.outdoor_min}-{heating_thresholds.outdoor_max}°C outdoor",
                   cooling_thresholds=f"{cooling_thresholds.indoor_min}-{cooling_thresholds.indoor_max}°C indoor, {cooling_thresholds.outdoor_min}-{cooling_thresholds.outdoor_max}°C outdoor")
        
        # Priority 1: Urgent need (very hot/cold)
        if indoor_temp and indoor_temp < heating_thresholds.indoor_min:
            if (outdoor_temp is not None and 
                heating_thresholds.outdoor_min <= outdoor_temp <= heating_thresholds.outdoor_max):
                logger.info("🔥 HVAC Mode Decision: URGENT HEATING needed",
                           indoor_temp=indoor_temp,
                           threshold=heating_thresholds.indoor_min,
                           outdoor_temp=outdoor_temp,
                           reason="indoor temperature below minimum heating threshold")
                return SystemMode.HEAT_ONLY
            else:
                logger.info("🚫 HVAC Mode Decision: Heating needed but outdoor conditions prevent it",
                           indoor_temp=indoor_temp,
                           outdoor_temp=outdoor_temp,
                           outdoor_range=f"{heating_thresholds.outdoor_min}-{heating_thresholds.outdoor_max}°C")
        
        if indoor_temp and indoor_temp > cooling_thresholds.indoor_max:
            if (outdoor_temp is not None and 
                cooling_thresholds.outdoor_min <= outdoor_temp <= cooling_thresholds.outdoor_max):
                logger.info("❄️ HVAC Mode Decision: URGENT COOLING needed",
                           indoor_temp=indoor_temp,
                           threshold=cooling_thresholds.indoor_max,
                           outdoor_temp=outdoor_temp,
                           reason="indoor temperature above maximum cooling threshold")
                return SystemMode.COOL_ONLY
            else:
                logger.info("🚫 HVAC Mode Decision: Cooling needed but outdoor conditions prevent it",
                           indoor_temp=indoor_temp,
                           outdoor_temp=outdoor_temp,
                           outdoor_range=f"{cooling_thresholds.outdoor_min}-{cooling_thresholds.outdoor_max}°C")
        
        # Priority 2: Outdoor temperature guidance
        heating_can_operate = (outdoor_temp is not None and 
                              heating_thresholds.outdoor_min <= outdoor_temp <= heating_thresholds.outdoor_max)
        cooling_can_operate = (outdoor_temp is not None and 
                              cooling_thresholds.outdoor_min <= outdoor_temp <= cooling_thresholds.outdoor_max)
        
        logger.info("🌡️ HVAC Mode Decision: System capability analysis",
                   heating_can_operate=heating_can_operate,
                   cooling_can_operate=cooling_can_operate,
                   outdoor_temp=outdoor_temp)
        
        if heating_can_operate and cooling_can_operate:
            # Both can operate - use outdoor temperature to decide
            mid_temp = (heating_thresholds.outdoor_max + cooling_thresholds.outdoor_min) / 2.0
            target = SystemMode.HEAT_ONLY if (outdoor_temp is not None and outdoor_temp <= mid_temp) else SystemMode.COOL_ONLY
            logger.info("⚖️ HVAC Mode Decision: Both systems available, choosing by outdoor temperature",
                        outdoor_temp=outdoor_temp,
                        mid_temp=mid_temp,
                        selected=target.value,
                        reason=f"outdoor temp {'<=' if (outdoor_temp is not None and outdoor_temp <= mid_temp) else '>'} midpoint")
            return target
        elif heating_can_operate:
            logger.info("🔥 HVAC Mode Decision: Only heating can operate",
                       outdoor_temp=outdoor_temp,
                       reason="outdoor temperature within heating range only")
            return SystemMode.HEAT_ONLY
        elif cooling_can_operate:
            logger.info("❄️ HVAC Mode Decision: Only cooling can operate",
                       outdoor_temp=outdoor_temp,
                       reason="outdoor temperature within cooling range only")
            return SystemMode.COOL_ONLY
        else:
            logger.info("🚫 HVAC Mode Decision: No system can operate",
                       outdoor_temp=outdoor_temp,
                       reason="outdoor temperature outside both heating and cooling ranges")
            return SystemMode.OFF

    def _execute_mode_transition_with_strategies(self, target_mode: SystemMode, 
                                               data: StateChangeData) -> HVACMode:
        """
        Execute state transition using separate heating/cooling strategies.
        
        
        """
        logger.info("🎯 HVAC Strategy Execution: Processing target mode",
                   target_mode=target_mode.value,
                   current_state=self.current_state.name)
        
        if target_mode == SystemMode.HEAT_ONLY:
            logger.info("🔥 HVAC Strategy: Executing heating strategy",
                       indoor_temp=data.current_temp,
                       outdoor_temp=data.weather_temp)
            
            # Use heating strategy to determine exact action
            strategy_result = self.heating_strategy.process_state_change(data)
            
            logger.info("🔥 HVAC Strategy: Heating strategy result",
                       strategy_result=strategy_result,
                       current_state=self.current_state.name)
            
            # Map strategy result to main state machine
            if strategy_result == "heating":
                if self.current_state == self.idle:
                    logger.info("🔥 HVAC Transition: Idle → Heating")
                    self.start_heating()  # type: ignore
                elif self.current_state == self.cooling:
                    logger.info("🔥 HVAC Transition: Cooling → Heating")
                    self.switch_to_heating()  # type: ignore
                return HVACMode.HEAT
                
            elif strategy_result == "defrosting":
                if self.current_state != self.defrost:
                    logger.info("🧊 HVAC Transition: Starting defrost cycle",
                               current_state=self.current_state.name)
                    self.start_defrost()  # type: ignore
                return HVACMode.OFF  # Defrost mode
                
            else:  # "off"
                logger.info("⏸️ HVAC Transition: Heating strategy says OFF")
                self._transition_to_idle()
                return HVACMode.OFF
                
        elif target_mode == SystemMode.COOL_ONLY:
            logger.info("❄️ HVAC Strategy: Executing cooling strategy",
                       indoor_temp=data.current_temp,
                       outdoor_temp=data.weather_temp)
            
            # Use cooling strategy to determine exact action
            strategy_result = self.cooling_strategy.process_state_change(data)
            
            logger.info("❄️ HVAC Strategy: Cooling strategy result",
                       strategy_result=strategy_result,
                       current_state=self.current_state.name)
            
            # Map strategy result to main state machine
            if strategy_result == "cooling":
                if self.current_state == self.idle:
                    logger.info("❄️ HVAC Transition: Idle → Cooling")
                    self.start_cooling()  # type: ignore
                elif self.current_state == self.heating:
                    logger.info("❄️ HVAC Transition: Heating → Cooling")
                    self.switch_to_cooling()  # type: ignore
                return HVACMode.COOL
                
            else:  # "cooling_off"
                logger.info("⏸️ HVAC Transition: Cooling strategy says OFF")
                self._transition_to_idle()
                return HVACMode.OFF
                
        else:  # SystemMode.OFF
            logger.info("⏸️ HVAC Strategy: Target mode is OFF, transitioning to idle",
                       current_state=self.current_state.name)
            self._transition_to_idle()
            return HVACMode.OFF

    def _execute_mode_transition(self, target_mode: SystemMode) -> HVACMode:
        """Legacy method - kept for backward compatibility."""
        current = self.current_state
        
        if target_mode == SystemMode.HEAT_ONLY:
            if current == self.idle:
                self.start_heating()  # type: ignore
            elif current == self.cooling:
                self.switch_to_heating()  # type: ignore
            return HVACMode.HEAT
            
        elif target_mode == SystemMode.COOL_ONLY:
            if current == self.idle:
                self.start_cooling()  # type: ignore
            elif current == self.heating:
                self.switch_to_cooling()  # type: ignore
            return HVACMode.COOL
            
        else:  # SystemMode.OFF
            self._transition_to_idle()
            return HVACMode.OFF

    def _transition_to_idle(self) -> None:
        """Transition to idle from any state."""
        if self.current_state == self.heating:
            logger.info("⏸️ HVAC Transition: Heating → Idle")
            self.stop_heating()  # type: ignore
        elif self.current_state == self.cooling:
            logger.info("⏸️ HVAC Transition: Cooling → Idle")
            self.stop_cooling()  # type: ignore
        elif self.current_state == self.defrost:
            logger.info("⏸️ HVAC Transition: Defrost → Idle")
            self.end_defrost()  # type: ignore
        elif self.current_state == self.idle:
            logger.debug("⏸️ HVAC Transition: Already idle, no transition needed")

    # State event handlers (."""
        temp = self.state_data.hvac_options.heating.temperature
        preset = self.state_data.hvac_options.heating.preset_mode
        logger.info("🔥 Entering heating mode", 
                   target_temp=temp,
                   preset_mode=preset,
                   indoor_temp=self.state_data.current_temp)

    def on_enter_cooling(self) -> None:
        """Handler for entering cooling state."""
        temp = self.state_data.hvac_options.cooling.temperature
        preset = self.state_data.hvac_options.cooling.preset_mode
        logger.info("❄️ Entering cooling mode",
                   target_temp=temp,
                   preset_mode=preset,
                   indoor_temp=self.state_data.current_temp)

    def on_enter_defrost(self) -> None:
        """Handler for entering defrost state."""
        defrost_config = self.state_data.hvac_options.heating.defrost
        logger.info("🧊 Starting defrost cycle",
                   duration_seconds=defrost_config.duration_seconds if defrost_config else 300,
                   outdoor_temp=self.state_data.outdoor_temp)

    def on_exit_defrost(self) -> None:
        """Handler for exiting defrost state."""
        self.state_data.defrost_needed = False
        logger.info("✅ Defrost cycle completed")

    def on_enter_idle(self) -> None:
        """Handler for entering idle state."""
        logger.info("⏸️ Entering idle mode",
                   indoor_temp=self.state_data.current_temp,
                   outdoor_temp=self.state_data.outdoor_temp)

    def get_current_hvac_mode(self) -> HVACMode:
        """Get the current HVAC mode based on state."""
        if self.current_state == self.heating:
            return HVACMode.HEAT
        elif self.current_state == self.cooling:
            return HVACMode.COOL
        else:
            return HVACMode.OFF

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status information."""
        return {
            "current_state": self.current_state.name,
            "hvac_mode": self.get_current_hvac_mode().value,
            "conditions": {
                "indoor_temp": self.state_data.current_temp,
                "outdoor_temp": self.state_data.outdoor_temp,
                "hour": self.state_data.current_hour,
                "is_weekday": self.state_data.is_weekday,
                "defrost_needed": self.state_data.defrost_needed,
                "should_be_active": self.state_data.should_be_active()
            },
            "configuration": {
                "system_mode": self.state_data.hvac_options.system_mode.value,
                "heating_target": self.state_data.hvac_options.heating.temperature,
                "cooling_target": self.state_data.hvac_options.cooling.temperature
            }
        }