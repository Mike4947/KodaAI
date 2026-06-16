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
        think: bool = True,
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
        if think:
            payload["think"] = True
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

    content = message.get("content", "")
    if not content:
        return calls

    # Try parsing JSON tool call from content
    for candidate in [content, _extract_json_block(content)]:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                if "tool_calls" in parsed:
                    for tc in parsed["tool_calls"]:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            args = json.loads(args)
                        calls.append({"name": fn.get("name", ""), "arguments": args})
                    return calls
                if "name" in parsed and "arguments" in parsed:
                    args = parsed["arguments"]
                    if isinstance(args, str):
                        args = json.loads(args)
                    calls.append({"name": parsed["name"], "arguments": args})
                    return calls
        except json.JSONDecodeError:
            continue

    return calls


def _extract_json_block(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return None
