Для управления глубиной хранения трейсов и настройки реплик в OpenSearch с Data Prepper v2.01, вам нужно использовать **Index State Management (ISM)** политики и шаблоны индексов.

## Настройка глубины хранения трейсов

### Вариант 1: Через ISM политику

Создайте ISM политику для автоматического удаления старых индексов:

```json
PUT _plugins/_ism/policies/traces-retention-policy
{
  "policy": {
    "description": "Retention policy for trace indices",
    "default_state": "hot",
    "states": [
      {
        "name": "hot",
        "actions": [],
        "transitions": [
          {
            "state_name": "delete",
            "conditions": {
              "min_index_age": "7d"
            }
          }
        ]
      },
      {
        "name": "delete",
        "actions": [
          {
            "delete": {}
          }
        ]
      }
    ],
    "ism_template": [
      {
        "index_patterns": ["otel-v1-apm-span-*"],
        "priority": 100
      }
    ]
  }
}
```

### Вариант 2: Через Data Prepper конфигурацию

В `data-prepper-config.yaml` можно настроить ротацию индексов:

```yaml
trace-pipeline:
  source:
    otel_trace_source:
  processor:
    - otel_trace_raw:
  sink:
    - opensearch:
        hosts: ["https://opensearch:9200"]
        index_type: "trace-analytics-raw"
        template_type: "v1"
        index: "otel-v1-apm-span-%{yyyy.MM.dd}"
        max_retries: 20
```

## Настройка отсутствия реплик

### Через шаблон индексов (рекомендуется)

Создайте или обновите шаблон индексов для трейсов:

```json
PUT _index_template/otel-traces-template
{
  "index_patterns": ["otel-v1-apm-span-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0,
      "index.codec": "best_compression"
    }
  },
  "priority": 200
}
```

### Для уже существующих индексов

Если индексы уже созданы:

```json
PUT otel-v1-apm-span-*/_settings
{
  "index": {
    "number_of_replicas": 0
  }
}
```

### Глобальная настройка для кластера

Для кластера из одного узла можно установить значение по умолчанию в `opensearch.yml`:

```yaml
cluster.routing.allocation.enable: all
index.number_of_replicas: 0
```

## Комплексная конфигурация Data Prepper

Пример полной конфигурации `pipelines.yaml`:

```yaml
trace-pipeline:
  source:
    otel_trace_source:
      ssl: false
      port: 21890
  processor:
    - otel_trace_raw:
  sink:
    - opensearch:
        hosts: ["https://opensearch-node:9200"]
        username: "admin"
        password: "admin"
        index_type: "trace-analytics-raw"
        index: "otel-v1-apm-span-%{yyyy.MM.dd}"
        template_type: "v1"
        max_retries: 20
        insecure: true
        dlq_file: "/usr/share/data-prepper/dlq/traces-dlq"
```

## Проверка настроек

```bash
# Проверить настройки индекса
GET otel-v1-apm-span-*/_settings

# Проверить применённую ISM политику
GET _plugins/_ism/explain/otel-v1-apm-span-*

# Список всех индексов трейсов
GET _cat/indices/otel-v1-apm-span-*?v
```

Глубину хранения (`7d` в примере) можно изменить на нужное значение: `1d`, `30d`, `90d` и т.д.
