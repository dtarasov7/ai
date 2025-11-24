Для Data Prepper v2.01 и OpenSearch v2.16 настройка глубины хранения индексов с трейсами и указание отсутствия реплик выполняется следующим образом:

## Настройка глубины хранения индексов с трейсами (retention)

### 1. Создание ISM политики для автоматического удаления старых данных

Index State Management (ISM) позволяет автоматизировать административные операции с индексами на основе изменения возраста индекса, размера или количества документов. Используя ISM, вы можете определить политики для автоматической обработки ролловеров или удаления индексов. Например, можно настроить политику, которая удаляет индекс после установленного периода.

Создайте файл с политикой ISM (`retention_policy.json`):

```json
{
  "policy": {
    "description": "Удаление trace-индексов через 30 дней",
    "default_state": "hot",
    "states": [
      {
        "name": "hot",
        "actions": [],
        "transitions": [
          {
            "state_name": "delete",
            "conditions": {
              "min_index_age": "30d"
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
    "ism_template": {
      "index_patterns": ["otel-v1-apm-span-*", "otel-v1-apm-service-map-*"],
      "priority": 100
    }
  }
}
```

Блок `ism_template` с `index_patterns` автоматически применяет политику к новым индексам, соответствующим указанным паттернам.

### 2. Интеграция ISM политики в Data Prepper

В Data Prepper версии 2.01 поддерживается параметр `ism_policy_file` для автоматического создания ISM политики на сервере OpenSearch при настройке индекса.

В конфигурации пайплайна (`pipelines.yaml`) добавьте параметр `ism_policy_file`:

```yaml
raw-trace-pipeline:
  source:
    otel_trace_source:
      # Ваши настройки source
  processor:
    - otel_traces:
  sink:
    - opensearch:
        hosts: ["https://localhost:9200"]
        username: "admin"
        password: "admin"
        index_type: trace-analytics-raw
        # Путь к файлу с ISM политикой
        ism_policy_file: "/path/to/retention_policy.json"

service-map-pipeline:
  source:
    pipeline:
      name: "entry-pipeline"
  processor:
    - service_map:
  sink:
    - opensearch:
        hosts: ["https://localhost:9200"]
        username: "admin"
        password: "admin"
        index_type: trace-analytics-service-map
        ism_policy_file: "/path/to/retention_policy.json"
```

После применения политики к индексу, ISM создает задание, которое выполняется каждые 5 минут по умолчанию для выполнения действий политики, проверки условий и перехода индекса в различные состояния.

## Настройка количества реплик для single-node кластера

Для кластера из одного узла необходимо установить `number_of_replicas: 0`, так как реплики не могут быть размещены на том же узле, где находится primary shard.

### В конфигурации Data Prepper

Добавьте параметры `number_of_replicas` и `number_of_shards` в настройки sink:

```yaml
raw-trace-pipeline:
  source:
    otel_trace_source:
      # Настройки source
  processor:
    - otel_traces:
  sink:
    - opensearch:
        hosts: ["https://localhost:9200"]
        username: "admin"
        password: "admin"
        index_type: trace-analytics-raw
        # Настройки для single-node кластера
        number_of_replicas: 0
        number_of_shards: 1
        # ISM политика
        ism_policy_file: "/path/to/retention_policy.json"

service-map-pipeline:
  source:
    pipeline:
      name: "entry-pipeline"
  processor:
    - service_map:
  sink:
    - opensearch:
        hosts: ["https://localhost:9200"]
        username: "admin"
        password: "admin"
        index_type: trace-analytics-service-map
        number_of_replicas: 0
        number_of_shards: 1
        ism_policy_file: "/path/to/retention_policy.json"
```

### Дополнительные настройки OpenSearch

В файле `opensearch.yml` для single-node кластера добавьте:

```yaml
discovery.type: single-node
```

### Проверка настроек

После запуска Data Prepper проверьте:

1. **Настройки индекса:**
```bash
GET otel-v1-apm-span-*/_settings
```

Должно показать `"number_of_replicas": "0"`.

2. **Статус ISM политики:**
```bash
GET _plugins/_ism/explain/otel-v1-apm-span-*
```

3. **Для существующих индексов** обновите настройки реплик вручную:
```bash
PUT otel-v1-apm-span-*/_settings
{
  "index": {
    "number_of_replicas": 0
  }
}
```

## Важные замечания для версий 2.01 и 2.16

1. ISM политики не поддерживаются в Amazon OpenSearch Serverless, и любые связанные с ISM настройки не будут иметь эффекта - это касается только Serverless, для обычного OpenSearch 2.16 ISM работает полностью.

2. Для корректной работы rollover в ISM политике необходимо убедиться, что в настройках индекса указан `rollover_alias`.

3. Data Prepper 2.01 полностью поддерживает конфигурацию `ism_policy_file` для автоматического создания политик при инициализации индексов.
