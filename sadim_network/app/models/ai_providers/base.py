from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ChatAttachment:
    """In-memory file attachment for multimodal providers."""

    filename: str
    mime_type: str
    data: bytes
    size: int = 0

    def __post_init__(self):
        if not self.size:
            self.size = len(self.data)


@dataclass
class ChatRequest:
    system_prompt: str
    messages: list[dict[str, Any]]
    tools: Optional[list[dict]] = None
    attachments: list[ChatAttachment] = field(default_factory=list)
    temperature: float = 0.25
    max_tokens: int = 800


@dataclass
class ChatResponse:
    text: str
    model: str
    provider: str
    raw: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[dict] = field(default_factory=list)


class BaseProvider:
    name = "base"
    supports_vision = False
    supports_tools = False

    def is_configured(self) -> bool:
        raise NotImplementedError

    def generate(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError
