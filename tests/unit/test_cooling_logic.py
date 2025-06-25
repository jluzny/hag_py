"""
Tests for cooling logic.

rs with comprehensive scenarios.
"""

import pytest
import structlog

from hag.config.settings import (
    HvacOptions, HassOptions, TemperatureThresholds, 
    HeatingOptions, CoolingOptions, HvacEntity, ActiveHours, SystemMode
)
from hag.hvac.strategies.cooling_strategy import CoolingStrategy
from hag.hvac.state_machine import StateChangeData

class TestCoolingLogic:
    """Test cooling logic simulation .rs."""
    
    @pytest.fixture
    def cooling_options(self):
        """Mock cooling-focused HVAC options."""
        return HvacOptions(
            temp_sensor="sensor.test_temperature",
            outdoor_sensor="sensor.test_outdoor_temperature",
            system_mode=SystemMode.AUTO,  # Use auto for comprehensive testing
            hvac_entities=[
                HvacEntity(entity_id="climate.living_room_ac", enabled=True, defrost=True),
                HvacEntity(entity_id="climate.bedroom_ac", enabled=True, defrost=False)
            ],
            heating=HeatingOptions(
                temperature=21.0,
                preset_mode="comfort",
                temperature_thresholds=TemperatureThresholds(
                    indoor_min=19.7,
                    indoor_max=20.2,
                    outdoor_min=-10.0,
                    outdoor_max=15.0
                )
            ),
            cooling=CoolingOptions(
                temperature=24.0,
                preset_mode="windFree",
                temperature_thresholds=TemperatureThresholds(
                    indoor_min=23.5,
                    indoor_max=25.0,
                    outdoor_min=10.0,
                    outdoor_max=45.0
                )
            ),
            active_hours=ActiveHours(
                start=8,
                start_weekday=7,
                end=21
            )
        )
    
    def test_cooling_logic_simulation(self, cooling_options):
        """
        Test cooling decision logic with comprehensive scenarios.
        
        
        """
        
        strategy = CoolingStrategy(cooling_options)
        
        print(f"Testing cooling logic with sensor: {cooling_options.temp_sensor}")
        print(f"Cooling thresholds: min={cooling_options.cooling.temperature_thresholds.indoor_min}, "
              f"max={cooling_options.cooling.temperature_thresholds.indoor_max}, "
              f"outdoor_min={cooling_options.cooling.temperature_thresholds.outdoor_min}, "
              f"outdoor_max={cooling_options.cooling.temperature_thresholds.outdoor_max}")
        
        scenarios = [
            # (indoor_temp, outdoor_temp, hour, is_weekday, expected_should_cool, description)
            (26.0, 25.0, 14, True, True, "Hot day - should cool"),
            (23.0, 25.0, 14, True, False, "Cool enough - should not cool"),
            (26.0, 5.0, 14, True, False, "Hot indoor but cold outdoor - cannot cool"),
            (26.0, 50.0, 14, True, False, "Hot indoor but extreme outdoor - cannot cool"),
            (26.0, 25.0, 6, True, False, "Hot but too early - cannot cool"),
            (26.0, 25.0, 23, True, False, "Hot but too late - cannot cool"),
            (25.0, 25.0, 14, True, False, "At threshold - should not cool"),
            (25.1, 25.0, 14, True, True, "Just above threshold - should cool"),
        ]
        
        for (indoor, outdoor, hour, weekday, expected_should_cool, desc) in scenarios:
            data = StateChangeData(
                current_temp=indoor,
                weather_temp=outdoor,
                hour=hour,
                is_weekday=weekday
            )
            
            result_state = strategy.process_state_change(data)
            should_cool = result_state == "cooling"
            
            print(f"Scenario: {desc} - Indoor: {indoor}°C, Outdoor: {outdoor}°C, "
                  f"Hour: {hour}, Should cool: {should_cool}")
            
            assert should_cool == expected_should_cool, \
                f"Failed cooling decision for: {desc}"
    
    def test_auto_mode_simulation(self, cooling_options):
        """
        Test Auto mode decision logic.
        
        
        """
        
        # Verify we're in Auto mode
        assert cooling_options.system_mode == SystemMode.AUTO
        
        print("Simulating Auto mode decision logic")
        print(f"Heating range: {cooling_options.heating.temperature_thresholds.indoor_min:.1f}°C - "
              f"{cooling_options.heating.temperature_thresholds.indoor_max:.1f}°C "
              f"(outdoor: {cooling_options.heating.temperature_thresholds.outdoor_min:.1f}°C to "
              f"{cooling_options.heating.temperature_thresholds.outdoor_max:.1f}°C)")
        print(f"Cooling range: {cooling_options.cooling.temperature_thresholds.indoor_min:.1f}°C - "
              f"{cooling_options.cooling.temperature_thresholds.indoor_max:.1f}°C "
              f"(outdoor: {cooling_options.cooling.temperature_thresholds.outdoor_min:.1f}°C to "
              f"{cooling_options.cooling.temperature_thresholds.outdoor_max:.1f}°C)")
        
        seasonal_scenarios = [
            (18.0, 5.0, SystemMode.HEAT_ONLY, "Winter - cold indoor & outdoor -> should heat"),
            (26.0, 30.0, SystemMode.COOL_ONLY, "Summer - hot indoor & outdoor -> should cool"),
            (22.0, 18.0, SystemMode.OFF, "Spring - comfortable -> should be off"),
            (26.0, 5.0, SystemMode.OFF, "Hot indoor, cold outdoor -> cannot cool (outdoor too cold)"),
            (18.0, 30.0, SystemMode.OFF, "Cold indoor, hot outdoor -> comfortable (no heating or cooling needed)"),
            (28.0, 50.0, SystemMode.OFF, "Too hot to cool safely -> should be off"),
            (15.0, -15.0, SystemMode.OFF, "Too cold outdoor for heating -> should be off"),
        ]
        
        for (indoor, outdoor, expected_mode, description) in seasonal_scenarios:
            simulated_mode = simulate_auto_mode_decision(cooling_options, indoor, outdoor)
            
            print(f"Auto mode scenario: {description} (Indoor: {indoor:.1f}°C, "
                  f"Outdoor: {outdoor:.1f}°C) -> {simulated_mode}")
            
            assert simulated_mode == expected_mode, \
                f"Auto mode decision failed for: {description}"
    
    def test_hvac_entity_simulation(self, cooling_options):
        """
        Test HVAC entity behavior simulation.
        
        
        """
        
        strategy = CoolingStrategy(cooling_options)
        
        print(f"Simulating HVAC entity control for {len(cooling_options.hvac_entities)} entities")
        
        cooling_scenarios = [
            (27.0, 30.0, True, "Hot summer day"),
            (25.5, 25.0, True, "Warm day"),
            (23.0, 20.0, False, "Cool day - no cooling needed"),
        ]
        
        for (indoor_temp, outdoor_temp, should_cool, scenario) in cooling_scenarios:
            data = StateChangeData(
                current_temp=indoor_temp,
                weather_temp=outdoor_temp,
                hour=14,
                is_weekday=True
            )
            
            result_state = strategy.process_state_change(data)
            actual_should_cool = result_state == "cooling"
            
            print(f"\nScenario: {scenario} (Indoor: {indoor_temp:.1f}°C, "
                  f"Outdoor: {outdoor_temp:.1f}°C)")
            
            if actual_should_cool:
                print("  Cooling would be active - sending commands to entities:")
                for entity in cooling_options.hvac_entities:
                    if entity.enabled:
                        print(f"    {entity.entity_id} -> COOL mode, "
                              f"{cooling_options.cooling.temperature:.1f}°C, "
                              f"preset: {cooling_options.cooling.preset_mode}")
                        
                        # Simulate preset-specific behavior
                        if cooling_options.cooling.preset_mode == "quiet":
                            print("      Low fan speed for minimal noise")
                        elif cooling_options.cooling.preset_mode == "windFreeSleep":
                            print("      Gentle airflow for comfort")
                        else:
                            print("      Standard operation")
                    else:
                        print(f"    {entity.entity_id} -> DISABLED, skipping")
            else:
                print("  No cooling needed - entities would be OFF")
            
            assert actual_should_cool == should_cool, f"Cooling decision failed for: {scenario}"
        
        living_room = next((e for e in cooling_options.hvac_entities 
                           if e.entity_id == "climate.living_room_ac"), None)
        assert living_room is not None, "Living room AC should exist"
        assert living_room.entity_id == "climate.living_room_ac"
        assert living_room.enabled == True
        assert living_room.defrost == True
        
        bedroom = next((e for e in cooling_options.hvac_entities 
                       if e.entity_id == "climate.bedroom_ac"), None)
        assert bedroom is not None, "Bedroom AC should exist"
        assert bedroom.entity_id == "climate.bedroom_ac"
        assert bedroom.enabled == True
        assert bedroom.defrost == False
        
        # Test centralized cooling configuration
        assert cooling_options.cooling.temperature == 24.0
        assert cooling_options.cooling.preset_mode == "windFree"
    
    def test_active_hours_simulation(self, cooling_options):
        """
        Test active hours logic.
        
        
        """
        
        print("Simulating active hours logic")
        print(f"Weekday hours: {cooling_options.active_hours.start} - {cooling_options.active_hours.end}")
        print(f"Weekend hours: {cooling_options.active_hours.start_weekday} - {cooling_options.active_hours.end}")
        
        # Test all hours of the day for both weekday and weekend
        for hour in range(24):
            weekday_active = is_hour_active(cooling_options, hour, True)
            weekend_active = is_hour_active(cooling_options, hour, False)
            
            print(f"Hour {hour}: Weekday: {weekday_active}, Weekend: {weekend_active}")
        
        assert is_hour_active(cooling_options, 8, True) == True, "8 AM weekday should be active"
        assert is_hour_active(cooling_options, 21, True) == True, "9 PM weekday should be active"
        assert is_hour_active(cooling_options, 7, True) == False, "7 AM weekday should be inactive"
        assert is_hour_active(cooling_options, 22, True) == False, "10 PM weekday should be inactive"
        
        assert is_hour_active(cooling_options, 7, False) == True, "7 AM weekend should be active"
        assert is_hour_active(cooling_options, 21, False) == True, "9 PM weekend should be active"
        assert is_hour_active(cooling_options, 6, False) == False, "6 AM weekend should be inactive"
        assert is_hour_active(cooling_options, 22, False) == False, "10 PM weekend should be inactive"
    
    def test_cooling_state_transitions(self, cooling_options):
        """Test cooling state machine transitions."""
        
        strategy = CoolingStrategy(cooling_options)
        
        # Initial state should be CoolingOff
        assert strategy.current_state.name == "CoolingOff"
        
        # Hot conditions - should transition to cooling
        hot_data = StateChangeData(
            current_temp=26.0,
            weather_temp=30.0,
            hour=14,
            is_weekday=True
        )
        
        result = strategy.process_state_change(hot_data)
        assert result == "cooling"
        assert strategy.current_state.name == "Cooling"
        
        # Cool down - should transition back to off
        cool_data = StateChangeData(
            current_temp=22.0,
            weather_temp=30.0,
            hour=14,
            is_weekday=True
        )
        
        result = strategy.process_state_change(cool_data)
        assert result == "cooling_off"
        assert strategy.current_state.name == "CoolingOff"

# Helper functions

def simulate_cooling_decision(options: HvacOptions, indoor_temp: float, 
                            outdoor_temp: float, hour: int, is_weekday: bool) -> bool:
    """Simulate cooling decision ."""
    thresholds = options.cooling.temperature_thresholds
    
    # Check outdoor temperature bounds
    outdoor_ok = (thresholds.outdoor_min <= outdoor_temp <= thresholds.outdoor_max)
    
    # Check active hours
    hours_ok = is_hour_active(options, hour, is_weekday)
    
    # Check if temperature is too high (should start cooling)
    temp_too_high = indoor_temp > thresholds.indoor_max
    
    # Should cool if all conditions are met
    return outdoor_ok and hours_ok and temp_too_high

def simulate_auto_mode_decision(options: HvacOptions, indoor_temp: float, outdoor_temp: float) -> SystemMode:
    """Simulate auto mode decision ."""
    heating_thresholds = options.heating.temperature_thresholds
    cooling_thresholds = options.cooling.temperature_thresholds
    
    # Check heating conditions
    can_heat = (indoor_temp < heating_thresholds.indoor_min and
                heating_thresholds.outdoor_min <= outdoor_temp <= heating_thresholds.outdoor_max)
    
    # Check cooling conditions
    can_cool = (indoor_temp > cooling_thresholds.indoor_max and
                cooling_thresholds.outdoor_min <= outdoor_temp <= cooling_thresholds.outdoor_max)
    
    if can_heat and not can_cool:
        return SystemMode.HEAT_ONLY
    elif can_cool and not can_heat:
        return SystemMode.COOL_ONLY
    else:
        return SystemMode.OFF

def is_hour_active(options: HvacOptions, hour: int, is_weekday: bool) -> bool:
    """Check if hour is active ."""
    if not options.active_hours:
        return True
    
    start_hour = (options.active_hours.start if is_weekday 
                 else options.active_hours.start_weekday)
    
    return start_hour <= hour <= options.active_hours.end