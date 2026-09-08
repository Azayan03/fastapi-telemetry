import logging
import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("telemetry")


def setup_telemetry(app: FastAPI, engine=None) -> TracerProvider | None:
    """
    Configures OpenTelemetry tracing for the FastAPI app and SQLAlchemy engine.
    Exports spans via OTLP gRPC to an OTel Collector or Jaeger instance.
    """
    if os.getenv("OTEL_SDK_DISABLED", "").lower() in ("true", "1"):
        logger.info("OpenTelemetry SDK is disabled via OTEL_SDK_DISABLED.")
        return None

    service_name = os.getenv("OTEL_SERVICE_NAME", "fastapi-telemetry")
    instance_id = os.getenv("HOSTNAME", "localhost")

    resource = Resource.create(
        attributes={
            "service.name": service_name,
            "service.instance.id": instance_id,
        }
    )

    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() in ("true", "1")
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
        span_processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(span_processor)
        logger.info("Configured OTLP gRPC span exporter to %s", otlp_endpoint)

    trace.set_tracer_provider(provider)

    # Instrument FastAPI application
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    # Instrument database queries via SQLAlchemy
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider)

    return provider
