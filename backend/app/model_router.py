from __future__ import annotations

from .ai import LLMProvider
from .config import Settings
from .streaming import InProcessGGUFStreamingProvider, ModelRouter, OpenAICompatibleStreamingProvider, StreamingLLMProvider, TemplateStreamingProvider


def build_model_router(settings: Settings, fallback: LLMProvider) -> ModelRouter:
    template = TemplateStreamingProvider(tuple(getattr(fallback, "acknowledgments", ("Je vous écoute.",))))
    compatible = OpenAICompatibleStreamingProvider(settings.llm_base_url, settings.llm_api_key, settings.llm_timeout_seconds, settings.fast_model)
    in_process = InProcessGGUFStreamingProvider(settings.llm_model_path, template, settings.llm_max_reply_tokens, settings.llm_context_tokens)
    hybrid = StreamingLLMProvider({"openai-compatible": compatible, "in-process": in_process, "template": template}, settings.llm_backend_order)
    return ModelRouter(hybrid, settings.fast_model, settings.deep_model)
