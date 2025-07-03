# HAG Python - Intelligent HVAC Automation

HAG (Home Assistant aGentic automation) Python is an intelligent HVAC automation system that integrates with Home Assistant to provide smart heating, cooling, and climate control using AI-powered decision making.

This is an experimental alpha version migrating from Rust-based Hass HVAC automation to Python to evaluate the latest tools and frameworks in the ecosystem.

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

## Python Libraries Used

This section documents all Python libraries used in the HAG HVAC system with one-line descriptions of their purpose:

### **Standard Library**

- **`asyncio`** - Powers async/await patterns for non-blocking HVAC operations, WebSocket connections, and concurrent task management
- **`datetime`** - Handles timestamp generation, defrost cycle timing calculations, and time-based logic for HVAC operations  
- **`timedelta`** - Calculates time durations for defrost periods, operational intervals, and timing validations
- **`typing`** - Provides comprehensive type hints (Dict, List, Optional, etc.) for type safety across all modules
- **`enum`** - Defines SystemMode (auto/heat_only/cool_only/off) and HVACMode enums for type-safe configuration
- **`dataclasses`** - Creates structured data containers like StateChangeData for HVAC state transitions
- **`json`** - Serializes/deserializes WebSocket messages and API payloads for Home Assistant communication
- **`os`** - Accesses environment variables for configuration overrides and system path operations
- **`sys`** - Handles application exit codes and error termination in the main CLI interface
- **`signal`** - Implements graceful shutdown handling for SIGINT/SIGTERM signals in the HVAC controller
- **`argparse`** - Parses command-line arguments for configuration paths, log levels, and validation options
- **`logging`** - Sets basic Python logging levels from CLI arguments before structured logging takes over
- **`pathlib`** - Manages file paths for configuration loading and file existence checks
- **`urllib.parse`** - Joins URLs for Home Assistant REST API endpoint construction
- **`tempfile`** - Creates temporary files for isolated configuration testing

### **Configuration & Validation**

- **`pydantic`** - Validates HVAC configuration with type-safe models, custom validators, and automatic data conversion
- **`pydantic-settings`** - Loads environment-aware configuration with automatic environment variable integration
- **`pyyaml`** - Parses YAML configuration files for human-readable HVAC settings and thresholds

### **Logging & Monitoring**

- **`structlog`** - Provides structured JSON logging with context throughout all HVAC operations and AI decisions

### **Dependency Injection**

- **`dependency-injector`** - Manages IoC container for HVAC components with constructor injection and service lifecycle
- **`dependency-injector.wiring`** - Enables decorator-based dependency injection for clean separation of concerns

### **State Management**

- **`python-statemachine`** - Implements formal HVAC state machines for heating/cooling strategies with event-driven transitions

### **AI & LangChain Framework**

- **`langchain.agents`** - Creates AI agents for intelligent HVAC decision-making with tool-based execution
- **`langchain.tools`** - Builds custom HVAC tools (temperature monitoring, entity control) for AI agent use
- **`langchain_core.prompts`** - Manages AI conversation templates with HVAC-specific system prompts
- **`langchain_openai`** - Integrates OpenAI GPT models for intelligent HVAC analysis and decision support
- **`langchain-community`** - Provides additional LangChain tools and integrations for extended AI functionality
- **`langchain-text-splitters`** - Handles text processing for AI prompt management (dependency)
- **`langsmith`** - Provides LangChain observability and debugging for AI agent interactions

### **HTTP & WebSocket Communication**

- **`aiohttp`** - Handles async HTTP requests and WebSocket connections to Home Assistant API
- **`websockets`** - Provides WebSocket client support for real-time Home Assistant event streaming (dependency)
- **`httpx`** - Modern async HTTP client used by LangChain for OpenAI API calls (dependency)
- **`httpcore`** - HTTP protocol implementation used by httpx (dependency)
- **`requests`** - Traditional HTTP client used by some dependencies (dependency)
- **`urllib3`** - HTTP connection pooling used by requests (dependency)
- **`certifi`** - SSL certificate verification for HTTPS connections (dependency)

### **Data Processing**

- **`orjson`** - Fast JSON serialization/deserialization used by LangChain for API communication (dependency)
- **`dataclasses-json`** - JSON serialization for dataclass objects used by LangChain (dependency)
- **`marshmallow`** - Schema validation and serialization used by dataclasses-json (dependency)
- **`jsonpatch`** - JSON patch operations used by LangChain (dependency)
- **`jsonpointer`** - JSON pointer operations for data manipulation (dependency)

### **Testing Framework**

- **`pytest`** - Modern testing framework for comprehensive unit and integration test suites
- **`pytest-asyncio`** - Enables async test execution for testing HVAC async operations
- **`unittest.mock`** - Provides mocking capabilities for isolating HVAC components during testing

### **AI & ML Dependencies**

- **`openai`** - Official OpenAI API client for GPT model integration via LangChain
- **`tiktoken`** - Token counting and encoding for OpenAI models (dependency)
- **`tenacity`** - Retry logic for robust API calls to OpenAI and Home Assistant (dependency)
- **`numpy`** - Numerical operations used by LangChain for data processing (dependency)

### **Async & Network Support**

- **`anyio`** - Async compatibility layer used by various async libraries (dependency)
- **`sniffio`** - Async library detection for compatibility (dependency)
- **`aiohappyeyeballs`** - IPv4/IPv6 dual-stack connection handling for aiohttp (dependency)
- **`aiosignal`** - Signal support for async operations (dependency)
- **`multidict`** - Multi-value dictionary for HTTP headers (dependency)
- **`yarl`** - URL parsing and manipulation for HTTP operations (dependency)
- **`frozenlist`** - Immutable list implementation for thread-safe operations (dependency)

### **Data & Type Support**

- **`attrs`** - Advanced class definition with automatic method generation (dependency)
- **`annotated-types`** - Type annotation support for pydantic (dependency)
- **`pydantic-core`** - Fast validation core for pydantic (dependency)
- **`typing-extensions`** - Extended typing support for advanced type hints (dependency)
- **`typing-inspect`** - Runtime type inspection utilities (dependency)
- **`mypy-extensions`** - Type checking extensions for static analysis (dependency)

### **Utilities & Support**

- **`python-dotenv`** - Loads environment variables from .env files for configuration
- **`packaging`** - Version parsing and dependency management utilities (dependency)
- **`greenlet`** - Lightweight microthreads for async operations (dependency)
- **`zstandard`** - Fast compression used by LangChain for data transfer (dependency)
- **`regex`** - Advanced regular expression support for text processing (dependency)
- **`charset-normalizer`** - Character encoding detection for text processing (dependency)
- **`idna`** - International domain name support for URLs (dependency)
- **`h11`** - HTTP/1.1 protocol implementation (dependency)
- **`propcache`** - Property caching for performance optimization (dependency)
- **`tqdm`** - Progress bars for long-running operations (dependency)
- **`distro`** - Linux distribution detection (dependency)
- **`jiter`** - Fast JSON iterator for data processing (dependency)
- **`requests-toolbelt`** - Enhanced HTTP client utilities (dependency)

### **Architecture Summary**

The HAG system leverages a **modern, enterprise-grade Python stack** combining:
- **Async Programming** (asyncio, aiohttp) for responsive operations
- **AI Integration** (LangChain ecosystem) for intelligent decision making  
- **Formal State Machines** (python-statemachine) for reliable HVAC control
- **Dependency Injection** (dependency-injector) for clean architecture
- **Type Safety** (pydantic, typing) for robust validation
- **Comprehensive Testing** (pytest, pytest-asyncio) for reliability

This architecture ensures professional-grade HVAC automation with AI enhancement capabilities.

## License

MIT License - see LICENSE file for details.