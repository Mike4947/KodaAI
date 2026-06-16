import json
from typing import Any

import httpx

from backend.config import settings


class OllamaClient:
    def __init__(self, model: str):
        self.model = model
        self.base_url = settings.ollama_base_url.rstrip("/")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": settings.ollama_num_ctx,
                "temperature": 0.2,
            },
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()


def parse_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract tool calls from Ollama response message."""
    calls = []

    if "tool_calls" in message and message["tool_calls"]:
        for tc in message["tool_calls"]:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append({"name": fn.get("name", ""), "arguments": args})
        return calls

    # Some models return tool info in content as JSON
    content = message.get("content", "")
    if content and '"tool_calls"' in content:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "tool_calls" in parsed:
                for tc in parsed["tool_calls"]:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        args = json.loads(args)
                    calls.append({"name": fn.get("name", ""), "arguments": args})
        except json.JSONDecodeError:
            pass

    return calls
