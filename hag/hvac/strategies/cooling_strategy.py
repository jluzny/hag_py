"""
Cooling strategy implementation.

rs state machine.
"""

from statemachine import StateMachine, State
from typing import Dict, Any
import structlog

from ...config.settings import HvacOptions
from ..state_machine import StateChangeData

logger = structlog.get_logger(__name__)

class CoolingStrategy(StateMachine):
    """
    Cooling state machine.

    
    """

    # States
    cooling_off = State("CoolingOff", initial=True)
    cooling = State("Cooling")

    # Transitions
    start_cooling = cooling_off.to(cooling)
    stop_cooling = cooling.to(cooling_off)
    stay_cooling = cooling.to(cooling)
    stay_off = cooling_off.to(cooling_off)

    def __init__(self, hvac_options: HvacOptions):
        self.hvac_options = hvac_options
        super().__init__()

        logger.info(
            "Cooling strategy initialized",
            cooling_temp=hvac_options.cooling.temperature,
            preset_mode=hvac_options.cooling.preset_mode,
        )

    def process_state_change(self, data: StateChangeData) -> str:
        """
        Process state change and determine transition.

        
        """

        current = self.current_state.name

        # Port Rust transition conditions
        can_operate = self._can_operate(data)
        is_temp_too_low = self._is_temp_too_low(data)
        is_temp_too_high = self._is_temp_too_high(data)

        logger.debug(
            "Cooling strategy evaluation",
            current_state=current,
            can_operate=can_operate,
            is_temp_too_low=is_temp_too_low,
            is_temp_too_high=is_temp_too_high,
            indoor_temp=data.current_temp,
            outdoor_temp=data.weather_temp,
        )

        # Port Rust smlang transition logic exactly
        if current == "CoolingOff":
            if can_operate and is_temp_too_high:
                self.start_cooling()
                self._start_or_stay_cooling(data)
                return "cooling"
            else:
                self.stay_off()
                self._switch_or_stay_off(data)
                return "cooling_off"

        elif current == "Cooling":
            if not can_operate or is_temp_too_low:
                self.stop_cooling()
                self._switch_or_stay_off(data)
                return "cooling_off"
            else:
                self.stay_cooling()
                self._start_or_stay_cooling(data)
                return "cooling"

        return current.lower()

    def _can_operate(self, data: StateChangeData) -> bool:
        
        cooling_thresholds = self.hvac_options.cooling.temperature_thresholds

        # Check outdoor temperature bounds
        weather_ok = (
            cooling_thresholds.outdoor_min
            <= data.weather_temp
            <= cooling_thresholds.outdoor_max
        )

        # Check active hours
        if self.hvac_options.active_hours:
            start_hour = (
                self.hvac_options.active_hours.start_weekday
                if data.is_weekday
                else self.hvac_options.active_hours.start
            )
            end_hour = self.hvac_options.active_hours.end
            hours_ok = start_hour <= data.hour <= end_hour
        else:
            hours_ok = True

        return weather_ok and hours_ok

    def _is_temp_too_low(self, data: StateChangeData) -> bool:
        """
        Check if temperature is too low for cooling.

        Port from Rust: "too low" means below cooling minimum (stop cooling).
        """
        return (
            data.current_temp
            < self.hvac_options.cooling.temperature_thresholds.indoor_min
        )

    def _is_temp_too_high(self, data: StateChangeData) -> bool:
        """
        Check if temperature is too high for cooling.

        Port from Rust: "too high" means above cooling maximum (start cooling).
        """
        return (
            data.current_temp
            > self.hvac_options.cooling.temperature_thresholds.indoor_max
        )

    def _start_or_stay_cooling(self, data: StateChangeData) -> None:
        
        logger.info(
            "❄️ Starting/staying COOLING",
            indoor_temp=data.current_temp,
            outdoor_temp=data.weather_temp,
            hour=data.hour,
            target_temp=self.hvac_options.cooling.temperature,
        )

    def _switch_or_stay_off(self, data: StateChangeData) -> None:
        
        logger.info(
            "⏸️ Cooling switching/staying OFF",
            indoor_temp=data.current_temp,
            outdoor_temp=data.weather_temp,
        )

    def get_hvac_mode(self) -> str:
        """
        Get HVAC mode for current state.

        
        """
        state_map = {"CoolingOff": "off", "Cooling": "cool"}
        return state_map.get(self.current_state.name, "off")

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive cooling strategy status."""
        return {
            "strategy": "cooling",
            "current_state": self.current_state.name,
            "hvac_mode": self.get_hvac_mode(),
            "target_temperature": self.hvac_options.cooling.temperature,
            "preset_mode": self.hvac_options.cooling.preset_mode,
            "thresholds": {
                "indoor_min": self.hvac_options.cooling.temperature_thresholds.indoor_min,
                "indoor_max": self.hvac_options.cooling.temperature_thresholds.indoor_max,
                "outdoor_min": self.hvac_options.cooling.temperature_thresholds.outdoor_min,
                "outdoor_max": self.hvac_options.cooling.temperature_thresholds.outdoor_max,
            },
        }

