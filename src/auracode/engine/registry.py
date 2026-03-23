"""Adapter and backend registries."""

from __future__ import annotations

from auracode.adapters.base import BaseAdapter
from auracode.routing.base import BaseRouterBackend


class AdapterRegistry:
    """Registry of available adapters, keyed by name."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseAdapter] = {}

    def register(self, adapter: BaseAdapter) -> None:
        """Register an adapter.  Overwrites if the name already exists."""
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> BaseAdapter | None:
        """Retrieve an adapter by name, or None."""
        return self._adapters.get(name)

    def list_adapters(self) -> list[str]:
        """Return the names of all registered adapters."""
        return list(self._adapters.keys())


class BackendRegistry:
    """Registry of router backends with a default selection."""

    def __init__(self) -> None:
        self._backends: dict[str, BaseRouterBackend] = {}
        self._default: str | None = None

    def register(self, name: str, backend: BaseRouterBackend, *, default: bool = False) -> None:
        """Register a backend.  Optionally mark it as the default."""
        self._backends[name] = backend
        if default or self._default is None:
            self._default = name

    def get(self, name: str) -> BaseRouterBackend | None:
        """Retrieve a backend by name, or None."""
        return self._backends.get(name)

    def get_default(self) -> BaseRouterBackend | None:
        """Return the default backend, or None if nothing is registered."""
        if self._default is None:
            return None
        return self._backends.get(self._default)

    def list_backends(self) -> list[str]:
        """Return the names of all registered backends."""
        return list(self._backends.keys())
