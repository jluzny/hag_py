"""
Dependency injection container for HAG system.

"""

from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject
import structlog

from hag.config.settings import Settings
from hag.config.loader import ConfigLoader
from hag.home_assistant.client import HomeAssistantClient
from hag.hvac.state_machine import HVACStateMachine
from hag.hvac.agent import HVACAgent

logger = structlog.get_logger(__name__)


class ApplicationContainer(containers.DeclarativeContainer):
    """
    Main dependency injection container for HAG application.


    """

    # Configuration
    config = providers.Configuration()

    # Core settings
    settings = providers.Singleton(Settings)

    # Settings from file
    settings_from_file = providers.Singleton(
        ConfigLoader.load_settings, config_file=config.config_file
    )

    # Home Assistant client
    ha_client = providers.Singleton(
        HomeAssistantClient, config=settings_from_file.provided.hass_options
    )

    # HVAC State Machine
    hvac_state_machine = providers.Singleton(
        HVACStateMachine, hvac_options=settings_from_file.provided.hvac_options
    )

    # HVAC Agent (AI-powered) - conditional creation
    hvac_agent = providers.Singleton(
        HVACAgent,
        ha_client=ha_client,
        hvac_options=settings_from_file.provided.hvac_options,
        state_machine=hvac_state_machine,
        llm_model=settings_from_file.provided.app_options.ai_model,
        temperature=settings_from_file.provided.app_options.ai_temperature,
    )

    # HVAC Controller (orchestrator) - AI configurable from settings
    hvac_controller = providers.Singleton(
        "hag.hvac.controller.HVACController",
        ha_client=ha_client,
        hvac_options=settings_from_file.provided.hvac_options,
        state_machine=hvac_state_machine,
        hvac_agent=hvac_agent,
        use_ai=settings_from_file.provided.app_options.use_ai,
    )


class ContainerBuilder:
    """
    Builder for setting up the application container.


    """

    def __init__(self):
        self.container = ApplicationContainer()
        self._config_file: str = "config/hvac_config.yaml"
        self._llm_model: str = "gpt-3.5-turbo"
        self._llm_temperature: float = 0.1

    def with_config_file(self, config_file: str) -> "ContainerBuilder":
        """Set configuration file path."""
        self._config_file = config_file
        return self

    def with_llm_model(self, model: str) -> "ContainerBuilder":
        """Set LLM model for AI agent."""
        self._llm_model = model
        return self

    def with_llm_temperature(self, temperature: float) -> "ContainerBuilder":
        """Set LLM temperature for AI agent."""
        self._llm_temperature = temperature
        return self

    def build(self) -> ApplicationContainer:
        """Build and configure the container."""

        logger.info(
            "Building application container",
            config_file=self._config_file,
            llm_model=self._llm_model,
            llm_temperature=self._llm_temperature,
        )

        # Configure the container
        self.container.config.from_dict(
            {
                "config_file": self._config_file,
                "llm_model": self._llm_model,
                "llm_temperature": self._llm_temperature,
            }
        )

        # Wire the container for dependency injection
        self.container.wire(
            modules=[
                "hag.hvac.controller",
                "hag.hvac.agent",
                "hag.main",
                "hag.core.container",
            ]
        )

        logger.info("Application container built successfully")
        return self.container


def create_container(config_file: str | None = None) -> ApplicationContainer:
    """
    Convenience function to create a configured container.
    """

    builder = ContainerBuilder()

    if config_file:
        builder.with_config_file(config_file)

    # Use default values (config file controls AI settings now)
    builder.with_llm_model("gpt-3.5-turbo").with_llm_temperature(0.1)

    return builder.build()


# Dependency injection decorators for use in other modules
def inject_ha_client():
    """Inject Home Assistant client."""
    return inject(Provide[ApplicationContainer.ha_client])


def inject_hvac_controller():
    """Inject HVAC controller."""
    return inject(Provide[ApplicationContainer.hvac_controller])


def inject_hvac_agent():
    """Inject HVAC agent."""
    return inject(Provide[ApplicationContainer.hvac_agent])


def inject_settings():
    """Inject application settings."""
    return inject(Provide[ApplicationContainer.settings_from_file])
