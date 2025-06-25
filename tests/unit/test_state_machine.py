"""
Tests for HVAC state machine.

Comprehensive state machine testing with strategy integration.
"""

import pytest
from datetime import datetime
import structlog

from hag.config.settings import (
    HvacOptions, TemperatureThresholds, HeatingOptions, CoolingOptions, 
    HvacEntity, DefrostOptions, ActiveHours, SystemMode
)
from hag.hvac.state_machine import HVACStateMachine, StateChangeData, HVACMode

class TestHVACStateMachine:
    """Test HVAC state machine with integrated strategies."""
    
    @pytest.fixture
    def comprehensive_options(self):
        """Complete HVAC options for comprehensive testing."""
        return HvacOptions(
            temp_sensor="sensor.test_temperature",
            outdoor_sensor="sensor.test_outdoor_temperature",
            system_mode=SystemMode.AUTO,
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
    
    def test_state_machine_initialization(self, comprehensive_options):
        """Test state machine initialization with strategies."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Test initial state
        assert sm.current_state.name == "Idle"
        
        # Test strategies are initialized
        assert sm.heating_strategy is not None
        assert sm.cooling_strategy is not None
        
        # Test state data is initialized
        assert sm.state_data.hvac_options == comprehensive_options
        assert sm.state_data.current_temp is None
        assert sm.state_data.outdoor_temp is None
    
    def test_auto_mode_heating_scenario(self, comprehensive_options):
        """Test auto mode selecting heating."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Cold conditions that should trigger heating
        sm.update_conditions(
            indoor_temp=18.0,    # Below heating min (19.7)
            outdoor_temp=5.0,    # Within heating range (-10 to 15)
            hour=14,             # Active hours
            is_weekday=True
        )
        
        mode = sm.evaluate_conditions()
        assert mode == HVACMode.HEAT
        assert sm.current_state.name == "Heating"
    
    def test_auto_mode_cooling_scenario(self, comprehensive_options):
        """Test auto mode selecting cooling."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Hot conditions that should trigger cooling
        sm.update_conditions(
            indoor_temp=26.0,    # Above cooling max (25.0)
            outdoor_temp=30.0,   # Within cooling range (10 to 45)
            hour=14,             # Active hours
            is_weekday=True
        )
        
        mode = sm.evaluate_conditions()
        assert mode == HVACMode.COOL
        assert sm.current_state.name == "Cooling"
    
    def test_auto_mode_defrost_scenario(self, comprehensive_options):
        """Test auto mode triggering defrost cycle."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Very cold conditions that should trigger defrost
        sm.update_conditions(
            indoor_temp=18.0,     # Below heating min
            outdoor_temp=-5.0,    # Below defrost threshold (0.0)
            hour=14,              # Active hours
            is_weekday=True
        )
        
        mode = sm.evaluate_conditions()
        # Defrost mode shows as OFF but state should be Defrosting
        assert mode == HVACMode.OFF
        assert sm.current_state.name == "Defrost"
    
    def test_auto_mode_off_scenario(self, comprehensive_options):
        """Test auto mode staying off."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Comfortable conditions - should stay off
        sm.update_conditions(
            indoor_temp=22.0,    # Between heating max and cooling min
            outdoor_temp=20.0,   # Moderate outdoor temp
            hour=14,             # Active hours
            is_weekday=True
        )
        
        mode = sm.evaluate_conditions()
        assert mode == HVACMode.OFF
        assert sm.current_state.name == "Idle"
    
    def test_active_hours_restriction(self, comprehensive_options):
        """Test that system respects active hours."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Cold conditions but outside active hours
        sm.update_conditions(
            indoor_temp=18.0,    # Should trigger heating
            outdoor_temp=5.0,    # Good outdoor conditions
            hour=6,              # Before active hours (8-21)
            is_weekday=True
        )
        
        mode = sm.evaluate_conditions()
        assert mode == HVACMode.OFF
        assert sm.current_state.name == "Idle"
    
    def test_outdoor_temperature_limits(self, comprehensive_options):
        """Test outdoor temperature limits are respected."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Indoor needs heating but outdoor too cold
        sm.update_conditions(
            indoor_temp=18.0,     # Below heating min
            outdoor_temp=-15.0,   # Below heating outdoor min (-10)
            hour=14,              # Active hours
            is_weekday=True
        )
        
        mode = sm.evaluate_conditions()
        assert mode == HVACMode.OFF
        assert sm.current_state.name == "Idle"
        
        # Indoor needs cooling but outdoor too hot
        sm.update_conditions(
            indoor_temp=26.0,     # Above cooling max
            outdoor_temp=50.0,    # Above cooling outdoor max (45)
            hour=14,              # Active hours
            is_weekday=True
        )
        
        mode = sm.evaluate_conditions()
        assert mode == HVACMode.OFF
        assert sm.current_state.name == "Idle"
    
    def test_mode_transitions(self, comprehensive_options):
        """Test transitions between different modes."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Start with heating
        sm.update_conditions(18.0, 5.0, 14, True)
        mode = sm.evaluate_conditions()
        assert mode == HVACMode.HEAT
        assert sm.current_state.name == "Heating"
        
        # Switch to cooling
        sm.update_conditions(26.0, 30.0, 14, True)
        mode = sm.evaluate_conditions()
        assert mode == HVACMode.COOL
        assert sm.current_state.name == "Cooling"
        
        # Back to idle
        sm.update_conditions(22.0, 20.0, 14, True)
        mode = sm.evaluate_conditions()
        assert mode == HVACMode.OFF
        assert sm.current_state.name == "Idle"
    
    def test_system_mode_overrides(self, comprehensive_options):
        """Test manual system mode overrides."""
        
        # Test heat_only mode
        heat_only_options = comprehensive_options.model_copy()
        heat_only_options.system_mode = SystemMode.HEAT_ONLY
        
        sm = HVACStateMachine(heat_only_options)
        
        # Hot conditions but heat_only mode
        sm.update_conditions(26.0, 30.0, 14, True)
        target_mode = sm._determine_target_mode()
        assert target_mode == SystemMode.HEAT_ONLY
        
        # Test cool_only mode
        cool_only_options = comprehensive_options.model_copy()
        cool_only_options.system_mode = SystemMode.COOL_ONLY
        
        sm = HVACStateMachine(cool_only_options)
        
        # Cold conditions but cool_only mode
        sm.update_conditions(18.0, 5.0, 14, True)
        target_mode = sm._determine_target_mode()
        assert target_mode == SystemMode.COOL_ONLY
        
        # Test off mode
        off_options = comprehensive_options.model_copy()
        off_options.system_mode = SystemMode.OFF
        
        sm = HVACStateMachine(off_options)
        
        # Any conditions but off mode
        sm.update_conditions(18.0, 5.0, 14, True)
        target_mode = sm._determine_target_mode()
        assert target_mode == SystemMode.OFF
    
    def test_status_reporting(self, comprehensive_options):
        """Test comprehensive status reporting."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Set some conditions
        sm.update_conditions(20.0, 10.0, 15, True)
        
        status = sm.get_status()
        
        # Test status structure
        assert "current_state" in status
        assert "hvac_mode" in status
        assert "conditions" in status
        assert "configuration" in status
        
        # Test conditions
        conditions = status["conditions"]
        assert conditions["indoor_temp"] == 20.0
        assert conditions["outdoor_temp"] == 10.0
        assert conditions["hour"] == 15
        assert conditions["is_weekday"] == True
        assert "should_be_active" in conditions
        
        # Test configuration
        config = status["configuration"]
        assert config["system_mode"] == "auto"
        assert config["heating_target"] == 21.0
        assert config["cooling_target"] == 24.0
    
    def test_weekend_vs_weekday_hours(self, comprehensive_options):
        """Test different active hours for weekday vs weekend."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Weekend morning (7 AM) - should be active (start_weekday=7)
        sm.update_conditions(18.0, 5.0, 7, False)  # Weekend
        assert sm.state_data.should_be_active() == True
        
        # Weekday morning (7 AM) - should be inactive (start=8)
        sm.update_conditions(18.0, 5.0, 7, True)   # Weekday
        assert sm.state_data.should_be_active() == False
    
    def test_strategy_integration(self, comprehensive_options):
        """Test that main state machine properly integrates with strategies."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Test heating strategy integration
        heating_data = StateChangeData(
            current_temp=18.0,
            weather_temp=5.0,
            hour=14,
            is_weekday=True
        )
        
        # Process through heating strategy
        heating_result = sm.heating_strategy.process_state_change(heating_data)
        assert heating_result == "heating"
        
        # Test cooling strategy integration
        cooling_data = StateChangeData(
            current_temp=26.0,
            weather_temp=30.0,
            hour=14,
            is_weekday=True
        )
        
        # Process through cooling strategy
        cooling_result = sm.cooling_strategy.process_state_change(cooling_data)
        assert cooling_result == "cooling"
        
        # Test main state machine uses strategies correctly
        sm.update_conditions(18.0, 5.0, 14, True)
        mode = sm.evaluate_conditions()
        assert mode == HVACMode.HEAT

    def test_active_hours_boundary_conditions(self, comprehensive_options):
        """Test exact boundary hours for active time ranges."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Test exact start boundary (weekday start=8)
        sm.update_conditions(18.0, 5.0, 8, True)  # Exactly at start hour
        assert sm.state_data.should_be_active() == True
        
        # Test just before start (7 AM weekday)  
        sm.update_conditions(18.0, 5.0, 7, True)  # One hour before start
        assert sm.state_data.should_be_active() == False
        
        # Test exact end boundary (end=21)
        sm.update_conditions(18.0, 5.0, 21, True)  # Exactly at end hour
        assert sm.state_data.should_be_active() == True
        
        # Test just after end (22 PM)
        sm.update_conditions(18.0, 5.0, 22, True)  # One hour after end
        assert sm.state_data.should_be_active() == False
        
        # Test weekend boundaries (start_weekday=7)
        sm.update_conditions(18.0, 5.0, 7, False)  # Exactly at weekend start
        assert sm.state_data.should_be_active() == True
        
        sm.update_conditions(18.0, 5.0, 6, False)  # One hour before weekend start
        assert sm.state_data.should_be_active() == False
        
        # Test edge case: midnight boundaries (0 and 23 hours)
        sm.update_conditions(18.0, 5.0, 0, True)  # Midnight
        assert sm.state_data.should_be_active() == False  # Outside active hours
        
        sm.update_conditions(18.0, 5.0, 23, True)  # 11 PM
        assert sm.state_data.should_be_active() == False  # Outside active hours

    def test_rapid_temperature_changes(self, comprehensive_options):
        """Test system behavior under rapid temperature fluctuations."""
        
        sm = HVACStateMachine(comprehensive_options)
        
        # Start with cold conditions (should heat)
        sm.update_conditions(18.0, 5.0, 14, True)
        mode1 = sm.evaluate_conditions()
        assert mode1 == HVACMode.HEAT
        
        # Rapid change to hot conditions (should cool)
        sm.update_conditions(26.0, 30.0, 14, True)
        mode2 = sm.evaluate_conditions()
        assert mode2 == HVACMode.COOL
        
        # Rapid change back to cold (should heat again)
        sm.update_conditions(18.0, 5.0, 14, True)
        mode3 = sm.evaluate_conditions()
        assert mode3 == HVACMode.HEAT
        
        # Quick change to comfortable range (should be off)
        sm.update_conditions(22.0, 18.0, 14, True)
        mode4 = sm.evaluate_conditions()
        assert mode4 == HVACMode.OFF
        
        # Test state stability - multiple updates with same conditions
        for _ in range(5):
            sm.update_conditions(22.0, 18.0, 14, True)
            mode = sm.evaluate_conditions()
            assert mode == HVACMode.OFF  # Should remain stable
        
        # Test oscillating temperatures around heating thresholds
        # From config: indoor_min=19.7, indoor_max=20.2
        temps = [19.6, 20.3, 19.7, 19.6, 20.3]  # Around heating thresholds
        modes = []
        for temp in temps:
            sm.update_conditions(temp, 5.0, 14, True)
            modes.append(sm.evaluate_conditions())
        
        # Should show consistent behavior based on thresholds
        assert modes[0] == HVACMode.HEAT  # 19.6 < 19.7 min threshold
        assert modes[1] == HVACMode.OFF   # 20.3 > 20.2 max threshold  
        assert modes[2] == HVACMode.OFF   # 19.7 = min threshold, at boundary
        assert modes[3] == HVACMode.HEAT  # 19.6 < 19.7 min threshold
        assert modes[4] == HVACMode.OFF   # 20.3 > 20.2 max threshold