"""
Simple colored logging using structlog's built-in ConsoleRenderer with custom timestamp colors.
"""

import structlog
import logging
from colorama import init, Fore, Style

# Initialize colorama for cross-platform colored output
init(autoreset=True)


class CustomColorProcessor:
    """Processor to add colored timestamp and level-based message coloring."""

    def __call__(self, logger, method_name, event_dict):
        """Add colored timestamp and color the main message based on log level."""

        # Color the timestamp
        timestamp = event_dict.pop("timestamp", "")
        if timestamp:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                # Create colored timestamp: dim cyan for date/time
                colored_time = f"{Fore.CYAN}{Style.DIM}[{dt.strftime('%H:%M:%S')}]{Style.RESET_ALL}"
                event_dict["timestamp"] = colored_time
            except:
                # Fallback to original timestamp with color
                event_dict["timestamp"] = (
                    f"{Fore.CYAN}{Style.DIM}{timestamp[:19]}{Style.RESET_ALL}"
                )

        # Color the main message based on log level
        level = event_dict.get("level", "info")
        event = event_dict.get("event", "")

        # Define colors for log levels
        level_colors = {
            "debug": Fore.CYAN,
            "info": Fore.BLUE,
            "warning": Fore.YELLOW,
            "error": Fore.RED,
            "critical": Fore.RED + Style.BRIGHT,
        }

        # # Special colors for HVAC events (override level colors)
        # if "🔥" in event or "heating" in event.lower():
        #     message_color = Fore.RED + Style.BRIGHT
        # elif "❄️" in event or "cooling" in event.lower():
        #     message_color = Fore.CYAN + Style.BRIGHT
        # elif "⏸️" in event or "off" in event.lower() or "idle" in event.lower():
        #     message_color = Fore.WHITE
        # elif "🎯" in event or "decision" in event.lower():
        #     message_color = Fore.YELLOW + Style.BRIGHT
        # elif "✅" in event or "execution" in event.lower():
        #     message_color = Fore.GREEN + Style.BRIGHT
        # elif "🔍" in event or "state machine" in event.lower():
        #     message_color = Fore.MAGENTA + Style.BRIGHT
        # elif "🚀" in event or "starting" in event.lower():
        #     message_color = Fore.GREEN + Style.BRIGHT
        # elif "🛑" in event or "stopping" in event.lower():
        #     message_color = Fore.RED + Style.BRIGHT
        # else:
        # Use level-based color
        message_color = level_colors.get(level, Fore.WHITE)

        # Apply color to the event message
        if event:
            event_dict["event"] = f"{message_color}{event}{Style.RESET_ALL}"

        # Add colored log level to display
        level_color = level_colors.get(level, Fore.WHITE)
        event_dict["level"] = f"{level_color}{level.upper():<7}{Style.RESET_ALL}"

        # Color structured context data (key=value pairs)
        context_color = Fore.GREEN + Style.DIM
        for key, value in event_dict.items():
            if key not in ["timestamp", "level", "event"] and not key.startswith("_"):
                # Color the key=value pairs in dim green
                if isinstance(value, str) and not value.startswith(
                    "\033"
                ):  # Don't re-color already colored values
                    event_dict[key] = f"{context_color}{value}{Style.RESET_ALL}"

        return event_dict


def setup_colored_logging(log_level: str = "info") -> None:
    """Setup colored logging with custom timestamp colors."""

    # Set up standard library logging level
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }

    # Configuration with custom timestamp and message coloring
    structlog.configure(
        processors=[
            # Add log level to event dict first
            structlog.stdlib.add_log_level,
            # Add timestamp
            structlog.processors.TimeStamper(fmt="iso"),
            # Color the timestamp, level, and main message
            CustomColorProcessor(),
            # Final processor for console output (colors already applied)
            structlog.dev.ConsoleRenderer(colors=False),  # Disable built-in coloring
        ],
        # Use WriteLoggerFactory for clean output
        logger_factory=structlog.WriteLoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging level
    logging.basicConfig(
        level=level_map.get(log_level.lower(), logging.INFO),
        force=True,
    )
