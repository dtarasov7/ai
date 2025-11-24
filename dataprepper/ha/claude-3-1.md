**Да, именно так!** OpenTelemetry Collector с loadbalancing exporter может сам обеспечить маршрутизацию всех спанов с одним traceID на один и тот же Data Prepper. При этом **peer_forwarder в Data Prepper становится не нужен**.

## Как это работает

### Механизм консистентного хеширования

```
Спан с traceID: abc123 → hash(abc123) → всегда Data Prepper #2
Спан с traceID: def456 → hash(def456) → всегда Data Prepper #1
Спан с traceID: abc123 → hash(abc123) → снова Data Prepper #2 ✓
```

Loadbalancing exporter использует консистентное хеширование (consistent hashing) по traceID, что гарантирует:
- Все спаны одного трейса **всегда** попадают на одну и ту же ноду Data Prepper
- Service-map строится корректно, так как вся информация о трейсе обрабатывается в одном месте
- При добавлении/удалении нод минимальное перераспределение трейсов

## Полная конфигурация для этого сценария

### OpenTelemetry Collector

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  
  batch:
    timeout: 10s
    send_batch_size: 8192
    send_batch_max_size: 10000

exporters:
  loadbalancing/dataprepper:
    # КЛЮЧЕВАЯ настройка - маршрутизация по traceID!
    routing_key: traceID
    
    protocol:
      otlp:
        tls:
          insecure: true
        # Настройки для надежности
        sending_queue:
          enabled: true
          num_consumers: 10
          queue_size: 1000
        retry_on_failure:
          enabled: true
          initial_interval: 5s
          max_interval: 30s
          max_elapsed_time: 300s
    
    resolver:
      static:
        hostnames:
          - dp-node1.example.com:21890
          - dp-node2.example.com:21890
          - dp-node3.example.com:21890

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [loadbalancing/dataprepper]
```

### Data Prepper (упрощенная конфигурация БЕЗ peer_forwarder)

`data-prepper-config.yaml`:
```yaml
# Peer forwarder НЕ нужен!
# peer_forwarder - закомментирован или удален

serverPort: 4900
health_check_service: true

# Метрики для мониторинга
metrics_registries:
  - prometheus:
      port: 4901
```

`pipelines.yaml`:
```yaml
entry-pipeline:
  source:
    otel_trace_source:
      address: 0.0.0.0:21890
      ssl: false
  
  buffer:
    bounded_blocking:
      buffer_size: 25600
      batch_size: 400
  
  # НЕТ trace_peer_forwarder процессора!
  sink:
    - pipeline:
        name: raw-trace-pipeline
    - pipeline:
        name: service-map-pipeline

raw-trace-pipeline:
  source:
    pipeline:
      name: entry-pipeline
  
  processor:
    - otel_traces:
    - otel_trace_group:
        hosts: ["opensearch-1.example.com:9200", "opensearch-2.example.com:9200"]
  
  sink:
    - opensearch:
        hosts:
          - "https://opensearch-1.example.com:9200"
          - "https://opensearch-2.example.com:9200"
        index_type: trace-analytics-raw
        username: "admin"
        password: "admin"
        insecure: true
        bulk_size: 5000
        flush_timeout: 30s

service-map-pipeline:
  source:
    pipeline:
      name: entry-pipeline
  
  processor:
    # service_map_stateful корректно работает, 
    # так как все спаны трейса на одной ноде
    - service_map_stateful:
        window_duration: 180s
  
  sink:
    - opensearch:
        hosts:
          - "https://opensearch-1.example.com:9200"
          - "https://opensearch-2.example.com:9200"
        index_type: trace-analytics-service-map
        username: "admin"
        password: "admin"
        insecure: true
```

## Преимущества этого подхода

### 1. **Простота конфигурации**
- Не нужен отдельный балансировщик (HAProxy/Nginx)
- Не нужен peer_forwarder в Data Prepper
- Меньше сетевого трафика между компонентами

### 2. **Гарантированная целостность трейсов**
```
Пример распределения:
- Trace ABC → всегда на dp-node1
- Trace DEF → всегда на dp-node2
- Trace GHI → всегда на dp-node3
- Trace ABC (новые спаны) → снова на dp-node1 ✓
```

### 3. **Корректная работа service-map**
Так как все спаны одного трейса обрабатываются на одной ноде:
- `service_map_stateful` процессор видит полную картину трейса
- Правильно строятся связи между сервисами
- Корректно рассчитываются метрики latency и error rate

## Как проверить, что работает правильно

### 1. Включите debug логирование в otelcol
```yaml
service:
  telemetry:
    logs:
      level: debug
```

В логах увидите:
```
Traces were routed to backend dp-node2.example.com:21890 for traceID abc123...
```

### 2. Мониторинг распределения нагрузки
```bash
# На каждой ноде Data Prepper смотрите метрики
curl http://dp-node1.example.com:4901/metrics | grep traces_received

# Должны видеть разные traceID на разных нодах, 
# но один traceID всегда на одной ноде
```

### 3. Проверка в OpenSearch Dashboards
- Откройте Trace Analytics
- Найдите конкретный trace
- Все его спаны должны быть полными (не разорванными)
- Service Map должна корректно показывать все связи

## Обработка сбоев

### При падении одной ноды Data Prepper

Loadbalancing exporter автоматически перераспределит трейсы:
```yaml
exporters:
  loadbalancing/dataprepper:
    routing_key: traceID
    protocol:
      otlp:
        retry_on_failure:
          enabled: true
          initial_interval: 5s
          max_interval: 30s
        # Важно: timeout должен быть меньше, чем интервал health check
        timeout: 10s
```

При восстановлении ноды:
- Новые трейсы могут начать маршрутизироваться на нее
- Существующие трейсы продолжат идти на прежние ноды (консистентность)

## Важные настройки для production

### 1. Health checks в resolver
```yaml
resolver:
  static:
    hostnames:
      - dp-node1.example.com:21890
      - dp-node2.example.com:21890
      - dp-node3.example.com:21890
    # Интервал проверки доступности (если поддерживается версией)
    interval: 5s
```

### 2. Настройка батчирования с учетом traceID
```yaml
processors:
  batch:
    timeout: 10s
    send_batch_size: 8192
    # Группировка по traceID происходит после батчирования
```

### 3. Мониторинг "залипания" трейсов
Следите, чтобы распределение было равномерным:
```bash
# Скрипт для проверки распределения
for node in dp-node1 dp-node2 dp-node3; do
  echo "$node: $(curl -s http://$node.example.com:4901/metrics | grep 'traces_received_total' | awk '{print $2}')"
done
```

## Итог

**Да, это оптимальное решение для статической инфраструктуры:**
- OpenTelemetry Collector с `routing_key: traceID` гарантирует, что все спаны одного трейса попадут на один Data Prepper
- Не нужен дополнительный балансировщик
- Не нужен peer_forwarder в Data Prepper
- Service-map строится корректно
- Конфигурация простая и надежная

Это решение я рекомендую для production использования в статической инфраструктуре.
