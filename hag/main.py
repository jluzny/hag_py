"""
Main application entry point for HAG Python.

rs with Python async/await and enhanced CLI.
"""

import asyncio
import logging
import sys
import signal
import os
from pathlib import Path
from typing import Optional
import structlog
from dependency_injector.wiring import inject, Provide

# Disable LangSmith telemetry by default for privacy
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGCHAIN_ENDPOINT", "")
os.environ.setdefault("LANGCHAIN_API_KEY", "")
os.environ.setdefault("LANGSMITH_TRACING", "false")

from hag.core.container import ApplicationContainer, create_container
from hag.core.exceptions import HAGError, ConfigurationError
from hag.hvac.controller import HVACController

# Configure colored logging immediately
from hag.core.logging import setup_colored_logging

setup_colored_logging("info")

logger = structlog.get_logger(__name__)


class HAGApplication:
    """
    Main HAG application class.


    """

    def __init__(
        self, config_file: Optional[str] = None, cli_log_level: Optional[int] = None
    ):
        self.config_file = config_file or self._find_config_file()
        self.cli_log_level = cli_log_level
        self.container: Optional[ApplicationContainer] = None
        self.hvac_controller: Optional[HVACController] = None
        self.shutdown_event = asyncio.Event()

    def _find_config_file(self) -> str:
        """Find configuration file using same logic as Rust version."""

        # Check environment variable
        import os

        config_from_env = os.getenv("HAG_CONFIG_FILE")
        if config_from_env and Path(config_from_env).exists():
            return config_from_env

        # Check standard locations
        possible_paths = [
            "config/hvac_config.yaml",
            "hvac_config.yaml",
            Path.home() / ".config" / "hag" / "hvac_config.yaml",
            "/etc/hag/hvac_config.yaml",
        ]

        for path in possible_paths:
            if Path(path).exists():
                return str(path)

        # Default path (may not exist)
        return "config/hvac_config.yaml"

    def _setup_logging(self) -> None:
        """Setup logging based on configuration."""

        # If CLI already set the log level, don't override
        if self.cli_log_level is not None:
            return

        # Get log level from config
        try:
            if self.container:
                settings = self.container.settings_from_file()
                config_log_level = settings.app_options.log_level
            else:
                config_log_level = logging.INFO

            # Setup colored logging with config level
            from hag.core.logging import setup_colored_logging

            setup_colored_logging(str(config_log_level))

            logger.info("Log level set from config", level=config_log_level)

        except Exception as e:
            logger.warning("Failed to set log level from config", error=str(e))

    async def setup(self) -> None:
        """Setup application dependencies."""

        logger.info("Setting up HAG application", config_file=self.config_file)

        try:
            # Verify config file exists
            if not Path(self.config_file).exists():
                raise ConfigurationError(
                    f"Configuration file not found: {self.config_file}"
                )

            # Create dependency injection container
            self.container = create_container(self.config_file)

            # Setup logging based on config (if not overridden by CLI)
            self._setup_logging()

            # Get HVAC controller from container
            self.hvac_controller = self.container.hvac_controller()

            logger.info("HAG application setup completed")

        except Exception as e:
            logger.error("Failed to setup HAG application", error=str(e))
            raise HAGError(f"Application setup failed: {e}")

    async def run(self) -> None:
        """
        Run the main application.


        """

        logger.info("🚀 Starting HAG HVAC automation system")

        try:
            # Setup signal handlers for graceful shutdown
            self._setup_signal_handlers()

            # Start HVAC controller
            if self.hvac_controller:
                await self.hvac_controller.start()

            logger.info("✅ HAG HVAC system is running.")
            logger.info("📊 Use Ctrl+C to stop the system gracefully")

            # Wait for shutdown signal
            await self.shutdown_event.wait()

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
        except Exception as e:
            logger.error("Application error", error=str(e))
            raise
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Graceful shutdown of the application."""

        logger.info("🛑 Shutting down HAG application")

        try:
            if self.hvac_controller:
                await self.hvac_controller.stop()

            logger.info("✅ HAG application stopped gracefully")

        except Exception as e:
            logger.error("Error during shutdown", error=str(e))

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info("Received shutdown signal", signal=signum)
            self.shutdown_event.set()

        # Handle SIGINT (Ctrl+C) and SIGTERM
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


# CLI Interface
async def main_async(
    config_file: Optional[str] = None, cli_log_level: Optional[int] = None
) -> None:
    """Async main function."""

    app = HAGApplication(config_file, cli_log_level)

    try:
        await app.setup()
        await app.run()
    except HAGError as e:
        logger.error("HAG application error", error=str(e))
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error", error=str(e))
        sys.exit(1)


def main() -> None:
    """
    Main entry point for the application.


    """

    import argparse

    parser = argparse.ArgumentParser(
        description="HAG - Home Assistant aGentic HVAC automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hag                                    # Run with default config
  hag --config custom_config.yaml       # Run with custom config
  hag --log-level debug                  # Run with debug logging
        """,
    )

    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to configuration file (default: auto-detect)",
    )

    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Set logging level (default: info)",
    )

    parser.add_argument(
        "--validate-config", action="store_true", help="Validate configuration and exit"
    )

    parser.add_argument("--version", action="version", version="HAG Python 0.1.0")

    args = parser.parse_args()

    # Setup logging level - prioritize config file, but allow CLI override
    import logging

    # If log level was explicitly provided via CLI, use it
    # Otherwise, we'll set it after loading config
    cli_log_level = None
    if args.log_level != "info":  # "info" is the default
        cli_log_level = getattr(logging, args.log_level.upper())
        from hag.core.logging import setup_colored_logging

        setup_colored_logging(args.log_level)

    # Handle config validation
    if args.validate_config:
        try:
            from hag.config.loader import ConfigLoader

            config_file = args.config or "config/hvac_config.yaml"
            settings = ConfigLoader.load_settings(config_file)

            print(f"✅ Configuration is valid: {config_file}")
            print(f"   Log level: {settings.app_options.log_level}")
            print(f"   AI enabled: {settings.app_options.use_ai}")
            print(f"   Temperature sensor: {settings.hvac_options.temp_sensor}")
            print(f"   System mode: {settings.hvac_options.system_mode}")
            print(f"   HVAC entities: {len(settings.hvac_options.hvac_entities)}")
            sys.exit(0)

        except Exception as e:
            print(f"❌ Configuration validation failed: {e}")
            sys.exit(1)

    # Show banner
    print("🏠 HAG - Home Assistant aGentic HVAC Automation")
    print("=" * 50)

    # Run the application
    try:
        asyncio.run(main_async(args.config, cli_log_level))
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)


# Additional CLI commands for debugging and management
@inject
async def status_command(
    hvac_controller: HVACController = Provide[ApplicationContainer.hvac_controller],
) -> None:
    """Get system status - debugging command."""

    try:
        status = await hvac_controller.get_status()

        print("\n📊 HAG System Status")
        print("=" * 30)
        print(f"Controller Running: {status['controller']['running']}")
        print(f"HA Connected: {status['controller']['ha_connected']}")
        print(f"Temperature Sensor: {status['controller']['temp_sensor']}")
        print(f"System Mode: {status['controller']['system_mode']}")

        if "state_machine" in status:
            sm_status = status["state_machine"]
            print(f"\nState Machine: {sm_status['current_state']}")
            print(f"HVAC Mode: {sm_status['hvac_mode']}")

            conditions = sm_status.get("conditions", {})
            if conditions.get("indoor_temp"):
                print(f"Indoor Temp: {conditions['indoor_temp']}°C")
            if conditions.get("outdoor_temp"):
                print(f"Outdoor Temp: {conditions['outdoor_temp']}°C")

        if status.get("ai_analysis"):
            print(f"\nAI Analysis:\n{status['ai_analysis']}")

    except Exception as e:
        print(f"❌ Failed to get status: {e}")


if __name__ == "__main__":
    main()
