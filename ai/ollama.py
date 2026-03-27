import asyncio
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .provider import AIProvider, register_provider


class OllamaProvider(AIProvider):
    def __init__(self, endpoint: str | None = None, model: str | None = None, timeout_seconds: int = 30):
        self.endpoint = (endpoint or os.getenv("AI_ENDPOINT") or "http://localhost:11434/v1").rstrip("/")
        self.model = model or os.getenv("AI_MODEL") or "qwen2.5-coder:7b"
        self.timeout_seconds = timeout_seconds

    async def complete(self, prompt: str) -> str:
        return await asyncio.to_thread(self._complete_sync, prompt)

    def _complete_sync(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }

        req = Request(
            url=f"{self.endpoint}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP error {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Ollama connection failed: {exc.reason}") from exc

        try:
            return parsed["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            raise RuntimeError("Unexpected Ollama response shape") from exc


register_provider("ollama", OllamaProvider)
