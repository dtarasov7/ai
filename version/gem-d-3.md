Конечно, вот готовый JSON для дашборда Grafana 11, который включает все ваши требования, а также подробное описание каждой его части.

### JSON-модель дашборда для импорта

Скопируйте этот код и вставьте его в Grafana через меню "Dashboards" -> "Import" -> "Paste JSON".

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
  "__requires": [
    {
      "type": "grafana",
      "id": "grafana",
      "name": "Grafana",
      "version": "10.0.0"
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
  "panels": [
    {
      "id": 1,
      "gridPos": {
        "h": 12,
        "w": 24,
        "x": 0,
        "y": 0
      },
      "type": "table",
      "title": "Текущие версии ПО",
      "description": "Отображает текущую и предыдущую версии для каждого приложения на каждом узле, а также время последней смены версии.",
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "pluginVersion": "11.0.0",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "refId": "A",
          "expr": "app_version_info{nodename=~\"$nodename\", appname=~\"$appname\"} * on(nodename, appname) group_left() app_version_change_time_seconds",
          "instant": true,
          "format": "table",
          "legendFormat": ""
        }
      ],
      "transformations": [
        {
          "id": "organize",
          "options": {
            "excludeByName": {
              "Time": true,
              "__name__": true,
              "job": true,
              "instance": true
            },
            "indexByName": {
              "nodename": 0,
              "appname": 1,
              "version": 2,
              "prev_version": 3,
              "Value": 4
            },
            "renameByName": {
              "Value": "Время смены версии",
              "appname": "Приложение",
              "nodename": "Узел",
              "prev_version": "Пред. версия",
              "version": "Текущая версия"
            }
          }
        }
      ],
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
          },
          "custom": {
            "align": "auto",
            "displayMode": "auto",
            "filterable": true
          }
        },
        "overrides": [
          {
            "matcher": {
              "id": "byName",
              "options": "Время смены версии"
            },
            "properties": [
              {
                "id": "unit",
                "value": "time:YYYY-MM-DD HH:mm:ss"
              }
            ]
          }
        ]
      }
    },
    {
      "id": 2,
      "gridPos": {
        "h": 12,
        "w": 24,
        "x": 0,
        "y": 12
      },
      "type": "timeseries",
      "title": "История смены версий ПО",
      "description": "График показывает изменение версий ПО во времени. Версия представлена в числовом формате (например, 1.22.1 -> 1022001). Резкие скачки на графике соответствуют обновлениям.",
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "pluginVersion": "11.0.0",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "refId": "A",
          "expr": "app_version_numeric{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "legendFormat": "{{nodename}} - {{appname}}",
          "range": true,
          "instant": false
        }
      ],
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisBorderShow": false,
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 0,
            "gradientMode": "none",
            "hideFrom": {
              "legend": false,
              "tooltip": false,
              "viz": false
            },
            "insertNulls": false,
            "lineInterpolation": "stepAfter",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "auto",
            "spanNulls": false,
            "stacking": {
              "group": "A",
              "mode": "none"
            },
            "thresholdsStyle": {
              "mode": "off"
            }
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
          },
          "unit": "short"
        },
        "overrides": []
      }
    }
  ],
  "refresh": "1m",
  "schemaVersion": 39,
  "tags": [
    "versions",
    "devops"
  ],
  "templating": {
    "list": [
      {
        "type": "datasource",
        "name": "DS_PROMETHEUS",
        "label": "Datasource",
        "query": "prometheus",
        "multi": false,
        "includeAll": false,
        "refresh": 1,
        "options": [],
        "current": {},
        "hide": 0
      },
      {
        "current": {
          "selected": false,
          "text": "All",
          "value": "$__all"
        },
        "datasource": {
          "type": "prometheus",
          "uid": "${DS_PROMETHEUS}"
        },
        "definition": "label_values(app_version_info, nodename)",
        "hide": 0,
        "includeAll": true,
        "multi": true,
        "name": "nodename",
        "options": [],
        "query": {
          "query": "label_values(app_version_info, nodename)",
          "refId": "Prometheus-nodename-Variable-Query"
        },
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
        "sort": 1,
        "type": "query"
      },
      {
        "current": {
          "selected": false,
          "text": "All",
          "value": "$__all"
        },
        "datasource": {
          "type": "prometheus",
          "uid": "${DS_PROMETHEUS}"
        },
        "definition": "label_values(app_version_info{nodename=~\"$nodename\"}, appname)",
        "hide": 0,
        "includeAll": true,
        "multi": true,
        "name": "appname",
        "options": [],
        "query": {
          "query": "label_values(app_version_info{nodename=~\"$nodename\"}, appname)",
          "refId": "Prometheus-appname-Variable-Query"
        },
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
        "sort": 1,
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
  "title": "Мониторинг версий ПО",
  "uid": "app-version-dashboard-v2",
  "version": 1,
  "weekStart": ""
}
```

---

### Описание дашборда и его компонентов

Этот дашборд создан для наглядного отображения информации о версиях ПО, собранной вашим экспортером.

#### 1. Переменные (фильтры)

Вверху дашборда вы увидите три выпадающих списка для фильтрации данных:

*   **Datasource**: Позволяет выбрать ваш источник данных Prometheus. Это делает дашборд переносимым между разными окружениями.
*   **nodename**: Автоматически заполняется списком всех узлов (`nodename`), с которых приходят метрики. Можно выбрать один, несколько или все узлы.
*   **appname**: Список приложений. Он зависит от выбранного `nodename`, то есть показывает только те приложения, которые есть на выбранных узлах.

#### 2. Панель 1: Таблица "Текущие версии ПО"

Эта панель показывает сводную информацию о текущем состоянии версий в удобном табличном виде.

*   **Тип панели**: `Table`.
*   **Запрос PromQL**:
    ```promql
    app_version_info{nodename=~"$nodename", appname=~"$appname"} * on(nodename, appname) group_left() app_version_change_time_seconds
    ```
    *   **Как это работает**: Запрос хитроумно объединяет две метрики. Он берет `app_version_info`, которая содержит все текстовые метки (`version`, `prev_version`), и "умножает" ее на `app_version_change_time_seconds` по общим меткам `nodename` и `appname`. Так как значение `app_version_info` всегда `1`, результатом операции становится метрика со всеми метками из `app_version_info` и значением (временем смены) из `app_version_change_time_seconds`.
*   **Ключевые настройки**:
    *   **Запрос в режиме "Instant"**: Нам нужен только последний срез данных, а не график.
    *   **Transformations -> Organize fields**: Эта трансформация используется, чтобы переименовать технические названия полей (`nodename`, `Value`) в человекочитаемые (`Узел`, `Время смены версии`) и скрыть ненужные системные метки.
    *   **Field Overrides**: Для колонки "Время смены версии" настроено специальное отображение. Grafana автоматически преобразует Unix timestamp (число секунд) в понятную дату и время (например, `2024-05-21 10:30:00`).

#### 3. Панель 2: График "История смены версий ПО"

Эта панель визуализирует, как версии приложений менялись с течением времени.

*   **Тип панели**: `Time series`.
*   **Запрос PromQL**:
    ```promql
    app_version_numeric{nodename=~"$nodename", appname=~"$appname"}
    ```
    *   **Как это работает**: Это простой запрос, который извлекает историю изменений числовой метрики `app_version_numeric` для выбранных фильтров.
*   **Ключевые настройки**:
    *   **Легенда**: Настроена для отображения в формате `{{nodename}} - {{appname}}`, чтобы было сразу понятно, какой график к какому приложению относится.
    *   **Line interpolation -> `Step after`**: Это **самая важная** настройка для такого графика. Она заставляет Grafana рисовать "ступеньки" вместо плавных линий. Это визуально корректно отражает тот факт, что версия меняется мгновенно в определенный момент времени, а не постепенно.
    *   **Описание**: В описание панели добавлено напоминание о том, что по оси Y отложено числовое представление версии, чтобы у пользователей не возникало вопросов.

Этот дашборд предоставляет всю необходимую информацию для отслеживания обновлений ПО в вашей инфраструктуре и может быть легко расширен панелями для мониторинга самого сборщика (например, график для `app_version_collector_duration_seconds` или стат-панель для `app_version_collector_success`).
