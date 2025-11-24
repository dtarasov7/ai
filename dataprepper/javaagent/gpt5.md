Коротко: включите экспорт только трасс (OTLP), а метрики и логи отключите. Этого достаточно, чтобы в otelcol ушли только трейсы.

Вариант через JVM-параметры javaagent
- Подключение агента: -javaagent:/path/opentelemetry-javaagent.jar
- Экспорт только трасс: otlp
- Отключить метрики и логи: none
- При желании отключить сбор runtime-метрик и лог-мост, чтобы снизить оверхед

Пример:
```
-javaagent:/path/opentelemetry-javaagent.jar \
-Dotel.service.name=my-java-service \
-Dotel.traces.exporter=otlp \
-Dotel.metrics.exporter=none \
-Dotel.logs.exporter=none \
-Dotel.exporter.otlp.endpoint=http://otel-collector:4317 \
-Dotel.exporter.otlp.protocol=grpc \
-Dotel.instrumentation.runtime-metrics.enabled=false \
-Dotel.instrumentation.micrometer.enabled=false \
-Dotel.instrumentation.log-bridge.enabled=false \
-Dotel.instrumentation.log4j-appender.enabled=false \
-Dotel.instrumentation.logback-appender.enabled=false
```

Вариант через переменные окружения (например, Docker/Kubernetes)
```
OTEL_SERVICE_NAME=my-java-service
OTEL_TRACES_EXPORTER=otlp
OTEL_METRICS_EXPORTER=none
OTEL_LOGS_EXPORTER=none
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc

# Дополнительно (чтобы не собирать лишнее):
OTEL_INSTRUMENTATION_RUNTIME_METRICS_ENABLED=false
OTEL_INSTRUMENTATION_MICROMETER_ENABLED=false
OTEL_INSTRUMENTATION_LOG_BRIDGE_ENABLED=false
OTEL_INSTRUMENTATION_LOG4J_APPENDER_ENABLED=false
OTEL_INSTRUMENTATION_LOGBACK_APPENDER_ENABLED=false
```

Пояснения и советы
- Достаточно выставить OTEL_METRICS_EXPORTER=none и OTEL_LOGS_EXPORTER=none — метрики и логи не будут отправляться. Дополнительные флаги “instrumentation.*.enabled=false” отключают сам сбор/мосты, уменьшая накладные расходы.
- Для otelcol убедитесь, что включён OTLP gRPC receiver на порту 4317 (или используйте HTTP/protobuf 4318 и задайте protocol=http/protobuf).
- Корреляция логов с трейсам (через MDC) не мешает обычному логированию в файлы/stdout; просто данные не будут отправляться в OTel, если экспортер логов выключен.

Если покажете, как вы сейчас запускаете JVM/контейнер, помогу адаптировать параметры под ваш сценарий.
