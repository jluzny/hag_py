# HAG Python - Intelligent HVAC Automation

HAG (Home Assistant aGentic automation) Python is an intelligent HVAC automation system that integrates with Home Assistant to provide smart heating, cooling, and climate control using AI-powered decision making.

## Features

- **AI-Powered Decision Making**: Uses LangChain for intelligent HVAC control beyond simple rule-based logic
- **Home Assistant Integration**: Native WebSocket and REST API integration
- **State Machine Control**: Robust state management with transition validation
- **Extensible Architecture**: Plugin-based system for easy automation additions
- **Type Safety**: Full type hints and Pydantic validation
- **Async Performance**: Non-blocking I/O for responsive automation
- **Comprehensive Monitoring**: Structured logging and optional metrics

## Architecture

### Core Components

- **Configuration System**: Type-safe YAML configuration with environment overrides
- **Home Assistant Client**: WebSocket and REST API client for HA integration
- **HVAC State Machine**: State-based control logic with transition validation
- **LangChain Agent**: AI-powered decision making and optimization
- **Dependency Injection**: Clean separation of concerns and testability
- **Automation Registry**: Extensible plugin system for additional automations

### Project Structure

```
hag_py/
├── hag/                        # Main package
│   ├── core/                   # Core infrastructure
│   ├── config/                 # Configuration management
│   ├── home_assistant/         # HA integration
│   ├── hvac/                   # HVAC control logic
│   │   ├── tools/              # LangChain tools
│   │   └── strategies/         # HVAC strategies
│   ├── automations/            # Extensible automations
│   └── monitoring/             # Logging and metrics
├── config/                     # Configuration files
├── tests/                      # Test suite
└── scripts/                    # Utility scripts
```

## Quick Start

### Prerequisites

- Python 3.11+
- Home Assistant instance with WebSocket API enabled
- Home Assistant Long-Lived Access Token

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd hag_py
```

2. Install dependencies:
```bash
pip install poetry
poetry install
```

3. Configure the system:
```bash
cp config/hvac_config.yaml.example config/hvac_config.yaml
# Edit config/hvac_config.yaml with your settings
```

4. Set environment variables:
```bash
export HASS_TOKEN="your-home-assistant-token"
export HASS_WS_URL="ws://your-ha-instance:8123/api/websocket"
export HASS_REST_URL="http://your-ha-instance:8123"
```

5. Run the application:
```bash
poetry run hag
```

## Configuration

The system uses YAML configuration with environment variable overrides:

```yaml
hass_options:
  ws_url: "ws://homeassistant.local:8123/api/websocket"
  rest_url: "http://homeassistant.local:8123"
  token: "${HASS_TOKEN}"  # Overridden by environment variable
  max_retries: 5

hvac_options:
  temp_sensor: "sensor.indoor_temperature"
  system_mode: "auto"  # auto, heat_only, cool_only, off
  
  hvac_entities:
    - entity_id: "climate.hvac_system"
      enabled: true
      defrost: true

  heating:
    temperature: 21.0
    preset_mode: "comfort"
    temperature_thresholds:
      indoor_min: 19.7
      indoor_max: 20.2
      outdoor_min: -10.0
      outdoor_max: 15.0

  cooling:
    temperature: 24.0
    preset_mode: "eco"
    temperature_thresholds:
      indoor_min: 23.0
      indoor_max: 23.5
      outdoor_min: 10.0
      outdoor_max: 45.0
```

## Development

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=hag

# Run only unit tests
poetry run pytest -m unit

# Run only integration tests
poetry run pytest -m integration
```

### Code Quality

```bash
# Format code
poetry run black hag tests
poetry run isort hag tests

# Lint code
poetry run flake8 hag tests

# Type checking
poetry run mypy hag
```

### Adding New Automations

1. Create a new automation class in `hag/automations/`:

```python
from hag.automations.base import BaseAutomation

class MyAutomation(BaseAutomation):
    async def setup(self, ha_client, container):
        # Setup logic
        pass
    
    async def handle_event(self, event):
        # Event handling logic
        pass
```

2. Register in `config/hvac_config.yaml`:

```yaml
automations:
  - type: "my_automation"
    enabled: true
    config:
      # Automation-specific configuration
```

## Migration from Rust/Elixir

This Python implementation maintains functional parity with the original Rust HAG system while adding AI capabilities through LangChain integration. The core HVAC logic has been directly ported to ensure reliable operation.

## License

MIT License - see LICENSE file for details.