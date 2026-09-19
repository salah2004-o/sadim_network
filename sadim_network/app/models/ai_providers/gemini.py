from __future__ import annotations

import base64
import json
import logging
import os
import random
import socket
import urllib.error
import urllib.request
from typing import Any

from .base import BaseProvider, ChatRequest, ChatResponse


logger = logging.getLogger(__name__)


def _http_json(
    url: str,
    payload: dict,
    headers: dict,
    timeout: int = 25,
) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")

        return json.loads(body)

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")

        raise RuntimeError(
            f"Gemini HTTP {exc.code}: {body[:3000]}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Gemini connection error: {exc.reason}"
        ) from exc

    except socket.timeout as exc:
        raise RuntimeError(
            f"Gemini request timed out after {timeout}s"
        ) from exc

    except TimeoutError as exc:
        raise RuntimeError(
            f"Gemini request timed out after {timeout}s"
        ) from exc

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Gemini returned invalid JSON: {exc}"
        ) from exc


class GeminiProvider(BaseProvider):
    name = "gemini"
    supports_vision = True
    supports_tools = True

    def __init__(self):
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.timeout = int(os.getenv("GEMINI_REQUEST_TIMEOUT", "25"))

    def _keys(self) -> list[str]:
        preferred = [
            value
            for key, value in sorted(os.environ.items())
            if key.startswith("GEMINI_API_KEY_") and value
        ]

        if preferred:
            return preferred

        return [
            os.environ[name]
            for name in ("API_KEY1", "API_KEY2")
            if os.environ.get(name)
        ]

    def is_configured(self) -> bool:
        return bool(self._keys())

    def _parts_from_message(
        self,
        message: dict,
        attachments: list | None = None,
    ) -> list[dict]:
        parts: list[dict] = []

        text = message.get("content") or message.get("text") or ""

        if text:
            parts.append({"text": text})

        for attachment in attachments or []:
            if not attachment.mime_type.startswith("image/"):
                continue

            parts.append({
                "inline_data": {
                    "mime_type": attachment.mime_type,
                    "data": base64.b64encode(
                        attachment.data
                    ).decode("ascii"),
                }
            })

        return parts or [{"text": ""}]

    def generate(self, request: ChatRequest) -> ChatResponse:
        keys = self._keys()

        if not keys:
            raise RuntimeError("Gemini API is not configured")

        contents = []

        for message in request.messages:
            role = message.get("role", "user")

            gemini_role = (
                "user"
                if role == "user"
                else "model"
            )

            if message.get("parts"):
                contents.append({
                    "role": gemini_role,
                    "parts": message["parts"],
                })
            else:
                attachments = (
                    request.attachments
                    if (
                        role == "user"
                        and message is request.messages[-1]
                    )
                    else []
                )

                contents.append({
                    "role": gemini_role,
                    "parts": self._parts_from_message(
                        message,
                        attachments,
                    ),
                })

        payload: dict[str, Any] = {
            "system_instruction": {
                "parts": [
                    {
                        "text": request.system_prompt
                    }
                ]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }

        if request.tools and self.supports_tools:
            payload["tools"] = request.tools

        errors = []

        for key_index, key in enumerate(
            random.sample(keys, len(keys)),
            start=1,
        ):
            url = (
                "https://generativelanguage.googleapis.com/"
                f"v1beta/models/{self.model}:generateContent"
                f"?key={key}"
            )

            try:
                logger.info(
                    "Gemini request started: model=%s key=%s/%s messages=%s tools=%s",
                    self.model,
                    key_index,
                    len(keys),
                    len(contents),
                    bool(request.tools),
                )

                raw = _http_json(
                    url,
                    payload,
                    {"Content-Type": "application/json"},
                    self.timeout,
                )

                candidates = raw.get("candidates") or []

                if not candidates:
                    raise RuntimeError(
                        "Gemini returned no candidates: "
                        + json.dumps(raw, ensure_ascii=False)[:3000]
                    )

                parts = (
                    candidates[0]
                    .get("content", {})
                    .get("parts", [])
                )

                text = "".join(
                    part.get("text", "")
                    for part in parts
                    if isinstance(part, dict)
                ).strip()

                tool_calls = [
                    part.get("functionCall")
                    for part in parts
                    if isinstance(part, dict)
                    and part.get("functionCall")
                ]

                usage = raw.get("usageMetadata", {})

                logger.info(
                    "Gemini request succeeded: model=%s text=%s tool_calls=%s",
                    self.model,
                    bool(text),
                    len(tool_calls),
                )

                return ChatResponse(
                    text=text,
                    model=self.model,
                    provider=self.name,
                    raw=raw,
                    input_tokens=usage.get(
                        "promptTokenCount",
                        0,
                    ),
                    output_tokens=usage.get(
                        "candidatesTokenCount",
                        0,
                    ),
                    tool_calls=tool_calls,
                )

            except Exception as exc:
                error_message = str(exc)

                errors.append(error_message)

                logger.exception(
                    "Gemini request failed: model=%s key=%s/%s error=%s",
                    self.model,
                    key_index,
                    len(keys),
                    error_message,
                )

        raise RuntimeError(
            "Gemini request failed: "
            + "; ".join(errors[-2:])
        )


class OpenAIProvider(BaseProvider):
    name = "openai"
    supports_vision = True
    supports_tools = False

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ).rstrip("/")
        self.timeout = int(
            os.getenv("OPENAI_REQUEST_TIMEOUT", "30")
        )

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, request: ChatRequest) -> ChatResponse:
        if not self.api_key:
            raise RuntimeError(
                "OpenAI API is not configured"
            )

        messages = [
            {
                "role": "system",
                "content": request.system_prompt,
            }
        ]

        for msg in request.messages:
            role = (
                "assistant"
                if msg.get("role") in ("assistant", "model")
                else "user"
            )

            content = (
                msg.get("content")
                or msg.get("text")
                or ""
            )

            if (
                role == "user"
                and request.attachments
                and msg is request.messages[-1]
            ):
                parts: list[dict] = [
                    {
                        "type": "text",
                        "text": content,
                    }
                ]

                for attachment in request.attachments:
                    if attachment.mime_type.startswith("image/"):
                        b64 = base64.b64encode(
                            attachment.data
                        ).decode("ascii")

                        parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{attachment.mime_type};"
                                    f"base64,{b64}"
                                )
                            },
                        })
                    else:
                        parts[0]["text"] += (
                            f"\n\n[ملف مرفق: "
                            f"{attachment.filename} — "
                            f"النوع {attachment.mime_type}]"
                        )

                messages.append({
                    "role": role,
                    "content": parts,
                })

            else:
                messages.append({
                    "role": role,
                    "content": content,
                })

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        raw = _http_json(
            f"{self.base_url}/chat/completions",
            payload,
            {
                "Content-Type": "application/json",
                "Authorization": (
                    f"Bearer {self.api_key}"
                ),
            },
            self.timeout,
        )

        choice = raw.get("choices", [{}])[0]

        text = (
            (choice.get("message") or {}).get("content")
            or ""
        )

        usage = raw.get("usage") or {}

        return ChatResponse(
            text=text.strip(),
            model=self.model,
            provider=self.name,
            raw=raw,
            input_tokens=usage.get(
                "prompt_tokens",
                0,
            ),
            output_tokens=usage.get(
                "completion_tokens",
                0,
            ),
        )


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    supports_vision = True
    supports_tools = False

    def __init__(self):
        self.api_key = os.getenv(
            "ANTHROPIC_API_KEY",
            "",
        )
        self.model = os.getenv(
            "ANTHROPIC_MODEL",
            "claude-3-5-haiku-latest",
        )
        self.timeout = int(
            os.getenv(
                "ANTHROPIC_REQUEST_TIMEOUT",
                "30",
            )
        )

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, request: ChatRequest) -> ChatResponse:
        if not self.api_key:
            raise RuntimeError(
                "Anthropic API is not configured"
            )

        messages = []

        for msg in request.messages:
            role = (
                "assistant"
                if msg.get("role") in ("assistant", "model")
                else "user"
            )

            content = (
                msg.get("content")
                or msg.get("text")
                or ""
            )

            if (
                role == "user"
                and request.attachments
                and msg is request.messages[-1]
            ):
                parts: list[dict] = [
                    {
                        "type": "text",
                        "text": content,
                    }
                ]

                for attachment in request.attachments:
                    if attachment.mime_type.startswith("image/"):
                        parts.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": attachment.mime_type,
                                "data": base64.b64encode(
                                    attachment.data
                                ).decode("ascii"),
                            },
                        })
                    else:
                        parts[0]["text"] += (
                            f"\n\n[ملف مرفق: "
                            f"{attachment.filename}]"
                        )

                messages.append({
                    "role": role,
                    "content": parts,
                })

            else:
                messages.append({
                    "role": role,
                    "content": content,
                })

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

        text = "".join(
            block.get("text", "")
            for block in blocks
            if block.get("type") == "text"
        ).strip()

        usage = raw.get("usage") or {}

        return ChatResponse(
            text=text,
            model=self.model,
            provider=self.name,
            raw=raw,
            input_tokens=usage.get(
                "input_tokens",
                0,
            ),
            output_tokens=usage.get(
                "output_tokens",
                0,
            ),
        )