from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str) -> str:
        pass

# Provider registry for future extension
PROVIDERS = {}


def register_provider(name: str, provider_cls):
    PROVIDERS[name] = provider_cls


def _ensure_builtin_providers_registered():
    # Lazy import avoids module side effects during startup and keeps registry centralized.
    if not PROVIDERS:
        from . import local_stub  # noqa: F401
        from . import ollama  # noqa: F401


def get_provider(name: str):
    _ensure_builtin_providers_registered()
    return PROVIDERS.get(name)
