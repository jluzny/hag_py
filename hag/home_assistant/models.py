"""
Home Assistant data models.

Direct port of Home Assistant event structures from Rust implementation.
"""

from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

@dataclass
class HassState:
    """Home Assistant entity state ."""
    entity_id: str
    state: str
    attributes: Dict[str, Any]
    last_changed: datetime
    last_updated: datetime
    context: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HassState":
        """Create HassState from Home Assistant API response."""
        try:
            return cls(
                entity_id=data["entity_id"],
                state=data["state"],
                attributes=data.get("attributes", {}),
                last_changed=datetime.fromisoformat(data["last_changed"].replace("Z", "+00:00")),
                last_updated=datetime.fromisoformat(data["last_updated"].replace("Z", "+00:00")),
                context=data.get("context")
            )
        except (KeyError, ValueError) as e:
            logger.error("Failed to parse HassState", data=data, error=str(e))
            raise ValueError(f"Invalid HassState data: {e}")

    def get_numeric_state(self) -> Optional[float]:
        """Get state as numeric value if possible."""
        try:
            return float(self.state)
        except (ValueError, TypeError):
            logger.debug("State is not numeric", entity_id=self.entity_id, state=self.state)
            return None

@dataclass
class HassStateChangeData:
    """State change event data ."""
    entity_id: str
    new_state: Optional[HassState]
    old_state: Optional[HassState]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HassStateChangeData":
        """Create from Home Assistant state_changed event data."""
        try:
            new_state = None
            old_state = None
            
            if data.get("new_state"):
                new_state = HassState.from_dict(data["new_state"])
            
            if data.get("old_state"):
                old_state = HassState.from_dict(data["old_state"])
            
            return cls(
                entity_id=data["entity_id"],
                new_state=new_state,
                old_state=old_state
            )
        except (KeyError, ValueError) as e:
            logger.error("Failed to parse HassStateChangeData", data=data, error=str(e))
            raise ValueError(f"Invalid state change data: {e}")

@dataclass  
class HassEvent:
    """Home Assistant event ."""
    event_type: str
    data: Dict[str, Any]
    origin: str
    time_fired: datetime
    context: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HassEvent":
        """Create from Home Assistant WebSocket event message."""
        try:
            event_data = data.get("event", data)
            
            return cls(
                event_type=event_data["event_type"],
                data=event_data.get("data", {}),
                origin=event_data.get("origin", "LOCAL"),
                time_fired=datetime.fromisoformat(
                    event_data["time_fired"].replace("Z", "+00:00")
                ),
                context=event_data.get("context")
            )
        except (KeyError, ValueError) as e:
            logger.error("Failed to parse HassEvent", data=data, error=str(e))
            raise ValueError(f"Invalid HassEvent data: {e}")

    def is_state_changed(self) -> bool:
        """Check if this is a state_changed event."""
        return self.event_type == "state_changed"

    def get_state_change_data(self) -> Optional[HassStateChangeData]:
        """Get state change data if this is a state_changed event."""
        if not self.is_state_changed():
            return None
        
        try:
            return HassStateChangeData.from_dict(self.data)
        except ValueError:
            logger.warning("Failed to parse state change data", event=self)
            return None

@dataclass
class HassServiceCall:
    """Home Assistant service call data."""
    domain: str
    service: str
    service_data: Optional[Dict[str, Any]] = None
    target: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API call."""
        result: Dict[str, Any] = {
            "domain": self.domain,
            "service": self.service,
        }
        
        if self.service_data:
            result["service_data"] = self.service_data
            
        if self.target:
            result["target"] = self.target
            
        return result

@dataclass
class WebSocketMessage:
    """WebSocket message wrapper."""
    message_type: str
    message_id: Optional[int] = None
    success: Optional[bool] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    event: Optional[HassEvent] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebSocketMessage":
        """Create from WebSocket message data."""
        msg_type = data.get("type", "unknown")
        
        # Parse event if present
        event = None
        if msg_type == "event" and "event" in data:
            try:
                event = HassEvent.from_dict(data)
            except ValueError as e:
                logger.warning("Failed to parse event in WebSocket message", error=str(e))
        
        return cls(
            message_type=msg_type,
            message_id=data.get("id"),
            success=data.get("success"),
            result=data.get("result"),
            error=data.get("error"),
            event=event
        )