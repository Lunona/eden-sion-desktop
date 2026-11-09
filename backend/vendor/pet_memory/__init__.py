"""Standalone memory component. No desktop-pet or AstrBot integration is performed."""
from .core import MemoryService
from .types import MemoryError, Scope

__version__ = "0.1.0"
__all__ = ["MemoryService", "MemoryError", "Scope"]
