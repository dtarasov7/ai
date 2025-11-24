### Настройка глубины хранения индексов с трейсами (Data Prepper v2.01 и OpenSearch v2.16)

Глубина хранения индексов с трейсами (т.е. период хранения данных, после которого индексы удаляются) настраивается с помощью механизма **Index State Management (ISM)** в OpenSearch. ISM позволяет автоматически управлять жизненным циклом индексов, включая удаление старых данных на основе возраста индекса (например, удаление через 30 дней). Data Prepper интегрируется с этим через конфигурацию sink'а `opensearch`, где вы можете указать файл с политикой ISM.

В Trace Analytics (для трейсов) Data Prepper использует специальные индексы, такие как:
- `otel-v1-apm-span` (для обработанных спанов трейсов).
- `otel-v1-apm-service-map` (для карты сервисов).

Эти индексы создаются автоматически при ingest'е данных через пайплайны вроде `raw-trace-pipeline` или `service-map-pipeline`. Для ролловера (ежедневных индексов) паттерн может быть `otel-v1-apm-span-*`.

#### Шаг 1: Создание политики ISM для retention
Создайте JSON-файл с политикой ISM (например, `retention_policy.json`). Политика начинается с состояния "hot" и переходит в "delete" после указанного периода (например, 30 дней). Это удалит индекс автоматически.

Пример JSON для удаления индекса через 30 дней (адаптировано для трейс-индексов):
```json
{
  "policy": {
    "description": "Удаление трейс-индексов через 30 дней",
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
        ],
        "transitions": []
      }
    ],
    "ism_template": {
      "index_patterns": ["otel-v1-apm-span-*", "otel-v1-apm-service-map-*"],
      "priority": 100
    }
  }
}
```
- **Объяснение**:
  - `default_state: "hot"`: Начальное состояние для новых индексов.
  - `min_index_age: "30d"`: Условие перехода — индекс старше 30 дней (можно изменить на "7d" для недели, "90d" для 3 месяцев и т.д.).
  - `ism_template.index_patterns`: Автоматически применяет политику к новым индексам, соответствующим паттерну (для трейсов). `priority` решает конфликты, если несколько шаблонов.
  - `delete`: Действие по удалению индекса.

Чтобы применить политику:
- **Автоматически для новых индексов**: Используйте `ism_template` в JSON (как выше). Загрузите политику в OpenSearch через API:
  ```
  PUT _plugins/_ism/policies/my_retention_policy
  { ... содержимое JSON ... }
  ```
- **Для существующих индексов**: Прикрепите вручную через API OpenSearch Dashboards или curl:
  ```
  POST otel-v1-apm-span-*/_ism/policies/my_retention_policy
  ```
- Проверьте применение:
  ```
  GET _plugins/_ism/explain/otel-v1-apm-span-*?pretty
  ```
ISM проверяет условия каждые 5 минут по умолчанию (настраивается в `plugins.index_state_management.job_interval` в `opensearch.yml`).

#### Шаг 2: Интеграция с Data Prepper
В конфигурации пайплайна Data Prepper (файл `pipelines.yaml`) укажите путь к файлу политики в секции `opensearch` sink. Это применит ISM при создании индекса.

Пример конфигурации для `raw-trace-pipeline` (для трейсов):
```yaml
raw-trace-pipeline:
  source:
    otel_trace_source:  # Или ваш source для трейсов
      ...
  processor:
    - otel_traces:
        ...
  sink:
    - opensearch:
        hosts: ["https://localhost:9200"]  # Ваш OpenSearch кластер
        username: "admin"
        password: "admin"  # Или используйте AWS credentials для Amazon OpenSearch
        index_type: trace-analytics-raw  # Для трейс-спанов
        # Настройки для retention
        ism_policy_file: "/path/to/retention_policy.json"  # Путь к JSON-файлу ISM
        # Дополнительно: шаблон индекса, если нужно
        template_file: "/path/to/otel-v1-apm-span-index-template.json"  # Опционально, для mappings
```
- `index_type: trace-analytics-raw`: Указывает, что это трейсы; Data Prepper автоматически использует индекс `otel-v1-apm-span`.
- `ism_policy_file`: Применяет вашу политику ISM при первом создании индекса. Если политика уже существует в OpenSearch, она будет использована.
- Перезапустите Data Prepper после изменений: `./run.sh --pipeline-config pipelines.yaml --config data-prepper-config.yaml`.

Если вы используете `service-map-pipeline`, замените `index_type` на `trace-analytics-service-map`.

**Примечание**: В версиях 2.01 (Data Prepper) и 2.16 (OpenSearch) ISM полностью поддерживается. Если индексы уже существуют, примените политику вручную. Для ролловера (ежедневных индексов) добавьте в шаблон индекса `rollover_alias: otel-v1-apm-span` для автоматического ролловера по размеру/возрасту.

### Указание отсутствия реплик для индексов (кластер из одного узла)

В кластере из одного узла реплики не нужны (и могут вызвать ошибки), поэтому установите `number_of_replicas: 0` в настройках индекса. Это делается в конфигурации `opensearch` sink в Data Prepper — при создании индекса эта настройка переопределит дефолт (который обычно 1).

#### Шаг 1: Настройка в Data Prepper
В `pipelines.yaml` добавьте `number_of_replicas: 0` в sink. Это применится к трейс-индексам.

Пример для `raw-trace-pipeline`:
```yaml
raw-trace-pipeline:
  source:
    ...
  processor:
    ...
  sink:
    - opensearch:
        hosts: ["https://localhost:9200"]
        username: "admin"
        password: "admin"
        index_type: trace-analytics-raw
        # Настройки для single-node кластера
        number_of_shards: 1  # Опционально: 1 первичный шард для простоты
        number_of_replicas: 0  # Нет реплик — идеально для одного узла
        # Retention, как выше
        ism_policy_file: "/path/to/retention_policy.json"
```
- `number_of_replicas: 0`: Устанавливает 0 реплик-шардов. Для multi-node кластера это было бы 1 или больше.
- `number_of_shards: 1`: Рекомендуется для single-node, чтобы избежать overhead (по умолчанию может быть 5).

#### Шаг 2: Проверка и применение в OpenSearch
- После ingest'а данных проверьте настройки индекса:
  ```
  GET otel-v1-apm-span-*/_settings?pretty
  ```
  В ответе должно быть `"number_of_replicas": "0"`.

- Если индекс уже создан с репликами, обновите настройки динамически (для существующих индексов):
  ```
  PUT otel-v1-apm-span-*/_settings
  {
    "index": {
      "number_of_replicas": 0
    }
  }
  ```

- В `opensearch.yml` для single-node кластера добавьте `discovery.type: single-node`, чтобы OpenSearch не ожидал реплик.

**Примечание**: Эти настройки переопределяют значения в шаблонах индексов (если используются `template_file`). Для production мониторьте дисковое пространство, так как без реплик нет redundancy. Если нужно, протестируйте на staging-кластере.

Если возникнут ошибки (например, с версиями), проверьте логи Data Prepper (`data-prepper.log`) или OpenSearch. Для более детальной помощи укажите вашу текущую конфигурацию пайплайна.
