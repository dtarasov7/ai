Ниже — два рабочих варианта для HA и горизонтального масштабирования Data Prepper в цепочке otelcol → dataprepper → OpenSearch. Оба сохраняют целостность трэйсов (все спаны одного trace попадают на одну ноду), а различаются местом, где обеспечивается «аффинность по traceID».

Вариант A: балансировщик между otelcol и пулом Data Prepper
- Идея: otelcol шлёт на один адрес (LB), за которым крутятся N реплик Data Prepper. «Склейку» трэйсов обеспечивает сам Data Prepper через peer_forwarder.
- Почему так: классический L4/L7‑LB не умеет хешировать по traceID для OTLP/gRPC; значит аффинность надёжно сделать внутри Data Prepper.

Что настроить
1) Data Prepper с peer_forwarder (все реплики должны «видеть» друг друга):
- discovery через статический список или DNS (в k8s — headless‑Service).
- peer_forwarder сам перешлёт части одного trace на «ответственную» ноду.

Пример pipelines.yaml (упростил до сути; адаптируйте ключи под вашу версию Data Prepper):
```yaml
# pipelines.yaml
otel-traces:
  source:
    otel_trace_source:
      # приём OTLP gRPC (или http, если используете HTTP)
      port: 21890
      ssl: false
  processor:
    - peer_forwarder:
        # один из вариантов discovery
        discovery_mode: dns
        domain_name: dataprepper-headless.default.svc.cluster.local
        # опционально: health_check_interval: 10s, connection_timeout: 5s
    - service_map: {}
  sink:
    - opensearch:
        hosts: ["https://opensearch-1:9200","https://opensearch-2:9200"]
        index_type: trace-analytics-raw
        # ретраи, backoff, размер и параллелизм bulk
        bulk_size: 5_000
        max_retries: 5
        retry_backoff: 200ms
```

2) Балансировщик:
- L4 (TCP) на порт OTLP gRPC (например 21890) с health‑check’ами к /health (если включено) или TCP‑probe.
- В k8s: обычный Service type LoadBalancer на Deployment Data Prepper; для peer_forwarder сделайте отдельный headless‑Service (ClusterIP: None), чтобы реплики находили друг друга.
- Sticky по traceID на LB не требуется (и для OTLP сделать это сложно/ненадёжно).

3) Конфиг otelcol — указывает один endpoint (адрес LB), batch+retry для устойчивости:
```yaml
receivers:
  otlp:
    protocols: {grpc: {}, http: {}}

processors:
  memory_limiter: {}
  batch: {timeout: 5s, send_batch_size: 8192}
  retry: {}  # если используете версию с отдельным retry, иначе в экспортере

exporters:
  otlp/dataprepper:
    endpoint: dataprepper-lb.example:21890
    tls: {insecure: true}   # или mTLS

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/dataprepper]
```

Плюсы
- Простая точка подключения для otelcol.
- Со временем просто добавляете/убираете реплики Data Prepper — кластер сам перераспределит трэйсы.

Важные детали
- Все реплики Data Prepper должны обмениваться между собой (peer_forwarder) и видеть один и тот же discovery.
- В OpenSearch укажите несколько хостов и корретно настройте ретраи/бэкоффы.
- Следите за метриками Data Prepper: рост retry, рост latency flush, очереди — сигнал к масштабированию.


Вариант B: несколько Data Prepper напрямую в конфигурации otelcol
- Идея: без внешнего LB. В otelcol используем loadbalancing exporter с консистентным хешированием по traceID → аффинность обеспечивает otelcol, а Data Prepper можно не настраивать на peer_forwarder.
- Когда удобно: k8s/VM, где легко дать otelcol список/имя‑шаблон реплик Data Prepper (DNS A‑records/headless‑Service).

Конфиг otelcol (loadbalancing exporter)
```yaml
receivers:
  otlp:
    protocols: {grpc: {}, http: {}}

processors:
  memory_limiter: {}
  batch: {timeout: 5s, send_batch_size: 8192}

exporters:
  loadbalancing/dataprepper:
    routing_key: traceID        # ключ консистентного хеширования
    protocol:
      otlp:
        # Параметры OTLP к целевым Data Prepper
        tls: {insecure: true}   # или настроенный TLS/mTLS
        # timeout, compression и т.п.
    resolver:
      dns:
        # Вариант 1: headless‑Service с несколькими A‑записями
        hostname: dataprepper-headless.default.svc.cluster.local
        port: 21890
        # Вариант 2: статический список адресов (если ваша сборка это поддерживает)
        # hostnames: ["dp-0.example:21890","dp-1.example:21890","dp-2.example:21890"]

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [loadbalancing/dataprepper]
```

Data Prepper в этом варианте можно упростить (peer_forwarder не обязателен):
```yaml
otel-traces:
  source:
    otel_trace_source:
      port: 21890
      ssl: false
  processor:
    - service_map: {}
  sink:
    - opensearch:
        hosts: ["https://opensearch-1:9200","https://opensearch-2:9200"]
        index_type: trace-analytics-raw
```

Плюсы
- Нет лишнего сетевого хопа (без LB).
- Чёткая аффинность по traceID на стороне otelcol, легко горизонтально масштабировать «добавил реплику — перераспределилось».

Важные детали
- Используйте именно loadbalancing exporter; базовый otlp‑exporter с одним endpoint не распределяет трафик по множеству A‑записей предсказуемо.
- При падении ноды Data Prepper exporter пересчитает хеш‑кольцо и повторит отправку; вместе с batch/ret ry получите мягкий backpressure вместо потери данных.
- Если у вас несколько кластеров otelcol, следите, чтобы все они видели одинаковый набор адресов Data Prepper (одинаковый DNS).


Общие практики для обоих вариантов
- Реплик Data Prepper ≥ 2–3; разнести по разным хостам/зонам (anti‑affinity).
- Health‑checks + readiness, graceful shutdown, RollingUpdate с maxUnavailable=1.
- HPA/автоскейл по CPU/Memory и пользовательским метрикам (rate спанов, размер очередей/бекпрешера).
- В OpenSearch:
  - несколько хостов, backoff/ретраи, контролируемый bulk (размер и параллелизм),
  - ISM/ILM политики для trace индексов, шаблоны и алиасы.
- Безопасность: TLS/mTLS на всех участках, ограничение допустимых размеров батчей, лимиты на max spans per trace.
- Нагрузочные тесты до продакшена; ориентир по sizing: реплики = ceil(пиковый RPS спанов / пропускная способность 1 реплики × запас 1.5–2x).

Когда выбрать что
- Нужна простота на стороне otelcol или у вас уже есть корпоративный LB — берите Вариант A (peer_forwarder включён).
- Хотите меньше hop’ов и контролируете конфиги otelcol — берите Вариант B (loadbalancing exporter по traceID), peer_forwarder можно не включать.

Могу подготовить точные конфиги под вашу среду. Подскажите:
- Kubernetes или VM? Какая версия Data Prepper/otelcol?
- OTLP протокол: gRPC или HTTP?
- Ожидаемый пик спанов/сек и требования к сохранности (нужна ли промежуточная очередь типа Kafka)?
