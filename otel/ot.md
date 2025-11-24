Чтобы настроить **Data Prepper** так, чтобы трейсы от разных **OpenTelemetry Collector**'ов попадали в разные индексы **OpenSearch**, нужно использовать **условную маршрутизацию** (conditional routing) в конфигурации Data Prepper. Это достигается с помощью **`routes`** и **`conditions`** в pipeline-конфигурации.

---

### 🔧 Общая идея

1. **Добавить метку (attribute)** в телеметрию на стороне OpenTelemetry Collector, чтобы идентифицировать источник.
2. В Data Prepper использовать эту метку в **условии маршрутизации**, чтобы направлять данные в нужный sink (OpenSearch index).
3. Настроить несколько **sink'ов** в Data Prepper с разными именами индексов.

---

## Шаг 1: Добавьте атрибут в OpenTelemetry Collector

В каждом OpenTelemetry Collector (или в его конфигурации) добавьте уникальный атрибут, например `collector.id`.

Пример конфига для одного из коллекторов (`otel-collector.yaml`):

```yaml
processors:
  attributes/add_collector_id:
    actions:
      - key: collector.id
        value: "collector-a"
        action: insert

service:
  pipelines:
    traces:
      processors: [attributes/add_collector_id]
      # ... exporters и receivers
```

Для другого коллектора используйте, например, `collector.id: "collector-b"`.

> 💡 Атрибут будет добавлен к каждому span'у, и вы сможете использовать его в Data Prepper.

---

## Шаг 2: Настройка Data Prepper pipeline

В файле `pipelines.yaml` (или аналогичном) создайте pipeline с несколькими маршрутами:

```yaml
entry-pipeline:
  source:
    otel_trace_source:
      ssl: false
  processor:
    - route:
        routes:
          - route: "collector_a_traces"
            condition: "/attributes/collector.id == 'collector-a'"
          - route: "collector_b_traces"
            condition: "/attributes/collector.id == 'collector-b'"
          # можно добавить default route, если нужно
  sink:
    - pipeline:
        name: "collector-a-pipeline"
      routes: ["collector_a_traces"]
    - pipeline:
        name: "collector-b-pipeline"
      routes: ["collector_b_traces"]

collector-a-pipeline:
  source:
    pipeline:
      name: "entry-pipeline"
  sink:
    - opensearch:
        hosts: ["https://your-opensearch:9200"]
        username: "admin"
        password: "admin"
        trace_analytics_raw: true
        index_type: "trace-analytics-raw"
        index: "traces-collector-a-%{yyyy.MM.dd}"

collector-b-pipeline:
  source:
    pipeline:
      name: "entry-pipeline"
  sink:
    - opensearch:
        hosts: ["https://your-opensearch:9200"]
        username: "admin"
        password: "admin"
        trace_analytics_raw: true
        index_type: "trace-analytics-raw"
        index: "traces-collector-b-%{yyyy.MM.dd}"
```

> 🔍 Обратите внимание:
> - `route` используется для фильтрации спанов по атрибуту.
> - Каждый pipeline направляет данные в свой индекс OpenSearch.
> - Используется `trace_analytics_raw: true`, чтобы сохранить формат, совместимый с Trace Analytics в OpenSearch Dashboards.

---

## Шаг 3: Проверка и запуск

1. Убедитесь, что атрибут `collector.id` действительно попадает в спаны (можно временно добавить `stdout` sink для отладки).
2. Запустите Data Prepper с этой конфигурацией.
3. Проверьте в OpenSearch, что данные попадают в разные индексы: `traces-collector-a-*` и `traces-collector-b-*`.

---

## Альтернатива: Использование одного pipeline с несколькими sink'ами и условиями

Если вы не хотите использовать вложенные pipeline'ы, можно использовать **условные sink'ы** (начиная с Data Prepper 2.x):

```yaml
traces-pipeline:
  source:
    otel_trace_source:
      ssl: false
  sink:
    - opensearch:
        hosts: ["https://opensearch:9200"]
        index: "traces-collector-a-%{yyyy.MM.dd}"
        condition: "/attributes/collector.id == 'collector-a'"
    - opensearch:
        hosts: ["https://opensearch:9200"]
        index: "traces-collector-b-%{yyyy.MM.dd}"
        condition: "/attributes/collector.id == 'collector-b'"
```

> ✅ Это проще и эффективнее, если у вас не слишком много условий.

---

## Полезные советы

- Убедитесь, что атрибут называется именно так, как вы его используете в условии (`/attributes/collector.id`).
- Используйте `stdout` sink для отладки:
  ```yaml
  sink:
    - stdout:
        condition: "/attributes/collector.id == 'collector-a'"
  ```
- Если атрибут может отсутствовать, добавьте условие на его наличие:  
  `condition: "has(/attributes/collector.id) && /attributes/collector.id == 'collector-a'"`

---

Если у тебя версия Data Prepper < 2.0 — маршрутизация через `pipeline`-ы обязательна. В 2.0+ можно использовать условия прямо в sink'ах.

Нужна помощь с конкретной версией или примером конфига под твой случай? Напиши!
