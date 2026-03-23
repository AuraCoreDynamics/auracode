"""AuraCode — Terminal-native, vendor-agnostic AI coding assistant."""

__version__ = "0.1.0"

from auracode.engine.core import AuraCodeEngine
from auracode.models.request import EngineRequest, EngineResponse, RequestIntent
from auracode.models.config import AuraCodeConfig
from auracode.app import create_application

__all__ = [
    "AuraCodeEngine",
    "EngineRequest",
    "EngineResponse",
    "RequestIntent",
    "AuraCodeConfig",
    "create_application",
]
