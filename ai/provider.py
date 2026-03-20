from abc import ABC, abstractmethod

class AIProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str) -> str:
        pass

# Provider registry for future extension
PROVIDERS = {}

def register_provider(name: str, provider_cls):
    PROVIDERS[name] = provider_cls

def get_provider(name: str):
    return PROVIDERS.get(name)
