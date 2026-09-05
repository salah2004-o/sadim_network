from __future__ import annotations

import base64
import json
import os
import random
import socket
import urllib.error
import urllib.request
from typing import Any

from .base import BaseProvider, ChatRequest, ChatResponse


def _http_json(url: str, payload: dict, headers: dict, timeout: int = 25) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class GeminiProvider(BaseProvider):
    name = "gemini"
    supports_vision = True
    supports_tools = True

    def __init__(self):
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.timeout = int(os.getenv("GEMINI_REQUEST_TIMEOUT", "25"))

    def _keys(self) -> list[str]:
        preferred = [v for k, v in sorted(os.environ.items()) if k.startswith("GEMINI_API_KEY_") and v]
        if preferred:
            return preferred
        return [os.environ[n] for n in ("API_KEY1", "API_KEY2") if os.environ.get(n)]

    def is_configured(self) -> bool:
        return bool(self._keys())

    def _parts_from_message(self, message: dict, attachments: list | None = None) -> list[dict]:
        parts: list[dict] = []
        text = message.get("content") or message.get("text") or ""
        if text:
            parts.append({"text": text})
        for att in attachments or []:
            if not att.mime_type.startswith("image/"):
                continue
            parts.append({
                "inline_data": {
                    "mime_type": att.mime_type,
                    "data": base64.b64encode(att.data).decode("ascii"),
                }
            })
        return parts or [{"text": ""}]

    def generate(self, request: ChatRequest) -> ChatResponse:
        keys = self._keys()
        if not keys:
            raise RuntimeError("Gemini API is not configured")

        contents = []
        for msg in request.messages:
            role = msg.get("role", "user")
            gemini_role = "user" if role == "user" else "model"
            if msg.get("parts"):
                contents.append({"role": gemini_role, "parts": msg["parts"]})
            else:
                atts = request.attachments if role == "user" and msg is request.messages[-1] else []
                contents.append({"role": gemini_role, "parts": self._parts_from_message(msg, atts)})

        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": request.system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if request.tools and self.supports_tools:
            payload["tools"] = request.tools

        errors = []
        for key in random.sample(keys, len(keys)):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={key}"
            try:
                raw = _http_json(url, payload, {"Content-Type": "application/json"}, self.timeout)
                parts = raw.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                tool_calls = [p.get("functionCall") for p in parts if p.get("functionCall")]
                usage = raw.get("usageMetadata", {})
                return ChatResponse(
                    text=text,
                    model=self.model,
                    provider=self.name,
                    raw=raw,
                    input_tokens=usage.get("promptTokenCount", 0),
                    output_tokens=usage.get("candidatesTokenCount", 0),
                    tool_calls=tool_calls,
                )
            except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError) as exc:
                errors.append(str(exc))
        raise RuntimeError("Gemini request failed: " + "; ".join(errors[-2:]))


class OpenAIProvider(BaseProvider):
    name = "openai"
    supports_vision = True
    supports_tools = False

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.timeout = int(os.getenv("OPENAI_REQUEST_TIMEOUT", "30"))

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, request: ChatRequest) -> ChatResponse:
        if not self.api_key:
            raise RuntimeError("OpenAI API is not configured")

        messages = [{"role": "system", "content": request.system_prompt}]
        for msg in request.messages:
            role = "assistant" if msg.get("role") in ("assistant", "model") else "user"
            content = msg.get("content") or msg.get("text") or ""
            if role == "user" and request.attachments and msg is request.messages[-1]:
                parts: list[dict] = [{"type": "text", "text": content}]
                for att in request.attachments:
                    if att.mime_type.startswith("image/"):
                        b64 = base64.b64encode(att.data).decode("ascii")
                        parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{att.mime_type};base64,{b64}"},
                        })
                    else:
                        parts[0]["text"] += f"\n\n[ملف مرفق: {att.filename} — النوع {att.mime_type}]"
                messages.append({"role": role, "content": parts})
            else:
                messages.append({"role": role, "content": content})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        raw = _http_json(
            f"{self.base_url}/chat/completions",
            payload,
            {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            self.timeout,
        )
        choice = raw.get("choices", [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = raw.get("usage") or {}
        return ChatResponse(
            text=text.strip(),
            model=self.model,
            provider=self.name,
            raw=raw,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    supports_vision = True
    supports_tools = False

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
        self.timeout = int(os.getenv("ANTHROPIC_REQUEST_TIMEOUT", "30"))

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, request: ChatRequest) -> ChatResponse:
        if not self.api_key:
            raise RuntimeError("Anthropic API is not configured")

        messages = []
        for msg in request.messages:
            role = "assistant" if msg.get("role") in ("assistant", "model") else "user"
            content = msg.get("content") or msg.get("text") or ""
            if role == "user" and request.attachments and msg is request.messages[-1]:
                parts: list[dict] = [{"type": "text", "text": content}]
                for att in request.attachments:
                    if att.mime_type.startswith("image/"):
                        parts.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": att.mime_type,
                                "data": base64.b64encode(att.data).decode("ascii"),
                            },
                        })
                    else:
                        parts[0]["text"] += f"\n\n[ملف مرفق: {att.filename}]"
                messages.append({"role": role, "content": parts})
            else:
                messages.append({"role": role, "content": content})

        payload = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": request.system_prompt,
            "messages": messages,
        }
        raw = _http_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            self.timeout,
        )
        blocks = raw.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        usage = raw.get("usage") or {}
        return ChatResponse(
            text=text,
            model=self.model,
            provider=self.name,
            raw=raw,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
