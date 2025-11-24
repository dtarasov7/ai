Отвечу на оба вопроса с конкретными решениями для Grafana.

## 1. Таблица изменений версий с предыдущей версией

### Подход через PromQL (детектирование изменений)

**Запрос для Grafana (единым выражением):**
```promql
# Найти изменения версии
(app{hostname=~"$hostname", appname=~"$appname"} 
  unless on(hostname, appname, version) 
  app{hostname=~"$hostname", appname=~"$appname"} offset 5m)
* on(hostname, appname) group_left(prev_version) 
label_replace(
  app{hostname=~"$hostname", appname=~"$appname"} offset 5m,
  "prev_version", "$1", "version", "(.*)"
)
```

**Настройка панели Table в Grafana:**
1. Создайте панель **Table**
2. Query options:
   - Min step: 1m
   - Format: **Time series** (не Instant!)
   - Relative time: 7d (или нужный период)
3. Transformations (по порядку):
   - **Reduce** → Mode: Last, Fields: All numeric fields
   - **Filter by value** → Field: Value, Match: Greater, Value: 0.9
   - **Organize fields** → Показать: Time, hostname, appname, version, prev_version
   - **Sort by** → Field: Time, Reverse: true

### Альтернативный подход (более надежный для редких изменений)

**Запрос A:**
```promql
changes_over_time(
  app{hostname=~"$hostname", appname=~"$appname"}[1h]
) > 0
```

**Запрос B (для предыдущей версии):**
```promql
label_replace(
  app{hostname=~"$hostname", appname=~"$appname"} offset 1h,
  "prev_version", "$1", "version", "(.*)"
)
```

В Transformations:
- **Merge** → объединить A и B
- **Group by** → Fields: hostname, appname, version, prev_version; Calculation: First non-null

## 2. История изменений версий во времени

### Вариант A: State Timeline (самый наглядный)

**Панель:** State Timeline

**Запрос:**
```promql
app{hostname="$hostname", appname="$appname"}
```

**Настройки панели:**
- Legend options → Display name: `{{version}}`
- State timeline → Show values: **Always** или **Auto**
- State timeline → Row height: 0.9
- State timeline → Line width: 0
- Value mappings:
  - Value: 1 → Text: `{{__field.labels.version}}`
  - Value: 0 → Text: (пусто)

Получите цветные полосы, где каждый цвет = версия, переходы видны четко.

### Вариант B: Несколько хостов/приложений одновременно

**Панель:** State Timeline

**Запрос:**
```promql
sum by (hostname, appname, version) (
  app{hostname=~"$hostname", appname=~"$appname"}
)
```

**Настройки:**
- Transform → **Partition by values** → Fields: hostname, appname
- Legend: `{{hostname}} - {{appname}}: {{version}}`

### Вариант C: График с аннотациями изменений

**Основная панель:** Time series

**Запрос для графика (кодируем версию в число):**
```promql
label_replace(
  app{hostname="$hostname", appname="$appname"},
  "__tmp", "$1.$2.$3", "version", "([0-9]+)\\.([0-9]+)\\.([0-9]+)"
) * 1
```

**Annotations (аннотации на графике):**
1. Dashboard settings → Annotations → New annotation
2. Query:
```promql
changes_over_time(app{hostname="$hostname", appname="$appname"}[5m]) > 0
```
3. Настройки аннотации:
   - Text: `Version changed to {{version}}`
   - Tags: version-change

### Вариант D: Таблица с историей всех состояний

**Панель:** Table

**Запрос:**
```promql
app{hostname=~"$hostname", appname=~"$appname"}
```

**Transformations:**
- **Series to rows** → превратить временные ряды в строки
- **Organize fields** → оставить Time, hostname, appname, version
- **Filter data by values** → Value > 0
- **Sort by** → Time (descending)

Получите полную историю: когда какая версия была активна.

## Готовый пример дашборда

```json
{
  "panels": [
    {
      "title": "Version Changes Table",
      "type": "table",
      "targets": [
        {
          "expr": "(app unless on(hostname,appname,version) app offset 5m) * on(hostname,appname) group_left(prev_version) label_replace(app offset 5m, \"prev_version\", \"$1\", \"version\", \"(.*)\")",
          "format": "time_series"
        }
      ],
      "transformations": [
        {
          "id": "reduce",
          "options": {
            "reducers": ["last"]
          }
        },
        {
          "id": "filterFieldsByName",
          "options": {
            "include": {
              "pattern": "Time|hostname|appname|version|prev_version"
            }
          }
        }
      ]
    },
    {
      "title": "Version History Timeline",
      "type": "state-timeline",
      "targets": [
        {
          "expr": "app{hostname=\"$hostname\", appname=\"$appname\"}",
          "legendFormat": "{{version}}"
        }
      ],
      "options": {
        "showValue": "always",
        "rowHeight": 0.9
      }
    }
  ],
  "templating": {
    "list": [
      {
        "name": "hostname",
        "type": "query",
        "query": "label_values(app, hostname)"
      },
      {
        "name": "appname",
        "type": "query", 
        "query": "label_values(app, appname)"
      }
    ]
  }
}
```

## Советы по оптимизации

1. **Для больших периодов** (месяц+): используйте recording rules в Prometheus для предрасчета изменений
2. **Для real-time мониторинга**: настройте Alert на изменение версии
3. **Для детального анализа**: экспортируйте данные через API в ClickHouse/TimescaleDB

Выбирайте подход в зависимости от:
- Частоты изменений (редкие/частые)
- Количества хостов/приложений
- Нужной детализации истории
