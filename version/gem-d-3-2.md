Отличное и интересное задание! Использование info-метрик и объединение данных из разных метрик — это классическая задача для Grafana.

Вот готовый JSON-код дашборда для Grafana 11. Ниже я подробно объясню, как он работает и как его импортировать.

### JSON-код дашборда

Скопируйте весь этот код и сохраните его в файл, например, `versions-dashboard.json`.

```json
{
  "__inputs": [
    {
      "name": "DS_PROMETHEUS",
      "label": "Prometheus",
      "description": "",
      "type": "datasource",
      "pluginId": "prometheus",
      "pluginName": "Prometheus"
    }
  ],
  "__elements": {},
  "__requires": [
    {
      "type": "grafana",
      "id": "grafana",
      "name": "Grafana",
      "version": "10.0.0"
    },
    {
      "type": "panel",
      "id": "table",
      "name": "Table",
      "version": ""
    },
    {
      "type": "datasource",
      "id": "prometheus",
      "name": "Prometheus",
      "version": "1.0.0"
    }
  ],
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": {
          "type": "grafana",
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
  "fiscalYearStartMonth": 0,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "liveNow": false,
  "panels": [
    {
      "datasource": {
        "type": "prometheus",
        "uid": "${datasource}"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [],
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
              "options": "Дата смены версии"
            },
            "properties": [
              {
                "id": "unit",
                "value": "s"
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "Дата сканирования"
            },
            "properties": [
              {
                "id": "unit",
                "value": "s"
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
      "id": 1,
      "options": {
        "footer": {
          "countRows": false,
          "fields": "",
          "reducer": [
            "sum"
          ],
          "show": false
        },
        "showHeader": true
      },
      "pluginVersion": "11.0.0",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "expr": "app_version_info{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "instant": true,
          "legendFormat": "info",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "expr": "app_version_change_time_seconds{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "hide": false,
          "instant": true,
          "legendFormat": "change_time",
          "refId": "B"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "expr": "app_version_scrape_timestamp_seconds{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "hide": false,
          "instant": true,
          "legendFormat": "scrape_time",
          "refId": "C"
        }
      ],
      "title": "Версии ПО",
      "transformations": [
        {
          "id": "merge",
          "options": {}
        },
        {
          "id": "labelsToFields",
          "options": {
            "labels": [
              "version",
              "prev_version"
            ]
          }
        },
        {
          "id": "organize",
          "options": {
            "excludeByName": {
              "Time": true,
              "Value #A": true
            },
            "indexByName": {
              "Time": 0,
              "Value #A": 7,
              "Value #B": 5,
              "Value #C": 6,
              "appname": 2,
              "nodename": 1,
              "prev_version": 4,
              "version": 3
            },
            "renameByName": {
              "Value #B": "Дата смены версии",
              "Value #C": "Дата сканирования",
              "appname": "Приложение",
              "nodename": "Сервер",
              "prev_version": "Предыдущая версия",
              "version": "Текущая версия"
            }
          }
        }
      ],
      "type": "table"
    }
  ],
  "refresh": "5m",
  "schemaVersion": 39,
  "style": "dark",
  "tags": [],
  "templating": {
    "list": [
      {
        "current": {
          "selected": false,
          "text": "Prometheus",
          "value": "Prometheus"
        },
        "hide": 0,
        "includeAll": false,
        "multi": false,
        "name": "datasource",
        "options": [],
        "query": "prometheus",
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
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
          "uid": "${datasource}"
        },
        "definition": "label_values(app_version_info, nodename)",
        "hide": 0,
        "includeAll": true,
        "multi": true,
        "name": "nodename",
        "options": [],
        "query": {
          "query": "label_values(app_version_info, nodename)",
          "refId": "StandardVariableQuery"
        },
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
          "uid": "${datasource}"
        },
        "definition": "label_values(app_version_info{nodename=~\"$nodename\"}, appname)",
        "hide": 0,
        "includeAll": true,
        "multi": true,
        "name": "appname",
        "options": [],
        "query": {
          "query": "label_values(app_version_info{nodename=~\"$nodename\"}, appname)",
          "refId": "StandardVariableQuery"
        },
        "refresh": 2,
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
  "timepicker": {},
  "timezone": "browser",
  "title": "Application Versions Dashboard",
  "uid": "my-app-versions-dashboard",
  "version": 1,
  "weekStart": ""
}
```

---

### Как импортировать дашборд в Grafana

1.  В интерфейсе Grafana наведите курсор на иконку дашбордов (четыре квадрата) в левой панели.
2.  Нажмите на кнопку **"+ New"** -> **"Import"**.
3.  Нажмите на кнопку **"Upload dashboard JSON file"** и выберите сохраненный файл `versions-dashboard.json`, либо просто вставьте скопированный JSON-код в текстовое поле.
4.  Нажмите **"Load"**.
5.  На следующей странице Grafana попросит вас выбрать источник данных Prometheus. Выберите ваш настроенный Prometheus из выпадающего списка.
6.  Нажмите **"Import"**.

### Как работает дашборд

#### 1. Переменные (Variables)

Вверху дашборда вы увидите три выпадающих списка:

*   **`datasource`**: Позволяет выбрать, какой источник данных Prometheus использовать.
*   **`nodename`**: Автоматически заполняется всеми значениями метки `nodename` из метрики `app_version_info`. Можно выбрать один, несколько или все серверы.
*   **`appname`**: Список приложений. Он динамически фильтруется на основе выбранного `nodename`. Если вы выберете `srv-1`, то в этом списке будут только приложения, работающие на `srv-1`.

#### 2. Панель "Таблица" (Table Panel)

Это основная и единственная панель на дашборде. Она использует мощный механизм трансформаций (Transformations) для объединения данных из трех разных метрик в одну красивую таблицу.

##### **Запросы (Queries):**

Панель делает три отдельных запроса к Prometheus:

*   **Запрос A**: `app_version_info{nodename=~"$nodename", appname=~"$appname"}`
    *   Получает основную информацию: `nodename`, `appname`, а также метки `version` и `prev_version`.
*   **Запрос B**: `app_version_change_time_seconds{nodename=~"$nodename", appname=~"$appname"}`
    *   Получает значение времени последнего изменения версии.
*   **Запрос C**: `app_version_scrape_timestamp_seconds{nodename=~"$nodename", appname=~"$appname"}`
    *   Получает значение времени последнего сканирования.

##### **Трансформации (Transformations):**

Данные из этих трех запросов затем обрабатываются по шагам:

1.  **Merge**: Эта трансформация объединяет результаты всех трех запросов в одну большую таблицу. Она автоматически находит общие метки (`nodename`, `appname`) и использует их как ключ для объединения.
2.  **Labels to fields**: Метки `version` и `prev_version` из первого запроса превращаются в полноценные колонки таблицы.
3.  **Organize fields**: Этот шаг наводит порядок:
    *   Переименовывает колонки в понятные русские названия ("Сервер", "Приложение", "Текущая версия" и т.д.).
    *   Скрывает ненужные технические поля (например, `Time`, `Value #A`).
    *   Расставляет колонки в нужном порядке.

##### **Настройка полей (Field Overrides):**

Две колонки содержат время в формате Unix Timestamp (секунды). Чтобы Grafana показывала их как обычную дату и время, используются переопределения (Overrides):

*   Для колонок "Дата смены версии" и "Дата сканирования" установлен **Unit** -> **Date & Time** -> **From Now**. Grafana автоматически поймет, что это Unix-секунды, и отформатирует их в читаемый вид (например, `2024-05-21 14:30:00`).

В итоге вы получите именно ту таблицу, которую запрашивали, с возможностью гибкой фильтрации по серверам и приложениям.