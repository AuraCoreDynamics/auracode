"""Adapter discovery — scans auracode.adapters.* subpackages."""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from auracode.engine.registry import AdapterRegistry

logger = structlog.get_logger(__name__)


def discover_adapters(registry: AdapterRegistry) -> None:
    """Scan auracode.adapters.* subpackages and call register() on each.

    Each subpackage must expose a ``register(registry)`` callable.  Packages
    that fail to import or lack a ``register`` function are skipped with a
    warning so one broken adapter never prevents the rest from loading.
    """
    import auracode.adapters as adapters_pkg

    for module_info in pkgutil.iter_modules(
        adapters_pkg.__path__, prefix=adapters_pkg.__name__ + "."
    ):
        if not module_info.ispkg:
            # Only subpackages (directories with __init__.py) are adapters.
            continue

        module_name = module_info.name
        try:
            module = importlib.import_module(module_name)
        except Exception:
            logger.warning(
                "adapter_import_failed",
                module=module_name,
                exc_info=True,
            )
            continue

        register_fn = getattr(module, "register", None)
        if register_fn is None:
            logger.warning(
                "adapter_missing_register",
                module=module_name,
            )
            continue

        try:
            register_fn(registry)
            logger.info("adapter_registered", module=module_name)
        except Exception:
            logger.warning(
                "adapter_register_failed",
                module=module_name,
                exc_info=True,
            )
