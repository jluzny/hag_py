"""
Tests for heating logic.

rs with comprehensive scenarios.
"""

import pytest
from datetime import datetime, timedelta
import structlog

from hag.config.settings import (
    HvacOptions, HassOptions, TemperatureThresholds, 
    HeatingOptions, CoolingOptions, HvacEntity, DefrostOptions, ActiveHours, SystemMode
)
from hag.hvac.strategies.heating_strategy import HeatingStrategy
from hag.hvac.state_machine import StateChangeData

class TestHeatingLogic:
    """Test heating logic simulation .rs."""
    
    @pytest.fixture
    def heating_options(self):
        """Mock heating-focused HVAC options."""
        return HvacOptions(
            temp_sensor="sensor.test_temperature",
            outdoor_sensor="sensor.test_outdoor_temperature",
            system_mode=SystemMode.HEAT_ONLY,
            hvac_entities=[
                HvacEntity(entity_id="climate.test_ac", enabled=True, defrost=True)
            ],
            heating=HeatingOptions(
                temperature=21.0,
                preset_mode="comfort",
                temperature_thresholds=TemperatureThresholds(
                    indoor_min=19.7,
                    indoor_max=20.2,
                    outdoor_min=-10.0,
                    outdoor_max=15.0
                ),
                defrost=DefrostOptions(
                    temperature_threshold=0.0,
                    period_seconds=3600,
                    duration_seconds=300
                )
            ),
            cooling=CoolingOptions(
                temperature=24.0,
                preset_mode="eco",
                temperature_thresholds=TemperatureThresholds(
                    indoor_min=23.0,
                    indoor_max=25.0,
                    outdoor_min=10.0,
                    outdoor_max=40.0
                )
            ),
            active_hours=ActiveHours(
                start=8,
                start_weekday=8,
                end=21
            )
        )
    
    def test_heating_logic_simulation(self, heating_options):
        """
        Test heating decision logic with comprehensive scenarios.
        
        
        """
        
        strategy = HeatingStrategy(heating_options)
        
        scenarios = [
            # (indoor_temp, outdoor_temp, hour, is_weekday, expected_should_heat, description)
            (18.0, 5.0, 14, True, True, "Cold day - should heat"),
            (21.0, 5.0, 14, True, False, "Warm enough - should not heat"),
            (18.0, 20.0, 14, True, False, "Cold indoor but warm outdoor - cannot heat"),
            (18.0, -15.0, 14, True, False, "Cold indoor but extreme outdoor - cannot heat"),
            (18.0, 5.0, 6, True, False, "Cold but too early - cannot heat"),
            (18.0, 5.0, 23, True, False, "Cold but too late - cannot heat"),
            (19.7, 5.0, 14, True, False, "At threshold - should not heat"),
            (19.6, 5.0, 14, True, True, "Just below threshold - should heat"),
        ]
        
        for (indoor, outdoor, hour, weekday, expected_should_heat, desc) in scenarios:
            data = StateChangeData(
                current_temp=indoor,
                weather_temp=outdoor,
                hour=hour,
                is_weekday=weekday
            )
            
            result_state = strategy.process_state_change(data)
            should_heat = result_state == "heating"
            
            print(f"Scenario: {desc} - Indoor: {indoor}°C, Outdoor: {outdoor}°C, "
                  f"Hour: {hour}, Should heat: {should_heat}")
            
            assert should_heat == expected_should_heat, \
                f"Failed heating decision for: {desc}"
    
    def test_heating_defrost_simulation(self, heating_options):
        """
        Test heating defrost cycle logic.
        
        
        """
        
        strategy = HeatingStrategy(heating_options)
        
        print(f"Defrost threshold: {heating_options.heating.defrost.temperature_threshold}°C, "
              f"period: {heating_options.heating.defrost.period_seconds}s, "
              f"duration: {heating_options.heating.defrost.duration_seconds}s")
        
        defrost_scenarios = [
            (5.0, False, "Above defrost threshold - no defrost needed"),
            (0.0, True, "At defrost threshold - defrost needed"),
            (-5.0, True, "Below defrost threshold - defrost needed"),
        ]
        
        for (outdoor_temp, expected_defrost, description) in defrost_scenarios:
            data = StateChangeData(
                current_temp=18.0,  # Cold enough to need heating
                weather_temp=outdoor_temp,
                hour=14,
                is_weekday=True
            )
            
            # Reset strategy state for clean test
            strategy.defrost_last = None
            strategy.defrost_current = None
            
            needs_defrost = strategy._need_defrost_cycle(data)
            
            print(f"Defrost scenario: {description} (Outdoor: {outdoor_temp:.1f}°C) -> "
                  f"Needs defrost: {needs_defrost}")
            
            assert needs_defrost == expected_defrost, \
                f"Defrost decision failed for: {description}"
    
    def test_heating_defrost_timing(self, heating_options):
        """Test defrost cycle timing logic."""
        
        strategy = HeatingStrategy(heating_options)
        
        # Test defrost period logic
        data = StateChangeData(
            current_temp=18.0,
            weather_temp=-5.0,  # Below threshold
            hour=14,
            is_weekday=True
        )
        
        # First time - should need defrost
        assert strategy._need_defrost_cycle(data) == True
        
        # Mark defrost as recently completed
        strategy.defrost_last = datetime.now() - timedelta(seconds=1800)  # 30 minutes ago
        
        # Should not need defrost yet (period is 3600 seconds)
        assert strategy._need_defrost_cycle(data) == False
        
        # Mark defrost as long ago
        strategy.defrost_last = datetime.now() - timedelta(seconds=3700)  # Over 1 hour ago
        
        # Should need defrost again
        assert strategy._need_defrost_cycle(data) == True
    
    def test_heating_defrost_completion(self, heating_options):
        """Test defrost cycle completion logic."""
        
        strategy = HeatingStrategy(heating_options)
        
        data = StateChangeData(
            current_temp=18.0,
            weather_temp=-5.0,
            hour=14,
            is_weekday=True
        )
        
        # No defrost running - should not be completed
        assert strategy._is_defrost_cycle_completed(data) == False
        
        # Start defrost cycle
        strategy.defrost_current = datetime.now() - timedelta(seconds=100)  # 100 seconds ago
        
        # Should not be completed yet (duration is 300 seconds)
        assert strategy._is_defrost_cycle_completed(data) == False
        
        # Mark defrost as running long enough
        strategy.defrost_current = datetime.now() - timedelta(seconds=350)  # Over 5 minutes
        
        # Should be completed now
        assert strategy._is_defrost_cycle_completed(data) == True
    
    def test_heating_entity_simulation(self, heating_options):
        """
        Test heating entity behavior simulation.
        
        
        """
        
        strategy = HeatingStrategy(heating_options)
        
        print(f"Simulating heating entity control for {len(heating_options.hvac_entities)} entities")
        
        heating_scenarios = [
            (17.0, 5.0, True, "Cold winter day"),
            (19.5, 10.0, True, "Cool day"),
            (21.0, 15.0, False, "Warm day - no heating needed"),
        ]
        
        for (indoor_temp, outdoor_temp, should_heat, scenario) in heating_scenarios:
            data = StateChangeData(
                current_temp=indoor_temp,
                weather_temp=outdoor_temp,
                hour=14,
                is_weekday=True
            )
            
            result_state = strategy.process_state_change(data)
            actual_should_heat = result_state == "heating"
            
            print(f"\nScenario: {scenario} (Indoor: {indoor_temp:.1f}°C, "
                  f"Outdoor: {outdoor_temp:.1f}°C)")
            
            if actual_should_heat:
                print("  Heating would be active - sending commands to entities:")
                for entity in heating_options.hvac_entities:
                    if entity.enabled:
                        print(f"    {entity.entity_id} -> HEAT mode, "
                              f"{heating_options.heating.temperature:.1f}°C, "
                              f"preset: {heating_options.heating.preset_mode}")
                        
                        # Simulate preset-specific behavior for heating
                        if heating_options.heating.preset_mode == "quiet":
                            print("      Low fan speed for minimal noise")
                        elif heating_options.heating.preset_mode == "windFreeSleep":
                            print("      Gentle airflow for comfort")
                        else:
                            print("      Standard operation")
                        
                        # Simulate defrost behavior if enabled
                        if entity.defrost:
                            print("      Defrost enabled - periodic defrost cycles")
                    else:
                        print(f"    {entity.entity_id} -> DISABLED, skipping")
            else:
                print("  No heating needed - entities would be OFF")
            
            assert actual_should_heat == should_heat, f"Heating decision failed for: {scenario}"
    
    def test_heating_state_transitions(self, heating_options):
        """Test heating state machine transitions."""
        
        strategy = HeatingStrategy(heating_options)
        
        # Initial state should be Off
        assert strategy.current_state.name == "Off"
        
        # Cold conditions - should transition to heating
        cold_data = StateChangeData(
            current_temp=18.0,
            weather_temp=5.0,
            hour=14,
            is_weekday=True
        )
        
        result = strategy.process_state_change(cold_data)
        assert result == "heating"
        assert strategy.current_state.name == "Heating"
        
        # Very cold outdoor - should transition to defrost
        defrost_data = StateChangeData(
            current_temp=18.0,
            weather_temp=-5.0,
            hour=14,
            is_weekday=True
        )
        
        result = strategy.process_state_change(defrost_data)
        assert result == "defrosting"
        assert strategy.current_state.name == "Defrost"
        
        # Warm up - defrost cycle should complete and transition to off
        # Need to simulate time passage for defrost to complete (300 seconds)
        import time
        time.sleep(0.1)  # Small delay to ensure time progression
        
        # Force defrost completion by setting defrost_current to an old time
        from datetime import datetime, timedelta
        strategy.defrost_current = datetime.now() - timedelta(seconds=301)
        
        warm_data = StateChangeData(
            current_temp=22.0,
            weather_temp=5.0,
            hour=14,
            is_weekday=True
        )
        
        result = strategy.process_state_change(warm_data)
        assert result == "off"
        assert strategy.current_state.name == "Off"

    def test_entity_specific_defrost_behavior(self):
        """Test that only entities with defrost=True participate in defrost cycles."""
        
        # Create options with mixed entity defrost settings
        mixed_defrost_options = HvacOptions(
            temp_sensor="sensor.test_temperature",
            outdoor_sensor="sensor.test_outdoor_temperature",
            system_mode=SystemMode.AUTO,
            hvac_entities=[
                HvacEntity(entity_id="climate.ac_with_defrost", enabled=True, defrost=True),
                HvacEntity(entity_id="climate.ac_no_defrost", enabled=True, defrost=False)
            ],
            heating=HeatingOptions(
                temperature=21.0,
                preset_mode="comfort",
                temperature_thresholds=TemperatureThresholds(
                    indoor_min=19.7,
                    indoor_max=20.2,
                    outdoor_min=-10.0,
                    outdoor_max=15.0
                ),
                defrost=DefrostOptions(
                    temperature_threshold=0.0,
                    period_seconds=3600,
                    duration_seconds=300
                )
            ),
            cooling=CoolingOptions(
                temperature=24.0,
                preset_mode="eco",
                temperature_thresholds=TemperatureThresholds(
                    indoor_min=23.0,
                    indoor_max=25.0,
                    outdoor_min=10.0,
                    outdoor_max=40.0
                )
            )
        )
        
        strategy = HeatingStrategy(mixed_defrost_options)
        
        # Test that entities are properly configured
        assert len(mixed_defrost_options.hvac_entities) == 2
        defrost_entities = [e for e in mixed_defrost_options.hvac_entities if e.defrost]
        no_defrost_entities = [e for e in mixed_defrost_options.hvac_entities if not e.defrost]
        
        assert len(defrost_entities) == 1
        assert len(no_defrost_entities) == 1
        assert defrost_entities[0].entity_id == "climate.ac_with_defrost"
        assert no_defrost_entities[0].entity_id == "climate.ac_no_defrost"
        
        # Test that defrost logic can still operate with mixed configuration
        cold_defrost_data = StateChangeData(
            current_temp=18.0,
            weather_temp=-5.0,  # Below defrost threshold
            hour=14,
            is_weekday=True
        )
        
        # Should still enter defrost mode when conditions are met
        strategy.start_heating()  # type: ignore  # Put into heating state first
        result = strategy.process_state_change(cold_defrost_data)
        assert result == "defrosting"
        assert strategy.current_state.name == "Defrost"

    def test_preset_mode_behaviors(self):
        """Test different preset modes and their behavioral impact."""
        
        preset_modes = ["comfort", "quiet", "windFreeSleep", "eco", "boost"]
        
        for preset_mode in preset_modes:
            # Create options with different preset modes
            preset_options = HvacOptions(
                temp_sensor="sensor.test_temperature", 
                outdoor_sensor="sensor.test_outdoor_temperature",
                system_mode=SystemMode.AUTO,
                hvac_entities=[
                    HvacEntity(entity_id="climate.test_ac", enabled=True, defrost=True)
                ],
                heating=HeatingOptions(
                    temperature=21.0,
                    preset_mode=preset_mode,
                    temperature_thresholds=TemperatureThresholds(
                        indoor_min=19.7,
                        indoor_max=20.2,
                        outdoor_min=-10.0,
                        outdoor_max=15.0
                    ),
                    defrost=DefrostOptions(
                        temperature_threshold=0.0,
                        period_seconds=3600,
                        duration_seconds=300
                    )
                ),
                cooling=CoolingOptions(
                    temperature=24.0,
                    preset_mode=preset_mode,
                    temperature_thresholds=TemperatureThresholds(
                        indoor_min=23.5,
                        indoor_max=25.0,
                        outdoor_min=10.0,
                        outdoor_max=45.0
                    )
                )
            )
            
            strategy = HeatingStrategy(preset_options)
            
            # Test that preset mode is properly stored
            assert strategy.hvac_options.heating.preset_mode == preset_mode
            
            # Test heating behavior with this preset mode
            cold_data = StateChangeData(
                current_temp=18.0,
                weather_temp=5.0,
                hour=14,
                is_weekday=True
            )
            
            result = strategy.process_state_change(cold_data)
            assert result == "heating"
            
            # Test that the HVAC mode mapping includes the preset
            hvac_mode = strategy.get_hvac_mode()
            assert hvac_mode == "heat"  # Should be heat regardless of preset
            
            # Test that status includes preset information
            status = strategy.get_status()
            assert "preset_mode" in status
            assert status["preset_mode"] == preset_mode

# Helper functions

def simulate_heating_decision(options: HvacOptions, indoor_temp: float, 
                            outdoor_temp: float, hour: int, is_weekday: bool) -> bool:
    """Simulate heating decision ."""
    thresholds = options.heating.temperature_thresholds
    
    # Check outdoor temperature bounds
    outdoor_ok = (thresholds.outdoor_min <= outdoor_temp <= thresholds.outdoor_max)
    
    # Check active hours
    hours_ok = is_hour_active(options, hour, is_weekday)
    
    # Check if temperature is too low (should start heating)
    temp_too_low = indoor_temp < thresholds.indoor_min
    
    # Should heat if all conditions are met
    return outdoor_ok and hours_ok and temp_too_low

def simulate_defrost_decision(options: HvacOptions, outdoor_temp: float) -> bool:
    """Simulate defrost decision ."""
    if not options.heating.defrost:
        return False
    return outdoor_temp <= options.heating.defrost.temperature_threshold

def is_hour_active(options: HvacOptions, hour: int, is_weekday: bool) -> bool:
    """Check if hour is active ."""
    if not options.active_hours:
        return True
    
    start_hour = (options.active_hours.start if is_weekday 
                 else options.active_hours.start_weekday)
    
    return start_hour <= hour <= options.active_hours.end