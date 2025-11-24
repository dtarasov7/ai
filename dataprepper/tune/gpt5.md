Ниже — проверенный набор приёмов, чтобы связка OTel Collector → Data Prepper держала высокий поток трейсов и не «падала». Я разделил рекомендации на «быстро стабилизировать сейчас», «тюнинг Collector», «тюнинг Data Prepper», «горизонтальное масштабирование» и «наблюдение/метрики».

Что сделать в первую очередь (для стабилизации)
- Включите в Collector memory_limiter и batch, а в exporter — отправную очередь с ретраями (sending_queue + retry_on_failure). Это гасит всплески и даёт бэкпрешер вместо OOM/штормов ретраев. 
- Уменьшите размер запросов из Collector к Data Prepper: ограничьте send_batch_size для трасс ≈ 50. Это прямо рекомендуют в руководстве по Trace Analytics для Data Prepper, чтобы каждое ExportTraceRequest было небольшим и предсказуемым. 
- Переключите экспорт трасс из Collector в Data Prepper на OTLP/gRPC и включите сжатие (gzip — по умолчанию), чтобы снизить CPU/сеть. Убедитесь, что бьёте в порт источника otel_trace_source (по умолчанию 21890). 
- На стороне Data Prepper поднимите JVM heap и зафиксируйте Xms=Xmx (G1GC по умолчанию у современных JVM). Если у вас OOM — увеличьте heap и уменьшите буферы/батчи (ниже — как). 

Пример минимального конфига Collector для «смягчения»
```yaml
receivers:
  otlp:
    protocols:
      grpc: {}     # принимаем от агентов/SDK

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 2048         # подберите под лимиты Pod/VM
    spike_limit_mib: 512
  batch/traces:
    send_batch_size: 50      # ключевой параметр для DP
    send_batch_max_size: 200
    timeout: 200ms

exporters:
  otlp/dataprepper:
    endpoint: dataprepper:21890
    compression: gzip
    # очередь + ретраи
    sending_queue:
      queue_size: 5000
      # опционально — WAL (постоянная очередь) для устойчивости:
      # storage: file_storage
    retry_on_failure:
      enabled: true
      initial_interval: 1s
      max_interval: 30s
      max_elapsed_time: 10m

# для persistent queue (опционально)
extensions:
  file_storage:
    directory: /var/lib/otelcol/wal

service:
  extensions: [file_storage]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch/traces]
      exporters: [otlp/dataprepper]
```
Пояснения: memory_limiter предотвращает OOM и даёт бэкпрешер; batch снижает накладные расходы; sending_queue + retry_on_failure разгружает пики; file_storage превращает очередь в WAL, переживает рестарты Collector. 

Тюнинг Data Prepper (pipelines.yaml и общие настройки)
- Источник для трейсинга: otel_trace_source. Важные параметры под нагрузку: port (по умолчанию 21890), max_connection_count, thread_count, max_request_length, request_timeout. Увеличьте max_connection_count и thread_count, если много одновременных подключений Collector’ов; не ставьте слишком высокий request_timeout, чтобы не накапливать «зависшие» запросы и ретраи. 
- Буфер и батчи: держите buffer_size одинаковым в входном (otel-trace-pipeline/entry) и raw-пайплайне и соблюдайте правило buffer_size ≥ workers * batch_size. Увеличивать бездумно нельзя — это напрямую расходует heap. 
- workers поднимайте по CPU (I/O-зависимость позволяет иметь workers больше числа vCPU). Начните с числа ядер и увеличивайте, наблюдая за загрузкой и GC. 
- Рекомендуемая связка значений (пример):
```yaml
otel-trace-pipeline:
  workers: 8
  delay: "100"
  source:
    otel_trace_source:
      port: 21890
      max_connection_count: 2000
      thread_count: 400
      max_request_length: 10mb  # увеличивайте осторожно
      ssl: false
  buffer:
    bounded_blocking:
      buffer_size: 1024        # одинаково в entry/raw
      batch_size: 16           # см. правило ниже
  sink:
    - pipeline: { name: "raw-trace-pipeline" }
    - pipeline: { name: "service-map-pipeline" }

raw-trace-pipeline:
  workers: 8
  delay: "3000"
  source: { pipeline: { name: "entry-pipeline" } }
  buffer:
    bounded_blocking:
      buffer_size: 1024
      batch_size: 64           # крупнее, т.к. bulk в OpenSearch
  processor:
    - otel_traces: {}          # группировка traceGroup и пр.
  sink:
    - opensearch:
        hosts: ["https://opensearch:9200"]
        index_type: trace-analytics-raw
        bulk_size: 5           # MiB; подбирайте по сети/кластеру
        max_retries: 20
        # рекомендуется настроить DLQ:
        dlq_file: /var/lib/data-prepper/dlq/trace.dlq
```
Аргументация: Data Prepper прямо рекомендует держать buffer_size ≥ workers*batch_size; raw-пайплайн может иметь больший batch_size, т.к. пишет bulk’ом в OpenSearch. У opensearch sink есть bulk_size и DLQ/max_retries — это сильно влияет на устойчивость при «задыхании» кластера. 

- JVM/GC: задайте JVM_OPTS, например -Xms4g -Xmx4g (или больше, если рост heap неизбежен), включите G1GC (дефолт на современных JDK), при нагрузке следите за паузами GC и при необходимости повышайте heap и/или уменьшайте буферы/батчи. 

Горизонтальное масштабирование: держать трассы «цельными»
- Несколько Data Prepper узлов: включите peer_forwarder, чтобы события одного traceId обрабатывал один узел. Это необходимо для service map/агрегаций. Для больших кластеров удобнее discovery_mode: dns. 
- В Trace Analytics используйте trace_peer_forwarder, чтобы не дублировать форвардинг между raw и service-map пайплайнами — это почти вдвое режет лишний сетевой трафик между нодами DP. 
- Перед Data Prepper поставьте «шардер» на стороне Collector:
  - loadbalancing exporter с routing_key=traceID и списком хостов Data Prepper. Так все спаны одного трейса поедут на один и тот же DP, а масштабирование станет линейным. 
```yaml
exporters:
  loadbalancing/dp:
    routing_key: traceID
    protocol:
      otlp: {}   # gRPC
    resolver:
      dns:
        hostname: dataprepper-headless.tracing.svc.cluster.local

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch/traces]
      exporters: [loadbalancing/dp]
```

Снижение объёма до Data Prepper (когда «много лишнего»)
- Сэмплирование в Collector:
  - probabilistic_sampler (head-based) — просто и эффективно, когда важно безусловно сбрасывать долю трафика. 
  - tail_sampling — если нужно выборочно сохранять «важные» трейсы (ошибки/медленные/по атрибутам). Для горизонтального масштаба объединяйте с loadbalancing по traceID и groupbytrace. 
- Фильтрация/нормализация: отрежьте ненужные спаны/атрибуты (filter/attributes/transform процессоры) и ограничьте размеры атрибутов, чтобы не раздувать память/сеть. 

Если пики всё равно «роняют» тракт — разнесите по очереди
- Вставьте Kafka между Collector и Data Prepper: Collector → Kafka exporter; Data Prepper читает из Kafka через kafka source (или используйте kafka buffer внутри Data Prepper). Это эффективно сглаживает пики и даёт долговременную буферизацию. 

Мониторинг и приёмы диагностики
- На Collector следите за:
  - otelcol_processor_refused_spans (memory_limiter — признак, что давится по памяти),
  - otelcol_exporter_queue_size/queue_capacity, otelcol_exporter_send_failed_spans. Если очереди долго заполнены — увеличивайте queue_size/реплики или снижайте трафик. 
- В Data Prepper наблюдайте метрики процессоров (recordsIn/Out, timeElapsed) и кастомные у otel_traces (traceGroupCacheCount, spanSetCount); при росте — масштабируйтесь горизонтально и/или уменьшайте окна агрегаций/service map. 
- Для OpenSearch sink отслеживайте ретраи/ошибки, подбирайте bulk_size и настройте DLQ, чтобы не блокироваться на «ядовитых» документах. 

Чек‑лист признаков и быстрых фиксов
- OOM у Data Prepper: увеличьте heap и уменьшите buffer_size/batch_size/workers; проверьте, нет ли слишком больших ExportTraceRequest (увеличьте send_batch_size=50 в Collector). 
- 429/5xx от Data Prepper и лавинообразные ретраи: уменьшите send_batch_size/timeout в Collector, включите sending_queue и ограничьте параллелизм (batch уменьшает конкурентность), поднимите max_connection_count на otel_trace_source. 
- Падает из‑за service map/агрегаций: включите peer_forwarder и trace_peer_forwarder; масштабируйте DP; при необходимости уменьшите окно service_map. 

Если пришлёте вашу текущую:
- версию Data Prepper/Collector,
- фрагменты pipelines.yaml и collector-config.yaml (только трейс‑пайплайны),
- тип «падения» (OOM, CrashLoopBackOff, timeout’ы),
- порядок нагрузки (трассов/сервисов в секунду),

я точечно подберу значения buffer_size/batch_size/workers, настройки exporter’ов и, при необходимости, шаблон для лоад‑балансинга/peer‑forwarder под ваш кейс.
