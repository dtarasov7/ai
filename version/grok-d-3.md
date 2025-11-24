```json
{
  "__inputs": [],
  "dashboard": {
    "id": null,
    "title": "App Version Dashboard",
    "tags": ["versions"],
    "style": "dark",
    "timezone": "browser",
    "editable": true,
    "hideControls": false,
    "graphTooltip": 0,
    "panels": [
      {
        "collapsed": false,
        "gridPos": {
          "h": 1,
          "w": 24,
          "x": 0,
          "y": 0
        },
        "id": 1,
        "panels": [],
        "title": "App Versions Overview",
        "type": "row"
      },
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
              "align": "auto",
              "displayMode": "auto"
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
            },
            "unit": "none"
          },
          "overrides": [
            {
              "matcher": {
                "id": "byRegexp",
                "options": "version"
              },
              "properties": [
                {
                  "id": "custom.displayMode",
                  "value": "color-background"
                },
                {
                  "id": "color",
                  "value": {
                    "fixedColor": "blue",
                    "mode": "fixed"
                  }
                },
                {
                  "id": "mappings",
                  "value": [
                    {
                      "options": {
                        "1.22.1": {
                          "color": "blue",
                          "index": 0
                        },
                        "1.20.1": {
                          "color": "red",
                          "index": 1
                        }
                      },
                      "type": "value"
                    }
                  ]
                }
              ]
            },
            {
              "matcher": {
                "id": "byRegexp",
                "options": "prev_version"
              },
              "properties": [
                {
                  "id": "custom.displayMode",
                  "value": "color-background"
                },
                {
                  "id": "color",
                  "value": {
                    "fixedColor": "orange",
                    "mode": "fixed"
                  }
                }
              ]
            },
            {
              "matcher": {
                "id": "byRegexp",
                "options": "change_time"
              },
              "properties": [
                {
                  "id": "unit",
                  "value": "dateTimeAsIso"
                }
              ]
            }
          ]
        },
        "gridPos": {
          "h": 10,
          "w": 24,
          "x": 0,
          "y": 1
        },
        "id": 2,
        "options": {
          "showHeader": true,
          "sortBy": [
            {
              "desc": true,
              "displayName": "nodename"
            }
          ]
        },
        "pluginVersion": "11.1.0",
        "targets": [
          {
            "datasource": {
              "type": "prometheus",
              "uid": "${datasource}"
            },
            "editorMode": "code",
            "expr": "app_version_info{nodename=~\"${nodename:regex}\", appname=~\"${appname:regex}\"}",
            "format": "table",
            "instant": true,
            "legendFormat": "",
            "range": false,
            "refId": "A"
          },
          {
            "datasource": {
              "type": "prometheus",
              "uid": "${datasource}"
            },
            "editorMode": "code",
            "expr": "fromUnixTimestamp(app_version_change_time_seconds{nodename=~\"${nodename:regex}\", appname=~\"${appname:regex}\"})",
            "format": "table",
            "instant": true,
            "legendFormat": "change_time",
            "range": false,
            "refId": "B"
          }
        ],
        "title": "Current and Previous Versions with Change Date",
        "transformations": [
          {
            "id": "organize",
            "options": {
              "excludeByRegexp": {
                "Time": true,
                "Value #A": true,
                "Value #B": true
              },
              "indexByName": {
                "nodename": 0,
                "appname": 1,
                "version": 2,
                "prev_version": 3,
                "change_time": 4
              },
              "renameByName": {
                "Label": "nodename",
                "Metric name": "appname"
              }
            }
          },
          {
            "id": "joinByField",
            "options": {
              "byField": "nodename",
              "keep": "all"
            }
          },
          {
            "id": "joinByField",
            "options": {
              "byField": "appname",
              "keep": "all"
            }
          }
        ],
        "type": "table"
      },
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
                  "color": "yellow",
                  "value": 1010000
                },
                {
                  "color": "red",
                  "value": 1020000
                }
              ]
            },
            "unit": "none"
          },
          "overrides": [
            {
              "matcher": {
                "id": "byName",
                "options": "Value"
              },
              "properties": [
                {
                  "id": "displayName",
                  "value": "Version (Numeric)"
                },
                {
                  "id": "mappings",
                  "value": [
                    {
                      "options": {
                        "1022001": {
                          "color": "green",
                          "index": 1,
                          "text": "1.22.1"
                        },
                        "1020001": {
                          "color": "yellow",
                          "index": 2,
                          "text": "1.20.1"
                        }
                      },
                      "type": "value"
                    }
                  ]
                }
              ]
            }
          ]
        },
        "gridPos": {
          "h": 10,
          "w": 24,
          "x": 0,
          "y": 11
        },
        "id": 3,
        "options": {
          "calculate": false,
          "cellGap": 2,
          "cellHeight": 40,
          "cellWidth": 100,
          "colorMode": "value",
          "colorValue": false,
          "exemplars": false,
          "filterValues": {
            "select": "All"
          },
          "hideEmpty": false,
          "hideLabels": false,
          "lineWidth": 1,
          "lineStyle": "Solid",
          "maxValues": 100,
          "now": true,
          "quandary": false,
          "showLegend": true,
          "showValue": "text",
          "text": {
            "align": "auto",
            "colorSize": 12,
            "showName": true,
            "showStates": true,
            "showValue": true,
            "size": "auto"
          },
          "valueMode": "numeric",
          "valueOptions": {
            "calculation": "lastNotNull",
            "reduceOptions": {
              "values": false,
              "calcs": [
                "lastNotNull"
              ],
              "fields": ""
            },
            "show": {
              "current": true,
              "previous": false,
              "all": false
            }
          }
        },
        "targets": [
          {
            "datasource": {
              "type": "prometheus",
              "uid": "${datasource}"
            },
            "editorMode": "code",
            "expr": "app_version_numeric{nodename=~\"${nodename:regex}\", appname=~\"${appname:regex}\"}",
            "legendFormat": "{{appname}} on {{nodename}}",
            "range": true,
            "refId": "A"
          }
        ],
        "title": "Version Changes Over Time (State Timeline)",
        "type": "stat"
      }
    ],
    "schemaVersion": 39,
    "refresh": "30s",
    "revision": 1,
    "version": 1,
    "templating": {
      "list": [
        {
          "allValue": null,
          "current": {
            "selected": false,
            "text": "Prometheus",
            "value": "prometheus"
          },
          "datasource": {
            "type": "prometheus",
            "uid": "prometheus"
          },
          "definition": "label_values()",
          "hide": 0,
          "includeAll": false,
          "label": "Datasource",
          "multi": false,
          "name": "datasource",
          "options": [],
          "query": {
            "query": "prometheus",
            "refId": "StandardVariableQuery",
            "scenarioId": "prometheus"
          },
          "refresh": 1,
          "regex": "",
          "skipUrlSync": false,
          "sort": 0,
          "type": "datasource"
        },
        {
          "allValue": null,
          "current": {},
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "definition": "label_values(app_version_info, nodename)",
          "hide": 0,
          "includeAll": true,
          "label": "Node Name",
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
          "sort": 1,
          "type": "query"
        },
        {
          "allValue": null,
          "current": {},
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "definition": "label_values(app_version_info, appname)",
          "hide": 0,
          "includeAll": true,
          "label": "App Name",
          "multi": true,
          "name": "appname",
          "options": [],
          "query": {
            "query": "label_values(app_version_info, appname)",
            "refId": "StandardVariableQuery"
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
    "timepicker": {
      "refresh_intervals": [
        "5s",
        "10s",
        "30s",
        "1m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "1d"
      ]
    },
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
    "links": []
  },
  "overwrite": false
}
```

### Пояснения к дашборду:

#### Переменные (Variables):
- **datasource**: Выбор источника данных Prometheus (по умолчанию первый доступный Prometheus).
- **nodename**: Множественный выбор узлов из метки `nodename` в `app_version_info`. Поддерживает regex для фильтрации.
- **appname**: Множественный выбор приложений из метки `appname` в `app_version_info`. Поддерживает regex.

#### Панели:
1. **Таблица "Current and Previous Versions with Change Date"** (ID 2):
   - **Запросы**:
     - A: `app_version_info{nodename=~"${nodename:regex}", appname=~"${appname:regex}"}` (Instant query для извлечения labels: nodename, appname, version, prev_version).
     - B: `fromUnixTimestamp(app_version_change_time_seconds{nodename=~"${nodename:regex}", appname=~"${appname:regex}"})` (Instant query для даты смены).
   - **Трансформации**:
     - Organize: Удаляет ненужные колонки (Time, Value), переименовывает и индексирует для соответствия (nodename, appname, version, prev_version, change_time).
     - Join by Field: Объединяет результаты по nodename и appname.
   - **Конфигурация полей**: 
     - Version и prev_version отображаются с цветами (синий для текущей, оранжевый для предыдущей).
     - Change_time форматируется как дата (ISO).
   - Таблица сортируется по nodename (desc).

2. **State Timeline "Version Changes Over Time"** (ID 3):
   - **Запрос**: `app_version_numeric{nodename=~"${nodename:regex}", appname=~"${appname:regex}"}` (Time series для исторических изменений numeric версии).
   - **Конфигурация**:
     - Использует State Timeline (в Grafana 11 это часть Stat панели с опциями для timeline, но для чистого State Timeline используйте dedicated панель; здесь адаптировано под Stat с value mode для timeline-like поведения. Для точного State Timeline замените тип на "state-timeline" в UI).
     - Value mappings: Маппит numeric значения на строковые версии (e.g., 1022001 → "1.22.1") с цветами.
     - Thresholds: Цвета на основе диапазонов версий.
     - Legend: Показывает appname и nodename.
     - Отображает изменения как discrete states во времени (gauge обновляется при смене, создавая steps).

#### Дополнительно:
- **Время**: По умолчанию последние 6 часов, но для timeline увеличьте в UI (e.g., now-7d).
- **Ряд**: Верхний ряд для заголовка.
- **Импорт**: Скопируйте JSON в Grafana (Dashboard → Import) и настройте datasource UID если нужно.
- **Предположения**: Метрики исторические (Prometheus хранит series over time). Для State Timeline добавьте больше mappings в UI для других версий. Если нужно чистый State Timeline, в Grafana UI измените тип панели на "State timeline" и настройте states на основе value.
