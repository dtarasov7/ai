{
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
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "liveNow": false,
  "panels": [
    {
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "description": "Отображает историю изменений версий ПО для каждой комбинации nodename + appname во времени",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "custom": {
            "fillOpacity": 70,
            "lineWidth": 0,
            "spanNulls": false
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
        "overrides": []
      },
      "gridPos": {
        "h": 12,
        "w": 24,
        "x": 0,
        "y": 0
      },
      "id": 1,
      "options": {
        "alignValue": "left",
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "mergeValues": true,
        "rowHeight": 0.9,
        "showValue": "always",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "editorMode": "code",
          "expr": "app{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "format": "time_series",
          "instant": false,
          "legendFormat": "{{nodename}} - {{appname}}",
          "range": true,
          "refId": "A"
        }
      ],
      "title": "История изменений версий ПО (State Timeline)",
      "type": "state-timeline"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "description": "Таблица с информацией о последних изменениях версий для каждой комбинации nodename, appname и version",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
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
              "options": "Время последнего изменения"
            },
            "properties": [
              {
                "id": "custom.width",
                "value": 200
              },
              {
                "id": "unit",
                "value": "dateTimeFromNow"
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "Текущая версия"
            },
            "properties": [
              {
                "id": "custom.width",
                "value": 150
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "Предыдущая версия"
            },
            "properties": [
              {
                "id": "custom.width",
                "value": 150
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "Количество изменений"
            },
            "properties": [
              {
                "id": "custom.width",
                "value": 120
              }
            ]
          }
        ]
      },
      "gridPos": {
        "h": 10,
        "w": 24,
        "x": 0,
        "y": 12
      },
      "id": 2,
      "options": {
        "cellHeight": "sm",
        "footer": {
          "countRows": false,
          "fields": "",
          "reducer": ["sum"],
          "show": false
        },
        "showHeader": true,
        "sortBy": [
          {
            "desc": true,
            "displayName": "Время последнего изменения"
          }
        ]
      },
      "pluginVersion": "11.0.0",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "editorMode": "code",
          "exemplar": false,
          "expr": "(\n  last_over_time(app{nodename=~\"$nodename\", appname=~\"$appname\"}[$__range])\n  * on(nodename, appname) group_left()\n  (timestamp(app{nodename=~\"$nodename\", appname=~\"$appname\"}) > 0)\n)",
          "format": "table",
          "instant": true,
          "legendFormat": "__auto",
          "range": false,
          "refId": "CurrentVersion"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "editorMode": "code",
          "exemplar": false,
          "expr": "changes(app{nodename=~\"$nodename\", appname=~\"$appname\"}[$__range])",
          "format": "table",
          "hide": false,
          "instant": true,
          "legendFormat": "__auto",
          "range": false,
          "refId": "Changes"
        }
      ],
      "title": "Таблица изменений версий ПО",
      "transformations": [
        {
          "id": "merge",
          "options": {}
        },
        {
          "id": "organize",
          "options": {
            "excludeByName": {
              "Time": true,
              "__name__": true,
              "instance": true,
              "job": true
            },
            "indexByName": {
              "Time": 0,
              "Value #Changes": 6,
              "Value #CurrentVersion": 5,
              "__name__": 7,
              "appname": 2,
              "instance": 8,
              "job": 9,
              "nodename": 1,
              "version": 3
            },
            "renameByName": {
              "Time": "",
              "Value #Changes": "Количество изменений",
              "Value #CurrentVersion": "Время последнего изменения",
              "appname": "Приложение",
              "nodename": "Хост",
              "version": "Текущая версия"
            }
          }
        },
        {
          "id": "convertFieldType",
          "options": {
            "conversions": [
              {
                "destinationType": "time",
                "targetField": "Время последнего изменения"
              }
            ],
            "fields": {}
          }
        }
      ],
      "type": "table"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "description": "Детальная информация о версиях в выбранном временном диапазоне с возможностью увидеть переходы между версиями",
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
            "barWidthFactor": 0.6,
            "drawStyle": "line",
            "fillOpacity": 0,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "insertNulls": false,
            "lineInterpolation": "stepAfter",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "always",
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
              }
            ]
          },
          "unit": "short"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 10,
        "w": 24,
        "x": 0,
        "y": 22
      },
      "id": 3,
      "options": {
        "legend": {
          "calcs": ["lastNotNull"],
          "displayMode": "table",
          "placement": "right",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      },
      "pluginVersion": "11.0.0",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "editorMode": "code",
          "expr": "app{nodename=~\"$nodename\", appname=~\"$appname\"}",
          "format": "time_series",
          "instant": false,
          "legendFormat": "{{nodename}} - {{appname}} (v{{version}})",
          "range": true,
          "refId": "A"
        }
      ],
      "title": "График версий ПО во времени (Time Series)",
      "type": "timeseries"
    }
  ],
  "refresh": "",
  "schemaVersion": 39,
  "tags": ["versions", "software", "monitoring"],
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
        "label": "Data Source",
        "multi": false,
        "name": "DS_PROMETHEUS",
        "options": [],
        "query": "prometheus",
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
        "type": "datasource"
      },
      {
        "current": {
          "selected": true,
          "text": "All",
          "value": "$__all"
        },
        "datasource": {
          "type": "prometheus",
          "uid": "${DS_PROMETHEUS}"
        },
        "definition": "label_values(app, nodename)",
        "hide": 0,
        "includeAll": true,
        "label": "Node Name",
        "multi": true,
        "name": "nodename",
        "options": [],
        "query": {
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
        "current": {
          "selected": true,
          "text": "All",
          "value": "$__all"
        },
        "datasource": {
          "type": "prometheus",
          "uid": "${DS_PROMETHEUS}"
        },
        "definition": "label_values(app{nodename=~\"$nodename\"}, appname)",
        "hide": 0,
        "includeAll": true,
        "label": "App Name",
        "multi": true,
        "name": "appname",
        "options": [],
        "query": {
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
    "from": "now-7d",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "",
  "title": "Software Version Tracking Dashboard",
  "uid": "software-version-tracking",
  "version": 1,
  "weekStart": ""
}
