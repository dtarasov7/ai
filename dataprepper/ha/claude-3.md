Рассмотрю оба варианта для статической инфраструктуры (VM/bare metal) с акцентом на сохранение целостности трейсов для построения service-map.

## Вариант 1: С балансировщиком (HAProxy/Nginx)

### Архитектура
```
otelcol → HAProxy/Nginx → [Data Prepper 1, 2, 3] → OpenSearch
                ↓
         peer_forwarder между Data Prepper
```

### Конфигурация Data Prepper с peer_forwarder

Для корректного построения service-map критически важно, чтобы все спаны одного трейса обрабатывались одним инстансом Data Prepper. Это обеспечивается через peer_forwarder.

**Data Prepper 1 (dp-node1.example.com):**

`data-prepper-config.yaml`:
```yaml
# Настройки peer forwarder для кластеризации
peer_forwarder:
  port: 4994
  discovery_mode: static
  static_endpoints:
    - "dp-node1.example.com:4994"
    - "dp-node2.example.com:4994"
    - "dp-node3.example.com:4994"
  
  # Настройки для обработки трейсов
  max_peer_client_connections: 200
  client_timeout: 10s
  server_timeout: 10s
  
  # SSL между пирами (опционально, но рекомендуется)
  ssl: false
  # ssl_certificate_file: "/etc/dataprepper/certs/cert.pem"
  # ssl_key_file: "/etc/dataprepper/certs/key.pem"
  
  # Важно для service-map
  drain_timeout: 30s

# REST API для мониторинга
serverPort: 4900
health_check_service: true
```

`pipelines.yaml`:
```yaml
# Входной пайплайн для приема OTLP трейсов
entry-pipeline:
  source:
    otel_trace_source:
      address: 0.0.0.0:21890
      ssl: false
      # Опционально: аутентификация
      # authentication:
      #   http_basic:
      #     username: "dataprepper"
      #     password: "secret"
  
  buffer:
    bounded_blocking:
      buffer_size: 25600
      batch_size: 400
  
  processor:
    # Peer forwarder для распределения трейсов по traceId
    - trace_peer_forwarder:
  
  sink:
    - pipeline:
        name: raw-trace-pipeline
    - pipeline:
        name: service-map-pipeline

# Пайплайн для сырых трейсов
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
        insecure: true  # или настройте сертификаты
        bulk_size: 5000
        max_retries: 5
        retry_backoff: exponential
        max_retry_backoff: 30s
        # Важно для производительности
        flush_timeout: 30s
        index_type: trace-analytics-raw

# Пайплайн для service-map (критически важен stateful процессор!)
service-map-pipeline:
  source:
    pipeline:
      name: entry-pipeline
  
  processor:
    - service_map_stateful:
        # Важные настройки для корректной агрегации
        window_duration: 180s  # окно агрегации
        
  sink:
    - opensearch:
        hosts:
          - "https://opensearch-1.example.com:9200"
          - "https://opensearch-2.example.com:9200"
        index_type: trace-analytics-service-map
        username: "admin"
        password: "admin"
        insecure: true
        bulk_size: 100
```

**Data Prepper 2 и 3 - идентичная конфигурация**, только меняется hostname в логах/метриках.

### Конфигурация HAProxy

`/etc/haproxy/haproxy.cfg`:
```cfg
global
    log /dev/log local0
    maxconn 4096
    daemon

defaults
    log     global
    mode    tcp
    option  tcplog
    option  dontlognull
    timeout connect 5000
    timeout client  50000
    timeout server  50000

# Фронтенд для OTLP gRPC
frontend dataprepper_frontend
    bind *:21890
    mode tcp
    default_backend dataprepper_backend

# Бэкенд с раундробином (peer_forwarder сам разрулит трейсы)
backend dataprepper_backend
    mode tcp
    balance roundrobin
    option tcp-check
    
    server dp1 dp-node1.example.com:21890 check port 4900 inter 2000
    server dp2 dp-node2.example.com:21890 check port 4900 inter 2000
    server dp3 dp-node3.example.com:21890 check port 4900 inter 2000

# Статистика (опционально)
stats enable
stats uri /stats
stats refresh 30s
```

### Конфигурация otelcol

`otel-collector-config.yaml`:
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
  otlp/dataprepper:
    endpoint: haproxy.example.com:21890  # Адрес HAProxy
    tls:
      insecure: true
    sending_queue:
      enabled: true
      num_consumers: 10
      queue_size: 1000
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/dataprepper]
```

## Вариант 2: Прямое указание нескольких Data Prepper в otelcol

### Архитектура
```
otelcol (loadbalancing exporter) → [Data Prepper 1, 2, 3] → OpenSearch
                                           ↓
                                    peer_forwarder между DP
```

### Конфигурация otelcol с loadbalancing exporter

`otel-collector-config.yaml`:
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

exporters:
  loadbalancing/dataprepper:
    # КРИТИЧНО: используем traceID для маршрутизации!
    routing_key: traceID
    
    protocol:
      otlp:
        tls:
          insecure: true
        sending_queue:
          enabled: true
          num_consumers: 10
          queue_size: 1000
        retry_on_failure:
          enabled: true
          initial_interval: 5s
          max_interval: 30s
    
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

### Упрощенная конфигурация Data Prepper

При использовании `routing_key: traceID` в loadbalancing exporter, можно отключить peer_forwarder:

`data-prepper-config.yaml`:
```yaml
# Peer forwarder можно отключить при правильной маршрутизации в otelcol
# peer_forwarder:
#   port: 4994

serverPort: 4900
health_check_service: true
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
  
  # БЕЗ trace_peer_forwarder!
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

service-map-pipeline:
  source:
    pipeline:
      name: entry-pipeline
  
  processor:
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

## Systemd сервисы для Data Prepper

`/etc/systemd/system/dataprepper.service`:
```ini
[Unit]
Description=Data Prepper
After=network.target

[Service]
Type=simple
User=dataprepper
Group=dataprepper
ExecStart=/opt/dataprepper/bin/data-prepper -c /etc/dataprepper/data-prepper-config.yaml -p /etc/dataprepper/pipelines.yaml
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

## Сравнение вариантов для статической инфраструктуры

| Критерий | Вариант 1 (HAProxy + peer_forwarder) | Вариант 2 (loadbalancing в otelcol) |
|----------|---------------------------------------|--------------------------------------|
| **Целостность трейсов** | Обеспечивается peer_forwarder | Обеспечивается routing_key: traceID |
| **Service-map** | ✓ Работает корректно | ✓ Работает корректно |
| **Сложность настройки** | Средняя (HAProxy + peer_forwarder) | Простая (только в otelcol) |
| **Отказоустойчивость** | HAProxy - single point of failure* | Встроенная в otelcol |
| **Масштабирование** | Простое добавление в HAProxy | Требует перезапуска otelcol |
| **Сетевая нагрузка** | Выше (peer_forwarder traffic) | Ниже (прямые соединения) |
| **Мониторинг** | HAProxy stats + DP metrics | Только DP metrics |

*Можно использовать keepalived для HA самого HAProxy

## Критические моменты для service-map

1. **Обязательная аффинность по traceID**
   - Вариант 1: обеспечивается через peer_forwarder
   - Вариант 2: через routing_key: traceID в loadbalancing exporter

2. **Настройки процессоров**
   ```yaml
   - service_map_stateful:
       window_duration: 180s  # Окно агрегации должно быть одинаковым на всех нодах
   ```

3. **Синхронизация времени**
   ```bash
   # На всех нодах Data Prepper
   sudo apt install chrony
   sudo systemctl enable chrony
   sudo chronyc sources
   ```

## Мониторинг и метрики

### Prometheus метрики Data Prepper
```yaml
# В data-prepper-config.yaml добавить:
metrics_registries:
  - prometheus:
      port: 4901
```

### Health checks
```bash
# Проверка здоровья Data Prepper
curl http://dp-node1.example.com:4900/health

# Метрики
curl http://dp-node1.example.com:4901/metrics
```

## Рекомендации по выбору

**Используйте Вариант 1 (HAProxy), если:**
- Нужна единая точка входа для множества otelcol
- Уже есть опыт с HAProxy/Nginx
- Готовы настраивать peer_forwarder
- Важна изоляция логики балансировки

**Используйте Вариант 2 (loadbalancing в otelcol), если:**
- Хотите минимальную конфигурацию
- У вас контролируемое количество otelcol
- Важно снизить сетевой трафик между Data Prepper
- Хотите избежать single point of failure в виде балансировщика

Для production рекомендую **Вариант 2** как более простой и надежный для статической инфраструктуры.
