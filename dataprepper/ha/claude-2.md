Рассмотрю два основных варианта обеспечения HA и горизонтального масштабирования Data Prepper в вашей цепочке.

## Вариант 1: С использованием балансировщика

### Архитектура
```
otelcol → Load Balancer → [Data Prepper 1, 2, 3...N] → OpenSearch
```

### Конфигурация Data Prepper с peer_forwarder

Data Prepper поддерживает горизонтальное масштабирование с использованием core peer forwarder для развертывания нескольких инстансов, формирующих кластер. Это позволяет инстансам Data Prepper взаимодействовать друг с другом в кластере и является обязательным для горизонтально масштабируемых развертываний.

**data-prepper-config.yaml:**
```yaml
# Конфигурация peer forwarder
peer_forwarder:
  port: 4910
  discovery_mode: dns  # или static, aws_cloud_map
  domain_name: "dataprepper-headless.namespace.svc.cluster.local"  # для K8s
  # Для static discovery:
  # discovery_mode: static  
  # static_endpoints: ["dp-node1:4910", "dp-node2:4910", "dp-node3:4910"]
  
  # SSL/TLS настройки (опционально)
  ssl: false
  # ssl_certificate_file: "/path/to/cert.pem"
  # ssl_key_file: "/path/to/key.pem"
  
  # Таймауты и батчинг
  max_batch_event_count: 48
  time_out: 300

# REST API настройки  
serverPort: 4900
ssl: false
```

**pipelines.yaml:**
```yaml
entry-pipeline:
  source:
    otel_trace_source:
      port: 21890
      ssl: false
  buffer:
    bounded_blocking:
      buffer_size: 25600
      batch_size: 400
  processor:
    - trace_peer_forwarder:
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
        hosts: ["https://opensearch-1:9200", "https://opensearch-2:9200"]
  sink:
    - opensearch:
        hosts: ["https://opensearch-1:9200", "https://opensearch-2:9200"]
        index_type: trace-analytics-raw
        bulk_size: 5000
        max_retries: 5
        retry_backoff: exponential
        initial_delay: 100ms
        max_delay: 30s

service-map-pipeline:
  source:
    pipeline:
      name: entry-pipeline
  processor:
    - service_map:
  sink:
    - opensearch:
        hosts: ["https://opensearch-1:9200", "https://opensearch-2:9200"]
        index_type: trace-analytics-service-map
```

### Конфигурация otelcol (указывает на балансировщик)
```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 10s
    send_batch_size: 8192
  memory_limiter:
    check_interval: 1s
    limit_mib: 512

exporters:
  otlp/dataprepper:
    endpoint: dataprepper-lb.example.com:21890  # Адрес балансировщика
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

### Настройка в Kubernetes

**Deployment:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: data-prepper
spec:
  replicas: 3
  selector:
    matchLabels:
      app: data-prepper
  template:
    metadata:
      labels:
        app: data-prepper
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: data-prepper
              topologyKey: kubernetes.io/hostname
      containers:
      - name: data-prepper
        image: opensearchproject/data-prepper:latest
        ports:
        - containerPort: 21890  # OTLP
        - containerPort: 4910   # Peer forwarder
        - containerPort: 4900   # API
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
```

**Services:**
```yaml
# Сервис для балансировки входящего трафика
apiVersion: v1
kind: Service
metadata:
  name: data-prepper-lb
spec:
  selector:
    app: data-prepper
  ports:
  - name: otlp
    port: 21890
    targetPort: 21890
  type: LoadBalancer  # или ClusterIP с Ingress

---
# Headless сервис для peer discovery
apiVersion: v1
kind: Service
metadata:
  name: dataprepper-headless
spec:
  clusterIP: None
  selector:
    app: data-prepper
  ports:
  - name: peer
    port: 4910
    targetPort: 4910
```

## Вариант 2: Несколько Data Prepper напрямую в otelcol

### Архитектура
```
otelcol (с loadbalancing exporter) → [Data Prepper 1, 2, 3...N] → OpenSearch
```

### Конфигурация otelcol с loadbalancing exporter

Loadbalancing exporter поддерживает маршрутизацию на основе traceID для трейсов. Если установить поле routing_key в "traceID", экспортер будет отправлять спаны на основе их traceID, либо можно использовать "service" для маршрутизации по имени сервиса.

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 10s
    send_batch_size: 8192
  memory_limiter:
    check_interval: 1s
    limit_mib: 512

exporters:
  loadbalancing/dataprepper:
    routing_key: traceID  # Критически важно для целостности трейсов!
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
      # Вариант 1: DNS resolver (для K8s headless service)
      dns:
        hostname: dataprepper-headless.namespace.svc.cluster.local
        port: 21890
        interval: 5s
      
      # Вариант 2: Static resolver
      # static:
      #   hostnames:
      #   - dataprepper-1.example.com:21890
      #   - dataprepper-2.example.com:21890
      #   - dataprepper-3.example.com:21890
      
      # Вариант 3: K8s service resolver
      # k8s:
      #   service: data-prepper
      #   ports:
      #   - 21890

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [loadbalancing/dataprepper]
```

### Упрощенная конфигурация Data Prepper (без peer_forwarder)

При использовании loadbalancing exporter с `routing_key: traceID`, peer_forwarder в Data Prepper не обязателен:

```yaml
# data-prepper-config.yaml
serverPort: 4900
ssl: false
# peer_forwarder не нужен при правильной маршрутизации в otelcol

# pipelines.yaml
entry-pipeline:
  source:
    otel_trace_source:
      port: 21890
      ssl: false
  buffer:
    bounded_blocking:
      buffer_size: 25600
      batch_size: 400
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
        hosts: ["https://opensearch:9200"]
  sink:
    - opensearch:
        hosts: ["https://opensearch-1:9200", "https://opensearch-2:9200"]
        index_type: trace-analytics-raw
        bulk_size: 5000
        max_retries: 5

service-map-pipeline:
  source:
    pipeline:
      name: entry-pipeline
  processor:
    - service_map_stateful:
  sink:
    - opensearch:
        hosts: ["https://opensearch-1:9200", "https://opensearch-2:9200"]
        index_type: trace-analytics-service-map
```

## Сравнение вариантов

| Аспект | Вариант 1 (с LB) | Вариант 2 (loadbalancing в otelcol) |
|--------|------------------|--------------------------------------|
| **Сложность конфигурации** | Средняя (настройка peer_forwarder) | Простая (только otelcol) |
| **Гибкость маршрутизации** | Ограничена возможностями LB | Полный контроль через routing_key |
| **Отказоустойчивость** | Зависит от LB | Встроенная в loadbalancing exporter |
| **Сетевые хопы** | Дополнительный хоп через LB | Прямое соединение |
| **Масштабирование** | Простое добавление нод | Требует обновления DNS/списка |
| **Когда использовать** | Уже есть инфраструктура LB, множество источников otelcol | Полный контроль над otelcol, минимум хопов |

## Важные рекомендации для обоих вариантов

### 1. Обеспечение целостности трейсов
Peer forwarder использует подход hash-ring для агрегации событий и определения, какая нода Data Prepper должна их обрабатывать на основе данного трейса. Peer forwarder группирует события на основе идентификационных ключей. Для service_map_stateful и otel_trace_raw идентификационным ключом является traceId по умолчанию.

### 2. Автомасштабирование (HPA в K8s)
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: data-prepper-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: data-prepper
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### 3. Мониторинг и метрики
Core peer forwarder предоставляет метрики с префиксом core.peerForwarder, включая requestForwardingLatency (задержка запросов, пересылаемых клиентом peer forwarder) и requestProcessingLatency (задержка запросов, обрабатываемых сервером peer forwarder).

### 4. Производительность
- Начальная оценка: количество реплик = ceil(пиковая нагрузка спанов/с / производительность одной реплики × 1.5-2x запас)
- Типичная производительность одной реплики: 5000-10000 спанов/с (зависит от ресурсов и обработки)

## Выбор варианта

**Используйте Вариант 1 (с балансировщиком), если:**
- У вас уже есть инфраструктура балансировщиков
- Множество независимых источников otelcol
- Нужна простая точка входа для всех коллекторов
- Хотите изолировать логику маршрутизации от otelcol

**Используйте Вариант 2 (loadbalancing в otelcol), если:**
- Хотите минимизировать сетевые хопы
- Нужен полный контроль над маршрутизацией трейсов
- У вас небольшое количество управляемых otelcol
- Важна прямая связь между компонентами

Оба варианта обеспечивают HA и горизонтальное масштабирование, выбор зависит от вашей инфраструктуры и требований.
