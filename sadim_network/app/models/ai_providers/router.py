from __future__ import annotations

import os
from typing import Optional

from .base import BaseProvider, ChatRequest, ChatResponse
from .gemini import AnthropicProvider, GeminiProvider, OpenAIProvider


PROVIDER_REGISTRY = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}


def list_available_providers() -> list[dict]:
    result = []
    for name, cls in PROVIDER_REGISTRY.items():
        instance = cls()
        result.append({
            "id": name,
            "configured": instance.is_configured(),
            "supports_vision": instance.supports_vision,
            "model": getattr(instance, "model", ""),
        })
    return result


class ProviderRouter:
    """Try preferred provider, then fall back through configured providers."""

    def __init__(self, preferred: Optional[str] = None):
        order_env = os.getenv("SADEEM_AI_PROVIDER_ORDER", "gemini,openai,anthropic")
        self.order = [p.strip() for p in order_env.split(",") if p.strip() in PROVIDER_REGISTRY]
        preferred = (preferred or os.getenv("SADEEM_AI_PROVIDER", "")).strip().lower()
        if preferred in PROVIDER_REGISTRY:
            self.order = [preferred] + [p for p in self.order if p != preferred]

    def providers(self) -> list[BaseProvider]:
        instances = []
        for name in self.order:
            cls = PROVIDER_REGISTRY[name]
            inst = cls()
            if inst.is_configured():
                instances.append(inst)
        return instances

    def generate(self, request: ChatRequest, prefer_vision: bool = False) -> ChatResponse:
        providers = self.providers()
        if prefer_vision:
            providers = sorted(providers, key=lambda p: (0 if p.supports_vision else 1))
        if not providers:
            raise RuntimeError("No AI providers configured")

        errors = []
        for provider in providers:
            try:
                return provider.generate(request)
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError("All AI providers failed: " + "; ".join(errors[-3:]))
