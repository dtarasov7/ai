Коротко:
- Реплики: задавайте number_of_replicas: 0 прямо в sink opensearch Data Prepper — это поддерживается в v2.0.1 и перекрывает значение в шаблоне. 
- Ретеншн: для индексов трасс в v2.0.1 встроенная политика создаётся автоматически (raw-span-policy) и делает только rollover (24h или 50gb) — удаления старых индексов нет. Ретеншн по сроку настраивается через ISM в самом OpenSearch 2.16 (добавить/изменить политику для otel-v1-apm-span-*). Параметр ism_policy_file в Data Prepper работает только для index_type: custom, то есть не для стандартных индексов трасс. 

Что поставить в pipelines.yaml (Data Prepper 2.0.1)
- Для сырых спанов:
```yaml
otel-trace-raw-pipeline:
  source:
    otel_trace_source: {}
  processor:
    - otel_trace: {}
  sink:
    - opensearch:
        hosts: ["https://opensearch:9200"]
        index_type: "trace-analytics-raw"      # создаёт otel-v1-apm-span-*
        number_of_replicas: 0                  # кластер из одного узла
        username: "admin"
        password: "admin"
        insecure: true
```
- Для service map (по желанию):
```yaml
  sink:
    - opensearch:
        index_type: "trace-analytics-service-map"  # otel-v1-apm-service-map-*
        number_of_replicas: 0
```
Поля index_type и number_of_replicas поддерживаются в 2.0.1; number_of_replicas перекрывает настройку в шаблоне индекса. 

Как задать глубину хранения (ISM в OpenSearch 2.16)
Вариант 1 — остаться на «стандартных» индексах трасс
- Это безопасно для Observability/Trace Analytics (дашборды ожидают otel-v1-apm-span/…); custom-индексы могут пропасть из дашбордов. 
- Создайте/обновите политику ISM с удалением старых индексов и примените её к otel-v1-apm-span-*.

Пример политики: удалить индексы старше 30 дней (можно оставить rollover по умолчанию от raw-span-policy или перенести его в свою политику):
```json
{
  "policy": {
    "policy_id": "otel-span-retention-30d",
    "description": "Rollover и удаление старых индексов спанов",
    "default_state": "hot",
    "states": [
      {
        "name": "hot",
        "actions": [
          { "rollover": { "min_index_age": "24h", "min_size": "50gb" } }
        ],
        "transitions": [
          { "state_name": "delete", "conditions": { "min_index_age": "30d" } }
        ]
      },
      { "name": "delete", "actions": [ { "delete": {} } ] }
    ],
    "ism_template": [
      { "index_patterns": ["otel-v1-apm-span-*"], "priority": 0 }
    ]
  }
}
```
Применение (OpenSearch 2.16 ISM API):
- Создать или обновить политику:
  PUT _plugins/_ism/policies/otel-span-retention-30d
- Привязать к индексам (если уже есть другая политика — используйте change_policy):
  POST otel-v1-apm-span-*/_plugins/_ism/change_policy
  { "policy_id": "otel-span-retention-30d" }

Документация ISM API (2.16) и пример политик: создание/изменение политики, transitions c min_index_age, delete. 

Замечания по версиям и ограничениям
- Data Prepper 2.0.1:
  - index_type для трасс: trace-analytics-raw и trace-analytics-service-map. Для них у Data Prepper встроены шаблоны/политики; ism_policy_file из sink игнорируется — он применяется только для index_type: custom. 
  - Встроенная raw-span-policy делает rollover (обычно 24h/50gb) и не удаляет индексы — поэтому ретеншн по сроку задаём через ISM в OpenSearch. 
- OpenSearch 2.16:
  - ISM доступен через _plugins/_ism; изменение политики на существующих индексах делается через change_policy/update managed index policy. 
- Если всё-таки используете собственные шаблоны (index_type: custom), убедитесь, что:
  - Указан rollover_alias для спанов ("otel-v1-apm-span"), иначе rollover будет падать. 
  - Понимаете, что Observability может не показать такие индексы без донастройки. 

Как проверить
- Реплики:
  GET otel-v1-apm-span-000001/_settings
  => "index.number_of_replicas": "0" 
- Привязка ISM:
  GET _plugins/_ism/explain/otel-v1-apm-span-000001
  — увидите policy_id и текущий state. 

Нужно пример под ваш срок хранения (например, 7/14/90 дней) или сделать политику и для service-map?
