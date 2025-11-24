# pip install opentelemetry-sdk opentelemetry-exporter-otlp
# exporters:
#  logging:
#    logLevel: debug
#service:
#  pipelines:
#    traces:
#      exporters: [logging, otlp/data-prepper]
#
#sink:
#  - stdout:
#      condition: "true"
#


from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Настройка экспортера
exporter = OTLPSpanExporter(endpoint="localhost:4317", insecure=True)
span_processor = BatchSpanProcessor(exporter)
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(span_processor)
trace.set_tracer_provider(tracer_provider)

# Генерация трейса
tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("test-span") as span:
    span.set_attribute("test.key", "test-value")
    span.add_event("Test event")

print("Тестовый трейс отправлен!")
