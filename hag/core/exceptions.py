"""
Custom exceptions for HAG system.

"""

class HAGError(Exception):
    """Base exception for HAG system - port of Rust WhateverError."""

    def __init__(self, message: str, context: dict | None = None):
        self.message = message
        self.context = context or {}
        super().__init__(message)

    def __str__(self) -> str:
        if self.context:
            return f"{self.message} (context: {self.context})"
        return self.message

class ConfigurationError(HAGError):
    """Configuration-related errors."""

    pass

class ConnectionError(HAGError):
    """Home Assistant connection errors."""

    pass

class StateError(HAGError):
    """State machine or HVAC state errors."""

    pass

class ValidationError(HAGError):
    """Validation errors for user input or system state."""

    pass

