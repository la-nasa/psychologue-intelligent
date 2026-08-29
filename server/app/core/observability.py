from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI

_CONFIGURED = False


def configure_tracing(settings: Settings) -> None:
    global _CONFIGURED
    if _CONFIGURED or not settings.otel_enabled or settings.env == "testing":
        return
    resource = Resource.create({"service.name": settings.otel_service_name, "deployment.environment": settings.env})  # pragma: no cover
    provider = TracerProvider(resource=resource)  # pragma: no cover
    provider.add_span_processor(  # pragma: no cover
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)  # pragma: no cover
    _CONFIGURED = True  # pragma: no cover


def instrument_app(app: FastAPI) -> None:  # pragma: no cover — exercé seulement avec un vrai collector
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,health/ready")
    RedisInstrumentor().instrument()


def get_tracer(name: str = "pi") -> trace.Tracer:  # pragma: no cover
    return trace.get_tracer(name)
