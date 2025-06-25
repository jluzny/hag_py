"""
Heating strategy with defrost cycle management.

rs state machine.
"""

from statemachine import StateMachine, State
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import structlog

from ...config.settings import HvacOptions
from ..state_machine import StateChangeData

logger = structlog.get_logger(__name__)

class HeatingStrategy(StateMachine):
    """
    Heating state machine with defrost cycle.
    
    
    """
    
    # States
    off = State("Off", initial=True)
    heating = State("Heating")
    defrosting = State("Defrost")
    
    # Transitions
    start_heating = off.to(heating)
    start_defrost_from_off = off.to(defrosting)
    start_defrost_from_heating = heating.to(defrosting)
    stop_heating = heating.to(off)
    stop_defrost = defrosting.to(off)
    stay_heating = heating.to(heating)
    stay_off = off.to(off)
    stay_defrosting = defrosting.to(defrosting)
    
    def __init__(self, hvac_options: HvacOptions):
        self.hvac_options = hvac_options
        self.defrost_last: Optional[datetime] = None
        self.defrost_current: Optional[datetime] = None
        super().__init__()
        
        logger.info("Heating strategy initialized", 
                   heating_temp=hvac_options.heating.temperature,
                   defrost_enabled=hvac_options.heating.defrost is not None)

    def process_state_change(self, data: StateChangeData) -> str:
        """
        Process state change and determine transition.
        
        
        """
        
        current = self.current_state.name
        
        # Port Rust transition conditions
        can_operate = self._can_operate(data)
        is_temp_too_low = self._is_temp_too_low(data)
        is_temp_too_high = self._is_temp_too_high(data)
        need_defrost = self._need_defrost_cycle(data)
        is_defrost_complete = self._is_defrost_cycle_completed(data)
        
        logger.debug("Heating strategy evaluation",
                    current_state=current,
                    can_operate=can_operate,
                    is_temp_too_low=is_temp_too_low,
                    is_temp_too_high=is_temp_too_high,
                    need_defrost=need_defrost,
                    indoor_temp=data.current_temp,
                    outdoor_temp=data.weather_temp)
        
        # Port Rust smlang transition logic exactly
        if current == "Off":
            if can_operate and is_temp_too_low and need_defrost:
                self.start_defrost_from_off()
                self._start_defrost(data)
                return "defrosting"
            elif can_operate and is_temp_too_low:
                self.start_heating()
                self._start_or_stay_heating(data)
                return "heating"
            else:
                self.stay_off()
                self._switch_or_stay_off(data)
                return "off"
                
        elif current == "Heating":
            if can_operate and need_defrost:
                self.start_defrost_from_heating()
                self._start_defrost(data)
                return "defrosting"
            elif not can_operate or is_temp_too_high:
                self.stop_heating()
                self._switch_or_stay_off(data)
                return "off"
            else:
                self.stay_heating()
                self._start_or_stay_heating(data)
                return "heating"
                
        elif current == "Defrost":
            if is_defrost_complete:
                self.stop_defrost()
                self._stop_defrost(data)
                return "off"
            elif not can_operate:
                self.stop_defrost()
                self._switch_or_stay_off(data)
                return "off"
            else:
                self.stay_defrosting()
                self._continue_defrost(data)
                return "defrosting"
        
        return current.lower()

    def _can_operate(self, data: StateChangeData) -> bool:
        
        heating_thresholds = self.hvac_options.heating.temperature_thresholds
        
        # Check outdoor temperature bounds
        weather_ok = (heating_thresholds.outdoor_min <= data.weather_temp <= 
                     heating_thresholds.outdoor_max)
        
        # Check active hours
        if self.hvac_options.active_hours:
            start_hour = (self.hvac_options.active_hours.start_weekday if data.is_weekday 
                         else self.hvac_options.active_hours.start)
            end_hour = self.hvac_options.active_hours.end
            hours_ok = start_hour <= data.hour <= end_hour
        else:
            hours_ok = True
        
        return weather_ok and hours_ok

    def _is_temp_too_low(self, data: StateChangeData) -> bool:
        
        return data.current_temp < self.hvac_options.heating.temperature_thresholds.indoor_min

    def _is_temp_too_high(self, data: StateChangeData) -> bool:
        
        return data.current_temp > self.hvac_options.heating.temperature_thresholds.indoor_max

    def _need_defrost_cycle(self, data: StateChangeData) -> bool:
        """
        Check if defrost cycle is needed.
        
        
        """
        if not self.hvac_options.heating.defrost:
            return False
        
        defrost_config = self.hvac_options.heating.defrost
        now = datetime.now()
        period = timedelta(seconds=defrost_config.period_seconds)
        temperature_threshold = defrost_config.temperature_threshold
        
        # Port Rust logic exactly
        if data.weather_temp > temperature_threshold:
            return False
        
        if self.defrost_last and (now - self.defrost_last) < period:
            return False
        
        return True

    def _is_defrost_cycle_completed(self, data: StateChangeData) -> bool:
        """
        Check if defrost cycle is completed.
        
        
        """
        if not self.defrost_current:
            return False
        
        if not self.hvac_options.heating.defrost:
            return True
        
        now = datetime.now()
        duration = timedelta(seconds=self.hvac_options.heating.defrost.duration_seconds)
        
        return (now - self.defrost_current) >= duration

    def _start_or_stay_heating(self, data: StateChangeData) -> None:
        
        logger.info("🔥 Starting/staying HEATING",
                   indoor_temp=data.current_temp,
                   outdoor_temp=data.weather_temp,
                   hour=data.hour,
                   target_temp=self.hvac_options.heating.temperature)

    def _switch_or_stay_off(self, data: StateChangeData) -> None:
        
        logger.info("⏸️ Heating switching/staying OFF",
                   indoor_temp=data.current_temp,
                   outdoor_temp=data.weather_temp)

    def _start_defrost(self, data: StateChangeData) -> None:
        """
        Start defrost cycle.
        
        
        """
        logger.info("🧊 Starting DEFROST cycle",
                   indoor_temp=data.current_temp,
                   outdoor_temp=data.weather_temp,
                   threshold=self.hvac_options.heating.defrost.temperature_threshold if self.hvac_options.heating.defrost else 0)
        
        self.defrost_current = datetime.now()

    def _continue_defrost(self, data: StateChangeData) -> None:
        
        if self.defrost_current:
            elapsed = datetime.now() - self.defrost_current
            logger.debug("❄️ Continuing defrost cycle", 
                        elapsed_seconds=elapsed.total_seconds())

    def _stop_defrost(self, data: StateChangeData) -> None:
        """
        Stop defrost cycle.
        
        
        """
        logger.info("✅ Stopping DEFROST cycle")
        
        # Mark defrost as completed
        self.defrost_last = datetime.now()
        self.defrost_current = None
        
        # Transition to off
        self._switch_or_stay_off(data)

    def get_hvac_mode(self) -> str:
        """
        Get HVAC mode for current state.
        
        
        """
        state_map = {
            "Off": "off",
            "Heating": "heat",
            "Defrost": "cool"  # Defrost uses cool mode
        }
        return state_map.get(self.current_state.name, "off")

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive heating strategy status."""
        defrost_status = None
        if self.hvac_options.heating.defrost:
            defrost_status = {
                "enabled": True,
                "temperature_threshold": self.hvac_options.heating.defrost.temperature_threshold,
                "period_seconds": self.hvac_options.heating.defrost.period_seconds,
                "duration_seconds": self.hvac_options.heating.defrost.duration_seconds,
                "last_defrost": self.defrost_last.isoformat() if self.defrost_last else None,
                "current_defrost": self.defrost_current.isoformat() if self.defrost_current else None,
                "next_defrost_allowed": (
                    self.defrost_last + timedelta(seconds=self.hvac_options.heating.defrost.period_seconds)
                ).isoformat() if self.defrost_last else "now"
            }
        
        return {
            "strategy": "heating",
            "current_state": self.current_state.name,
            "hvac_mode": self.get_hvac_mode(),
            "target_temperature": self.hvac_options.heating.temperature,
            "preset_mode": self.hvac_options.heating.preset_mode,
            "thresholds": {
                "indoor_min": self.hvac_options.heating.temperature_thresholds.indoor_min,
                "indoor_max": self.hvac_options.heating.temperature_thresholds.indoor_max,
                "outdoor_min": self.hvac_options.heating.temperature_thresholds.outdoor_min,
                "outdoor_max": self.hvac_options.heating.temperature_thresholds.outdoor_max
            },
            "defrost": defrost_status
        }