Ниже — готовый JSON для Grafana 11. В нем есть:
- Переменные: datasource, nodename, appname
- Таблица с текущей версией, предыдущей версией и датой последней смены
- State timeline с историей смен версий (по наведению видно строковую версию)

Импорт: Dashboards → New → Import → Paste JSON → выбрать Prometheus datasource.

```json
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": {
          "type": "grafana",
          "uid": "grafana"
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
  "liveNow": false,
  "links": [],
  "refresh": "30s",
  "schemaVersion": 39,
  "style": "dark",
  "tags": [
    "versions",
    "prometheus",
    "apps"
  ],
  "templating": {
    "list": [
      {
        "name": "datasource",
        "type": "datasource",
        "label": "Datasource",
        "query": "prometheus",
        "hide": 0,
        "current": null
      },
      {
        "name": "nodename",
        "type": "query",
        "label": "Node",
        "hide": 0,
        "datasource": {
          "type": "prometheus",
          "uid": "$datasource"
        },
        "refresh": 1,
        "includeAll": true,
        "multi": true,
        "allValue": ".*",
        "query": "label_values(app_version_info, nodename)",
        "sort": 1
      },
      {
        "name": "appname",
        "type": "query",
        "label": "App",
        "hide": 0,
        "datasource": {
          "type": "prometheus",
          "uid": "$datasource"
        },
        "refresh": 1,
        "includeAll": true,
        "multi": true,
        "allValue": ".*",
        "query": "label_values(app_version_info{nodename=~\"$nodename\"}, appname)",
        "sort": 1
      }
    ]
  },
  "time": {
    "from": "now-30d",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "",
  "title": "App Versions (Prometheus)",
  "uid": "app-versions-v11",
  "version": 1,
  "weekStart": "",
  "panels": [
    {
      "type": "table",
      "title": "Текущая/предыдущая версия и дата смены",
      "description": "Показывает текущую и предыдущую версии и время последней смены по (nodename, appname).",
      "gridPos": {
        "h": 10,
        "w": 24,
        "x": 0,
        "y": 0
      },
      "pluginVersion": "11.0.0",
      "datasource": {
        "type": "prometheus",
        "uid": "$datasource"
      },
      "targets": [
        {
          "refId": "A",
          "editorMode": "code",
          "expr": "app_version_change_time_seconds{nodename=~\"$nodename\", appname=~\"$appname\"}\n  * on (nodename, appname) group_left(version, prev_version)\n    app_version_info{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "legendFormat": "",
          "instant": true,
          "range": false
        }
      ],
      "options": {
        "showHeader": true,
        "footer": {
          "show": false,
          "fields": "",
          "reducer": [
            "count"
          ]
        }
      },
      "fieldConfig": {
        "defaults": {
          "mappings": [],
          "color": {
            "mode": "thresholds"
          },
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "value": null,
                "color": "green"
              }
            ]
          }
        },
        "overrides": [
          {
            "matcher": {
              "id": "byName",
              "options": "__name__"
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
                "id": "unit",
                "value": "dateTimeAsIso"
              },
              {
                "id": "displayName",
                "value": "Дата смены версии"
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "nodename"
            },
            "properties": [
              {
                "id": "displayName",
                "value": "Хост"
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "appname"
            },
            "properties": [
              {
                "id": "displayName",
                "value": "Приложение"
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "version"
            },
            "properties": [
              {
                "id": "displayName",
                "value": "Текущая версия"
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
                "value": "Предыдущая версия"
              }
            ]
          }
        ]
      },
      "transformations": [
        {
          "id": "organize",
          "options": {
            "excludeByName": {
              "__name__": true
            },
            "indexByName": {
              "nodename": 0,
              "appname": 1,
              "version": 2,
              "prev_version": 3,
              "Value": 4
            },
            "renameByName": {
              "nodename": "Хост",
              "appname": "Приложение",
              "version": "Текущая версия",
              "prev_version": "Предыдущая версия",
              "Value": "Дата смены версии"
            }
          }
        }
      ]
    },
    {
      "type": "state-timeline",
      "title": "История смены версий",
      "description": "Лента состояний по версиям. Наведите курсор, чтобы увидеть строковую версию из метрики info.",
      "gridPos": {
        "h": 12,
        "w": 24,
        "x": 0,
        "y": 10
      },
      "pluginVersion": "11.0.0",
      "datasource": {
        "type": "prometheus",
        "uid": "$datasource"
      },
      "targets": [
        {
          "refId": "A",
          "editorMode": "code",
          "expr": "app_version_numeric{nodename=~\"$nodename\", appname=~\"$appname\"}\n  * on (nodename, appname) group_right(version)\n    app_version_info{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "legendFormat": "{{nodename}} • {{appname}}",
          "instant": false,
          "range": true,
          "exemplar": true
        }
      ],
      "options": {
        "legend": {
          "showLegend": true,
          "displayMode": "list",
          "placement": "bottom"
        },
        "mergeValues": true,
        "rowHeight": 0.9,
        "tooltip": {
          "mode": "single"
        }
      },
      "fieldConfig": {
        "defaults": {
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "value": null,
                "color": "green"
              }
            ]
          },
          "custom": {
            "fillOpacity": 70,
            "lineWidth": 1,
            "spanNulls": true,
            "insertNulls": false
          }
        },
        "overrides": [
          {
            "matcher": {
              "id": "byName",
              "options": "Value"
            },
            "properties": [
              {
                "id": "unit",
                "value": "none"
              }
            ]
          }
        ]
      }
    }
  ]
}
```

Пояснения и тонкости:
- Таблица использует join в PromQL: app_version_change_time_seconds * on(...) group_left(...) app_version_info — так в одну строку попадают и версии (строковые из info), и время смены.
- State timeline использует числовую метрику для смен состояний и «обогащает» её лейблом version из info через group_right. По наведению вы увидите version=... в тултипе. Рядов будет по одному на каждую пару (nodename, appname) с учетом выбранных переменных.
- Переменные:
  - datasource — Prometheus источник
  - nodename — из label_values(app_version_info, nodename), поддерживает множественный выбор и All (.*)
  - appname — фильтруется по выбранным nodename, также множественный и All (.*)

Если понадобится, можно добавить:
- колонку «Когда сканировали» с app_version_scrape_timestamp_seconds (и подсветкой по давности)
- индикацию статуса сборщика: app_version_collector_success и длительность app_version_collector_duration_seconds.
