"""LLM provider abstraction.

All model calls in the app go through `get_provider().complete(...)`. Today this is
backed by the Anthropic API; swap `LLM_PROVIDER=bedrock` in .env to route the exact same
tool-use loop through AWS Bedrock with no other code changes.

The interface deliberately mirrors the Anthropic Messages shape (system prompt + a list
of messages + a list of tools), because Bedrock's Anthropic models accept the same schema.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import settings


@dataclass
class LLMResponse:
    """Normalized response: the raw content blocks plus why the model stopped."""
    content: list[dict[str, Any]]  # Anthropic-style content blocks
    stop_reason: str | None


class LLMProvider(Protocol):
    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...


class AnthropicProvider:
    """Backed by the Anthropic API (default for local development)."""

    def __init__(self) -> None:
        from anthropic import Anthropic

        if not settings.anthropic_api_key or settings.anthropic_api_key.startswith(
            "sk-ant-your-key"
        ):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy backend/.env.example to "
                "backend/.env and add your key."
            )
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools or [],
        )
        content = [block.model_dump() for block in resp.content]
        return LLMResponse(content=content, stop_reason=resp.stop_reason)


class BedrockProvider:
    """Backed by AWS Bedrock. Enable with LLM_PROVIDER=bedrock.

    Uses the Bedrock Runtime `invoke_model` API with the Anthropic messages schema so the
    surrounding agent loop is identical to the Anthropic path.
    """

    def __init__(self) -> None:
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self._model = settings.bedrock_model

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import json

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "tools": tools or [],
        }
        resp = self._client.invoke_model(
            modelId=self._model, body=json.dumps(body)
        )
        payload = json.loads(resp["body"].read())
        return LLMResponse(
            content=payload.get("content", []),
            stop_reason=payload.get("stop_reason"),
        )


class GeminiProvider:
    """Backed by the Google Gemini API. Enable with LLM_PROVIDER=gemini.

    Gemini uses a different wire format than Anthropic (contents/parts with
    functionCall/functionResponse instead of content blocks with tool_use/tool_result).
    Rather than change the agent loop, this provider translates:
      * Anthropic-style messages + tools  ->  Gemini request  (on the way in)
      * Gemini response                    ->  Anthropic-style content blocks (on the way out)
    so the rest of the app is provider-agnostic. Implemented over the REST API with httpx
    (the API key is sent in a header, never in the URL).
    """

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self) -> None:
        if not settings.google_api_key or settings.google_api_key.startswith(
            "your-google"
        ):
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Add your Gemini API key to backend/.env "
                "(GOOGLE_API_KEY=...) and set LLM_PROVIDER=gemini."
            )
        self._key = settings.google_api_key
        self._model = settings.gemini_model
        self._url = self.ENDPOINT.format(model=self._model)

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": _to_gemini_contents(messages),
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.4},
        }
        if tools:
            body["tools"] = [
                {"functionDeclarations": [_to_gemini_function(t) for t in tools]}
            ]
            body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}

        with httpx.Client(timeout=90) as client:
            resp = client.post(
                self._url, headers={"x-goog-api-key": self._key}, json=body
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Gemini API error {resp.status_code}: {resp.text[:400]}"
            )
        return _from_gemini_response(resp.json())


# ---- Gemini <-> Anthropic translation helpers ----

# JSON-Schema type -> Gemini (OpenAPI proto) type enum (uppercase).
_GEMINI_SCHEMA_KEYS = {"type", "properties", "items", "required", "enum", "description"}


def _convert_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a JSON Schema (Anthropic tool input_schema) to Gemini's schema subset."""
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, val in schema.items():
        if key not in _GEMINI_SCHEMA_KEYS:
            continue  # drop unsupported keywords ($schema, additionalProperties, default…)
        if key == "type" and isinstance(val, str):
            out["type"] = val.upper()
        elif key == "properties" and isinstance(val, dict):
            out["properties"] = {k: _convert_schema(v) for k, v in val.items()}
        elif key == "items":
            out["items"] = _convert_schema(val)
        else:
            out[key] = val
    return out


def _to_gemini_function(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "parameters": _convert_schema(tool.get("input_schema", {"type": "object"})),
    }


def _to_gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate Anthropic-style message history into Gemini `contents`."""
    import json

    contents: list[dict[str, Any]] = []
    id_to_name: dict[str, str] = {}

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role == "assistant":
            parts: list[dict[str, Any]] = []
            if isinstance(content, str):
                if content:
                    parts.append({"text": content})
            else:
                for block in content or []:
                    btype = block.get("type")
                    sig = block.get("thought_signature")
                    if btype == "text" and block.get("text"):
                        part: dict[str, Any] = {"text": block["text"]}
                        if sig:
                            part["thoughtSignature"] = sig
                        parts.append(part)
                    elif btype == "tool_use":
                        id_to_name[block.get("id", "")] = block.get("name", "tool")
                        part = {
                            "functionCall": {
                                "name": block.get("name"),
                                "args": block.get("input", {}) or {},
                            }
                        }
                        # Gemini 3 models require the thoughtSignature to be echoed back
                        # on the functionCall part, or the next turn is rejected (400).
                        if sig:
                            part["thoughtSignature"] = sig
                        parts.append(part)
            if parts:
                contents.append({"role": "model", "parts": parts})

        else:  # user (string) or tool results (list of tool_result blocks)
            if isinstance(content, str):
                contents.append({"role": "user", "parts": [{"text": content}]})
                continue
            parts = []
            for block in content or []:
                if block.get("type") == "tool_result":
                    name = id_to_name.get(block.get("tool_use_id", ""), "tool")
                    raw = block.get("content")
                    try:
                        parsed = json.loads(raw) if isinstance(raw, str) else raw
                    except (ValueError, TypeError):
                        parsed = {"result": raw}
                    if not isinstance(parsed, dict):
                        parsed = {"result": parsed}
                    parts.append({
                        "functionResponse": {"name": name, "response": parsed}
                    })
                elif block.get("type") == "text":
                    parts.append({"text": block.get("text", "")})
            if parts:
                contents.append({"role": "user", "parts": parts})

    return contents


def _from_gemini_response(data: dict[str, Any]) -> LLMResponse:
    """Translate a Gemini response into Anthropic-style content blocks."""
    import uuid

    candidates = data.get("candidates") or []
    if not candidates:
        feedback = data.get("promptFeedback")
        raise RuntimeError(
            f"Gemini returned no candidates (possibly blocked): {feedback or data}"
        )

    parts = (candidates[0].get("content") or {}).get("parts") or []
    blocks: list[dict[str, Any]] = []
    has_tool = False
    for part in parts:
        # Gemini 3 attaches a thoughtSignature to parts; we must carry it back on the
        # next turn (see _to_gemini_contents), so stash it on our block.
        sig = part.get("thoughtSignature")
        if part.get("text"):
            block = {"type": "text", "text": part["text"]}
            if sig:
                block["thought_signature"] = sig
            blocks.append(block)
        elif "functionCall" in part:
            has_tool = True
            fc = part["functionCall"]
            block = {
                "type": "tool_use",
                "id": "call_" + uuid.uuid4().hex[:16],
                "name": fc.get("name"),
                "input": fc.get("args", {}) or {},
            }
            if sig:
                block["thought_signature"] = sig
            blocks.append(block)

    if not blocks:
        # e.g. finishReason MAX_TOKENS with no content — return empty text so the loop ends.
        blocks.append({"type": "text", "text": ""})

    return LLMResponse(
        content=blocks, stop_reason="tool_use" if has_tool else "end_turn"
    )


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        if settings.llm_provider == "bedrock":
            _provider = BedrockProvider()
        elif settings.llm_provider == "gemini":
            _provider = GeminiProvider()
        else:
            _provider = AnthropicProvider()
    return _provider


def reset_provider() -> None:
    """Testing / config-reload helper."""
    global _provider
    _provider = None
