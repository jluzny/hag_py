"""
Enhanced logging configuration with colored console output.
"""

import sys
import structlog
import logging
from colorama import init, Fore, Back, Style

# Initialize colorama for cross-platform colored output
init(autoreset=True)

class ColoredConsoleRenderer:
    """Simple colored console renderer using colorama."""
    
    def __call__(self, logger, name, event_dict):
        """Render log entry with colors."""
        
        # Extract event and level
        event = event_dict.pop("event", "")
        level = event_dict.pop("level", "info")
        logger_name = event_dict.pop("logger", name)
        timestamp = event_dict.pop("timestamp", "")
        
        # Parse timestamp for cleaner display
        if timestamp:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M:%S")
            except:
                time_str = timestamp[:8]  # Fallback
        else:
            time_str = ""
        
        # Color mapping
        level_colors = {
            "debug": Fore.CYAN,
            "info": Fore.BLUE,
            "warning": Fore.YELLOW,
            "error": Fore.RED
        }
        
        level_color = level_colors.get(level, Fore.WHITE)
        
        # Special colors for HVAC events
        if "🔥" in event or "heating" in event.lower():
            event_color = Fore.RED + Style.BRIGHT
        elif "❄️" in event or "cooling" in event.lower():
            event_color = Fore.CYAN + Style.BRIGHT
        elif "⏸️" in event or "off" in event.lower() or "idle" in event.lower():
            event_color = Fore.WHITE
        elif "🎯" in event or "decision" in event.lower():
            event_color = Fore.YELLOW + Style.BRIGHT
        elif "✅" in event or "execution" in event.lower():
            event_color = Fore.GREEN + Style.BRIGHT
        elif "🔍" in event or "state machine" in event.lower():
            event_color = Fore.MAGENTA + Style.BRIGHT
        elif "🚀" in event or "starting" in event.lower():
            event_color = Fore.GREEN + Style.BRIGHT
        elif "🛑" in event or "stopping" in event.lower():
            event_color = Fore.RED + Style.BRIGHT
        else:
            event_color = level_color
        
        # Build the log line
        parts = []
        
        # Timestamp
        if time_str:
            parts.append(f"{Fore.WHITE}{Style.DIM}[{time_str}]")
        
        # Level
        parts.append(f"{level_color}{level.upper():<5}")
        
        # Logger name (shortened)
        if logger_name:
            short_name = logger_name.split(".")[-1]
            parts.append(f"{Fore.WHITE}{Style.DIM}{short_name}:")
        
        # Event message
        parts.append(f"{event_color}{event}")
        
        # Additional context
        if event_dict:
            context_parts = []
            for key, value in event_dict.items():
                if key == "indoor_temp":
                    context_parts.append(f"{Fore.CYAN}🏠{value}°C")
                elif key == "outdoor_temp":
                    context_parts.append(f"{Fore.BLUE}🌤️{value}°C")
                elif key == "mode" or key == "target_mode":
                    context_parts.append(f"{Fore.MAGENTA}mode={value}")
                elif key == "entity_id":
                    # Shorten entity ID
                    short_entity = value.split(".")[-1] if "." in value else value
                    context_parts.append(f"{Fore.GREEN}entity={short_entity}")
                elif key in ["current_state", "new_state", "previous_state"]:
                    context_parts.append(f"{Fore.YELLOW}{key.replace('_', '')}={value}")
                elif isinstance(value, bool):
                    color = Fore.GREEN if value else Fore.RED
                    context_parts.append(f"{color}{key}={value}")
                elif isinstance(value, (int, float)) and key != "timestamp":
                    context_parts.append(f"{Fore.CYAN}{key}={value}")
                elif isinstance(value, str) and len(value) < 30:
                    context_parts.append(f"{key}={value}")
            
            if context_parts:
                context_str = f"{Fore.WHITE}{Style.DIM}({', '.join(context_parts)})"
                parts.append(context_str)
        
        # Print to console
        line = " ".join(parts) + Style.RESET_ALL
        print(line, file=sys.stderr)
        
        # Return empty string since we've already printed
        return ""

def setup_colored_logging(log_level: str = "info") -> None:
    """Setup colored logging configuration."""
    
    # Configure structlog with colored console output
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    # Always use colored console renderer (works in most terminals)
    processors.append(ColoredConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Set up standard library logging level
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO, 
        "warning": logging.WARNING,
        "error": logging.ERROR
    }
    
    logging.basicConfig(
        level=level_map.get(log_level.lower(), logging.INFO),
        force=True,
        handlers=[],  # Clear default handlers since we use structlog
    )