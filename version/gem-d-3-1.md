Отличная задача! Создадим JSON дашборд для Grafana 11, который использует эти метрики.

Этот дашборд будет содержать:
1.  **Переменные**: `datasource`, `nodename`, `appname`.
2.  **Таблицу**: Отображающую текущую версию, предыдущую версию, дату смены версии и дату последнего сканирования для каждого приложения/узла.

**Логика запросов:**

*   **Текущая версия (string) / Предыдущая версия (string)**: Мы получим их из меток `version` и `prev_version` метрики `app_version_info`.
*   **Дата смены версии**: Получим значение метрики `app_version_change_time_seconds`, которое является Unix timestamp, и Grafana автоматически преобразует его в читаемый формат.
*   **Дата сканирования**: Получим значение метрики `app_version_scrape_timestamp_seconds`, также Unix timestamp.

---

### JSON Дашборда Grafana

Скопируйте этот JSON и импортируйте его в Grafana (Dashboards -> New -> Import -> Paste JSON).

```json
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": {
          "type": "datasource",
          "uid": "-- Grafana --"
        },
        "enable": true,
        "hide": true,
        "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts",
        "type": "dashboard"
      }
    ]
  },
  "editable": true,
  "gnetId": null,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "liveNow": false,
  "panels": [
    {
      "datasource": {
        "type": "prometheus",
        "uid": "$datasource"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [],
          "noValue": "N/A",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "red",
                "value": 80
              }
            ]
          }
        },
        "overrides": [
          {
            "matcher": {
              "id": "byName",
              "options": "version"
            },
            "properties": [
              {
                "id": "displayName",
                "value": "Текущая Версия"
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "prev_version"
            },
            "properties": [
              {
                "id": "displayName",
                "value": "Предыдущая Версия"
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "Value #B"
            },
            "properties": [
              {
                "id": "displayName",
                "value": "Дата Смены Версии"
              },
              {
                "id": "unit",
                "value": "dateTimeAsLocal"
              },
              {
                "id": "custom.displayMode",
                "value": "auto"
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "Value #C"
            },
            "properties": [
              {
                "id": "displayName",
                "value": "Дата Сканирования"
              },
              {
                "id": "unit",
                "value": "dateTimeAsLocal"
              },
              {
                "id": "custom.displayMode",
                "value": "auto"
              }
            ]
          }
        ]
      },
      "gridPos": {
        "h": 15,
        "w": 24,
        "x": 0,
        "y": 0
      },
      "id": 2,
      "options": {
        "cellOptions": {
          "type": "coloredtext"
        },
        "footer": {
          "reducer": [
            "sum"
          ],
          "show": false
        },
        "rowHeight": "auto",
        "showHeader": true,
        "sortBy": [
          {
            "desc": false,
            "displayName": "nodename"
          },
          {
            "desc": false,
            "displayName": "appname"
          }
        ],
        "viewMode": "table"
      },
      "pluginVersion": "11.0.0",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "$datasource"
          },
          "editorMode": "builder",
          "expr": "app_version_info{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "instant": true,
          "legendFormat": "App Info",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "$datasource"
          },
          "editorMode": "builder",
          "expr": "app_version_change_time_seconds{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "instant": true,
          "legendFormat": "Change Time",
          "refId": "B"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "$datasource"
          },
          "editorMode": "builder",
          "expr": "app_version_scrape_timestamp_seconds{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "instant": true,
          "legendFormat": "Scrape Time",
          "refId": "C"
        }
      ],
      "title": "Информация о Версиях ПО",
      "type": "table"
    }
  ],
  "schemaVersion": 39,
  "style": "dark",
  "tags": [
    "app_versioning"
  ],
  "templating": {
    "list": [
      {
        "current": {
          "text": "Prometheus",
          "value": "Prometheus"
        },
        "hide": 0,
        "label": "Datasource",
        "name": "datasource",
        "options": [],
        "query": "prometheus",
        "queryValue": "",
        "regex": "",
        "type": "datasource"
      },
      {
        "allValue": null,
        "current": {
          "selected": true,
          "text": "All",
          "value": "$__all"
        },
        "datasource": {
          "type": "prometheus",
          "uid": "$datasource"
        },
        "definition": "label_values(app_version_info, nodename)",
        "hide": 0,
        "includeAll": true,
        "multi": true,
        "name": "nodename",
        "options": [],
        "query": "label_values(app_version_info, nodename)",
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
        "sort": 0,
        "type": "query"
      },
      {
        "allValue": null,
        "current": {
          "selected": true,
          "text": "All",
          "value": "$__all"
        },
        "datasource": {
          "type": "prometheus",
          "uid": "$datasource"
        },
        "definition": "label_values(app_version_info{nodename=~\"$nodename\"}, appname)",
        "hide": 0,
        "includeAll": true,
        "multi": true,
        "name": "appname",
        "options": [],
        "query": "label_values(app_version_info{nodename=~\"$nodename\"}, appname)",
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
        "sort": 0,
        "type": "query"
      }
    ]
  },
  "time": {
    "from": "now-6h",
    "to": "now"
  },
  "timepicker": {
    "hidden": false,
    "refresh_intervals": [
      "5s",
      "10s",
      "30s",
      "1m",
      "2m",
      "5m",
      "10m",
      "15m",
      "30m",
      "1h",
      "2h",
      "1d"
    ],
    "time_options": [
      "5m",
      "15m",
      "30m",
      "1h",
      "2h",
      "4h",
      "12h",
      "1d",
      "2d",
      "7d",
      "30d"
    ]
  },
  "timezone": "",
  "title": "Версии ПО",
  "uid": "app_version_dashboard",
  "version": 1
}
```

---

### Пояснения к JSON:

1.  **`templating.list`**:
    *   **`datasource`**: Переменная для выбора вашего Prometheus datasource. По умолчанию `prometheus`.
    *   **`nodename`**: Заполняется уникальными значениями метки `nodename` из `app_version_info`. Поддерживает множественный выбор (`multi: true`) и опцию "All".
    *   **`appname`**: Заполняется уникальными значениями метки `appname` из `app_version_info`, фильтруясь по выбранным `nodename`. Также поддерживает множественный выбор и "All".

2.  **`panels.table`**:
    *   **`title`**: "Информация о Версиях ПО".
    *   **`datasource`**: Использует переменную `$datasource`.
    *   **`targets` (запросы Prometheus)**:
        *   **`refId: A`**: `app_version_info{nodename=~"$nodename", appname=~"$appname"}`
            *   Этот запрос возвращает все метки `nodename`, `appname`, `version`, `prev_version`. Grafana Table Panel автоматически отобразит их как столбцы.
        *   **`refId: B`**: `app_version_change_time_seconds{nodename=~"$nodename", appname=~"$appname"}`
            *   Возвращает время изменения версии.
        *   **`refId: C`**: `app_version_scrape_timestamp_seconds{nodename=~"$nodename", appname=~"$appname"}`
            *   Возвращает время последнего сканирования.
        *   Grafana умна и объединит строки из разных запросов по общим меткам (`nodename`, `appname`), создавая одну строку для каждой уникальной пары app/node.
    *   **`fieldConfig.overrides`**: Здесь мы настраиваем отображение столбцов:
        *   Переименовываем столбцы `version` в "Текущая Версия" и `prev_version` в "Предыдущая Версия".
        *   Переименовываем столбцы `Value #B` (значение из запроса B) в "Дата Смены Версии" и `Value #C` (значение из запроса C) в "Дата Сканирования".
        *   Для этих двух "датовых" столбцов мы устанавливаем `unit: "dateTimeAsLocal"`, чтобы они отображались как локальное время в читаемом формате.

### Как использовать:

1.  Убедитесь, что ваши метрики `app_version_info`, `app_version_change_time_seconds`, `app_version_scrape_timestamp_seconds` экспортируются в Prometheus.
2.  В Grafana перейдите в `Dashboards` -> `New` -> `Import`.
3.  Вставьте скопированный выше JSON в текстовое поле `Import via panel json`.
4.  Нажмите `Load`.
5.  Выберите ваш источник данных Prometheus для переменной `datasource`.
6.  Нажмите `Import`.

Дашборд будет создан, и вы сможете выбирать узлы и приложения, чтобы просматривать информацию о версиях.
