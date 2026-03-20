from .provider import AIProvider, register_provider

class LocalStubProvider(AIProvider):
    async def complete(self, prompt: str) -> str:
        # TODO: Implement LAN-hosted model call
        return "[AI response placeholder]"

register_provider("local_stub", LocalStubProvider)
