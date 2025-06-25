# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## IMPORTANT: Commit Message Guidelines

**NEVER mention Claude, AI, or automated assistance in commit messages.** 

- Remove all "🤖 Generated with [Claude Code]" footers
- Remove all "Co-Authored-By: Claude" lines  
- Write commit messages as if created by the human developer
- Focus on technical changes and improvements only
- Keep commit messages professional and direct

## Project Overview

HAG (Home Assistant aGentic automation) Python implementation is a complete port of the Rust HAG HVAC system to Python, using modern Python frameworks for AI-powered HVAC automation.

This is a **COMPLETE MIGRATION** from Rust with full functional parity including:
- All heating/cooling logic from Rust implementation
- Advanced defrost cycle management with timing constraints
- Separate heating/cooling state machines (direct ports)
- Comprehensive test coverage (all Rust tests ported)
- AI enhancement capabilities through LangChain

## Architecture

### Core Components
- **Configuration System**: Pydantic models for type-safe configuration (`hag/config/settings.py`)
- **Home Assistant Client**: WebSocket/REST client with reconnection logic (`hag/home_assistant/client.py`)
- **State Machine**: Main HVAC state machine using python-statemachine (`hag/hvac/state_machine.py`)
- **Strategy Pattern**: Separate heating/cooling strategies with individual state machines:
  - `hag/hvac/strategies/heating_strategy.py` - Direct port of Rust heating logic with defrost cycles
  - `hag/hvac/strategies/cooling_strategy.py` - Direct port of Rust cooling state machine
- **HVAC Controller**: Main controller orchestrating all components (`hag/hvac/controller.py`)
- **AI Agent**: LangChain-powered agent for intelligent decision making (`hag/hvac/agent.py`)
- **Dependency Injection**: Container-based DI system (`hag/core/container.py`)

### Key Features (Ported from Rust)

#### Heating Strategy (`heating_strategy.py`)
- **Defrost Cycle Management**: Implements advanced defrost logic with timing constraints:
  ```python
  def _need_defrost_cycle(self, data: StateChangeData) -> bool:
      if not self.hvac_options.heating.defrost:
          return False
      
      defrost_config = self.hvac_options.heating.defrost
      now = datetime.now()
      period = timedelta(seconds=defrost_config.period_seconds)
      temperature_threshold = defrost_config.temperature_threshold
      
      if data.weather_temp > temperature_threshold:
          return False
      
      if self.defrost_last and (now - self.defrost_last) < period:
          return False
      
      return True
  ```
- **State Machine**: Off -> Heating -> Defrosting -> Off transitions
- **Temperature Thresholds**: Indoor min/max and outdoor min/max validation
- **Active Hours**: Weekday/weekend scheduling support

#### Cooling Strategy (`cooling_strategy.py`)
- **State Machine**: CoolingOff -> Cooling -> CoolingOff transitions
- **Temperature Management**: Indoor threshold checking with outdoor bounds
- **Preset Modes**: Support for windFree, quiet, etc.

#### Main State Machine (`state_machine.py`)
- **Strategy Integration**: Uses separate heating/cooling strategies for decisions
- **Auto Mode Logic**: Intelligent mode selection based on conditions
- **State Transitions**: Idle -> Heating/Cooling/Defrost -> Idle
- **Comprehensive Status**: Full system status reporting

### Dependencies

```toml
[tool.poetry.dependencies]
python = "^3.11"
pydantic = "^2.0"
structlog = "^23.0"
dependency-injector = "^4.41"
python-statemachine = "^2.0"
langchain = "^0.1"
langchain-core = "^0.1"
httpx = "^0.25"
websockets = "^12.0"
pyyaml = "^6.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.0"
pytest-asyncio = "^0.21"
```

## Testing

### Test Structure (Complete Rust Port)
- **Unit Tests**:
  - `tests/unit/test_heating_logic.py` - All 8 Rust heating scenarios ported
  - `tests/unit/test_cooling_logic.py` - Complete cooling tests with auto mode simulation
  - `tests/unit/test_state_machine.py` - State machine integration tests
- **Integration Tests**:
  - `tests/integration/test_hvac_integration.py` - Port of Rust main_test.rs

### Key Test Scenarios (All Ported from Rust)

#### Heating Tests (8 scenarios)
```python
scenarios = [
    (18.0, 5.0, 14, True, True, "Cold day - should heat"),
    (21.0, 5.0, 14, True, False, "Warm enough - should not heat"),
    (18.0, 20.0, 14, True, False, "Cold indoor but warm outdoor - cannot heat"),
    (18.0, -15.0, 14, True, False, "Cold indoor but extreme outdoor - cannot heat"),
    (18.0, 5.0, 6, True, False, "Cold but too early - cannot heat"),
    (18.0, 5.0, 23, True, False, "Cold but too late - cannot heat"),
    (19.7, 5.0, 14, True, False, "At threshold - should not heat"),
    (19.6, 5.0, 14, True, True, "Just below threshold - should heat"),
]
```

#### Defrost Tests
- Temperature threshold validation (0.0°C threshold)
- Timing constraints (3600s period, 300s duration)
- State machine transitions with defrost cycles

#### Integration Tests
- Controller lifecycle management
- Temperature change event handling
- Manual override functionality
- Error handling and recovery
- Configuration validation

## Running Tests

```bash
# Install dependencies
pip install pytest pytest-asyncio pydantic structlog dependency-injector python-statemachine langchain langchain-core httpx websockets

# Run all tests
python -m pytest tests/ -v

# Run specific test categories  
python -m pytest tests/unit/ -v          # Unit tests
python -m pytest tests/integration/ -v   # Integration tests

# Run with coverage
python -m pytest tests/ -v --cov=hag
```

## Configuration

### Example Configuration (config/config.yaml)
```yaml
hass_options:
  ws_url: "ws://localhost:8123/api/websocket"
  rest_url: "http://localhost:8123"
  token: "your_token_here"
  max_retries: 3
  retry_delay_ms: 1000

hvac_options:
  temp_sensor: "sensor.indoor_temperature"
  outdoor_sensor: "sensor.outdoor_temperature"
  system_mode: "auto"  # auto, heat_only, cool_only, off
  
  hvac_entities:
    - entity_id: "climate.living_room_ac"
      enabled: true
      defrost: true
    - entity_id: "climate.bedroom_ac"  
      enabled: true
      defrost: false
      
  heating:
    temperature: 21.0
    preset_mode: "comfort"
    temperature_thresholds:
      indoor_min: 19.7
      indoor_max: 20.2
      outdoor_min: -10.0
      outdoor_max: 15.0
    defrost:
      temperature_threshold: 0.0
      period_seconds: 3600
      duration_seconds: 300
      
  cooling:
    temperature: 24.0
    preset_mode: "windFree"
    temperature_thresholds:
      indoor_min: 23.5
      indoor_max: 25.0
      outdoor_min: 10.0
      outdoor_max: 45.0
      
  active_hours:
    start: 8
    start_weekday: 7
    end: 21
```

## Usage

```python
from hag.core.container import ApplicationContainer
from hag.config.settings import load_config

# Load configuration
config = load_config("config/config.yaml")

# Initialize container
container = ApplicationContainer()
container.config.from_dict(config)

# Get controller
controller = container.hvac_controller()

# Start system
await controller.start()

# Manual operations
await controller.trigger_evaluation()
await controller.manual_override("heat", target_temperature=22.0)
status = await controller.get_status()

# Stop system
await controller.stop()
```

## Development Status

✅ **COMPLETED - Full Rust Migration**:
- All Rust logic ported with functional parity
- Separate heating/cooling state machines implemented
- Advanced defrost cycle management with timing
- Complete test coverage (all scenarios ported)
- AI enhancement through LangChain
- Dependency injection architecture
- Configuration system with validation

## Migration Notes

This Python implementation is a **complete functional port** of the Rust HAG system with the following enhancements:
- **AI Integration**: LangChain agents for intelligent decision making
- **Modern Python**: Uses latest Python patterns and frameworks
- **Type Safety**: Pydantic models for configuration validation
- **Testing**: Comprehensive test suite with all Rust scenarios
- **Modularity**: Clean separation of concerns for easy extension

All original Rust functionality has been preserved and enhanced, making this a drop-in replacement with AI capabilities.

## Important Commands

```bash
# Run tests and fix any issues
python -m pytest tests/ -v

# Install in development mode
pip install -e .

# Run main application
python -m hag

# Run with specific config
python -m hag --config config/config.yaml
```