Я помогу вам создать дашборд для отображения истории изменения версий ПО с использованием State timeline в Grafana v11 и Prometheus v2.31.Отлично! Я подготовлю для вас JSON дашборда с использованием State timeline панели для отображения истории изменения версий ПО.

## Решение для отображения истории версий в Grafana v11

Для вашего случая с метрикой `app{nodename="...", appname="...", version="..."}` я создам дашборд с использованием State timeline панели. State timeline visualization позволяет отображать изменения состояний во времени.

### Особенности реализации:

1. Необходимо использовать трансформацию "Grouping to matrix", которая доступна в Grafana 8.5 и выше (в v11 она точно есть)
2. State timeline panel показывает дискретные изменения состояний во времени, каждое поле или серия отображается как уникальная горизонтальная полоса
3. Для корректного отображения меток версий потребуется правильно настроить запрос Prometheus

### JSON дашборда:

```json
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": {
          "type": "prometheus",
          "uid": "$datasource"
        },
        "enable": true,
        "hide": true,
        "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts",
        "target": {
          "limit": 100,
          "matchAny": false,
          "tags": [],
          "type": "dashboard"
        },
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
      "datasource": {
        "type": "prometheus",
        "uid": "${datasource}"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "fillOpacity": 70,
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "insertNulls": false,
            "lineWidth": 0,
            "spanNulls": false
          },
          "mappings": [
            {
              "type": "value",
              "value": "null",
              "text": "N/A"
            }
          ],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          },
          "unit": "short"
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
                "value": "${__field.labels.version}"
              }
            ]
          }
        ]
      },
      "gridPos": {
        "h": 10,
        "w": 24,
        "x": 0,
        "y": 0
      },
      "id": 1,
      "options": {
        "alignValue": "center",
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "mergeValues": true,
        "rowHeight": 0.9,
        "showValue": "auto",
        "tooltip": {
          "mode": "single",
          "sort": "none"
        }
      },
      "pluginVersion": "11.0.0",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "editorMode": "code",
          "exemplar": false,
          "expr": "sum by(nodename, appname, version) (app{nodename=~\"$nodename\", appname=~\"$appname\"})",
          "format": "time_series",
          "instant": false,
          "interval": "",
          "legendFormat": "{{nodename}} - {{appname}} - v{{version}}",
          "range": true,
          "refId": "A"
        }
      ],
      "title": "История изменения версий ПО",
      "transformations": [
        {
          "id": "groupingToMatrix",
          "options": {
            "columnField": "version",
            "rowField": "nodename - appname",
            "valueField": "Value"
          }
        }
      ],
      "type": "state-timeline"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "${datasource}"
      },
      "fieldConfig": {
        "defaults": {
          "custom": {
            "align": "auto",
            "cellOptions": {
              "type": "auto"
            },
            "inspect": false
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": [
          {
            "matcher": {
              "id": "byName",
              "options": "Time"
            },
            "properties": [
              {
                "id": "custom.hidden",
                "value": true
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "Value"
            },
            "properties": [
              {
                "id": "custom.hidden",
                "value": true
              }
            ]
          }
        ]
      },
      "gridPos": {
        "h": 8,
        "w": 24,
        "x": 0,
        "y": 10
      },
      "id": 2,
      "options": {
        "showHeader": true,
        "cellHeight": "sm",
        "footer": {
          "reducer": ["sum"],
          "show": false
        }
      },
      "pluginVersion": "11.0.0",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "editorMode": "code",
          "exemplar": false,
          "expr": "app{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "format": "table",
          "instant": true,
          "interval": "",
          "legendFormat": "",
          "range": false,
          "refId": "A"
        }
      ],
      "title": "Текущие версии ПО",
      "transformations": [
        {
          "id": "organize",
          "options": {
            "excludeByName": {
              "Time": true,
              "Value": true,
              "__name__": true,
              "job": true,
              "instance": true
            },
            "indexByName": {
              "nodename": 0,
              "appname": 1,
              "version": 2
            },
            "renameByName": {
              "appname": "Приложение",
              "nodename": "Хост",
              "version": "Версия"
            }
          }
        }
      ],
      "type": "table"
    }
  ],
  "refresh": "30s",
  "schemaVersion": 39,
  "tags": ["monitoring", "versions"],
  "templating": {
    "list": [
      {
        "current": {
          "selected": false,
          "text": "Prometheus",
          "value": "prometheus_uid"
        },
        "hide": 0,
        "includeAll": false,
        "label": "Data Source",
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
        "allValue": ".*",
        "current": {
          "selected": true,
          "text": ["All"],
          "value": ["$__all"]
        },
        "datasource": {
          "type": "prometheus",
          "uid": "${datasource}"
        },
        "definition": "label_values(app, nodename)",
        "hide": 0,
        "includeAll": true,
        "label": "Хост",
        "multi": true,
        "name": "nodename",
        "options": [],
        "query": {
          "qryType": 1,
          "query": "label_values(app, nodename)",
          "refId": "PrometheusVariableQueryEditor-VariableQuery"
        },
        "refresh": 2,
        "regex": "",
        "skipUrlSync": false,
        "sort": 1,
        "type": "query"
      },
      {
        "allValue": ".*",
        "current": {
          "selected": true,
          "text": ["All"],
          "value": ["$__all"]
        },
        "datasource": {
          "type": "prometheus",
          "uid": "${datasource}"
        },
        "definition": "label_values(app{nodename=~\"$nodename\"}, appname)",
        "hide": 0,
        "includeAll": true,
        "label": "Приложение",
        "multi": true,
        "name": "appname",
        "options": [],
        "query": {
          "qryType": 1,
          "query": "label_values(app{nodename=~\"$nodename\"}, appname)",
          "refId": "PrometheusVariableQueryEditor-VariableQuery"
        },
        "refresh": 2,
        "regex": "",
        "skipUrlSync": false,
        "sort": 1,
        "type": "query"
      }
    ]
  },
  "time": {
    "from": "now-24h",
    "to": "now"
  },
  "timezone": "browser",
  "title": "Мониторинг версий ПО",
  "uid": "software-versions-timeline",
  "version": 1,
  "weekStart": ""
}
```

### Как использовать дашборд:

1. **Импортируйте JSON** в Grafana через меню Dashboards → Import
2. **Настройте datasource** - укажите правильный UID вашего Prometheus источника данных
3. **Проверьте имя метрики** - если ваша метрика называется не `app`, замените её во всех запросах

### Особенности панелей:

**Панель 1 - State Timeline:**
- Отображает историю изменений версий во времени
- Каждая комбинация хост+приложение показывается отдельной строкой
- Версии отображаются разными цветами
- Включена трансформация "Grouping to matrix" для правильного отображения меток как состояний

**Панель 2 - Таблица:**
- Отображает текущие версии в табличном виде с использованием instant запроса и трансформации "Organize fields"
- Показывает только актуальные данные

### Переменные дашборда:

- `$datasource` - выбор источника данных Prometheus
- `$nodename` - фильтр по хостам (multi-select)
- `$appname` - фильтр по приложениям (multi-select)

### Важные замечания для версий:

1. **Prometheus v2.31** полностью поддерживает необходимые запросы с group by
2. **Grafana v11** имеет все необходимые функции для State timeline и трансформаций
3. Для корректного отображения истории важно, чтобы Prometheus хранил достаточную историю данных (настройка `retention.time`)

Дашборд автоматически обновляется каждые 30 секунд и показывает данные за последние 24 часа. Вы можете изменить временной диапазон через селектор времени Grafana.
