{
  "__inputs": [],
  "__elements": [],
  "__requires": [
    {
      "type": "grafana",
      "id": "grafana",
      "name": "Grafana",
      "version": "11.0.0"
    },
    {
      "type": "panel",
      "id": "state-timeline",
      "name": "State timeline",
      "version": "11.0.0"
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
  "description": "Отслеживание версий приложений на серверах",
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
        "uid": "$datasource"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "align": "auto",
            "cellOptions": {
              "type": "auto"
            },
            "filterable": false,
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
              "options": "appname"
            },
            "properties": [
              {
                "id": "displayName",
                "value": "Application"
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
                "value": "Node"
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
                "value": "Current Version"
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
                "value": "Previous Version"
              }
            ]
          },
          {
            "matcher": {
              "id": "byName",
              "options": "change_time"
            },
            "properties": [
              {
                "id": "displayName",
                "value": "Last Change Time"
              },
              {
                "id": "unit",
                "value": "dateTimeFromNow"
              }
            ]
          }
        ]
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 0
      },
      "id": 1,
      "options": {
        "showHeader": true,
        "sortBy": [
          {
            "desc": false,
            "displayName": "Application"
          }
        ]
      },
      "pluginVersion": "11.0.0",
      "targets": [
        {
          "editorMode": "code",
          "expr": "app_version_info{nodename=\"$nodename\", appname=\"$appname\"}",
          "legendFormat": "{{appname}}",
          "range": true,
          "refId": "A"
        }
      ],
      "title": "Текущие и предыдущие версии",
      "type": "table"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "$datasource"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
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
          },
          "unit": "dateTimeFromNow"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 0
      },
      "id": 2,
      "options": {
        "alignValue": "left",
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "rowHeight": 0.9,
        "showValue": "always",
        "tooltip": {
          "mode": "single"
        }
      },
      "pluginVersion": "11.0.0",
      "targets": [
        {
          "editorMode": "code",
          "expr": "app_version_change_time_seconds{nodename=\"$nodename\", appname=\"$appname\"} > 0",
          "legendFormat": "{{appname}}",
          "range": true,
          "refId": "A"
        }
      ],
      "title": "История смены версий",
      "type": "state-timeline"
    }
  ],
  "refresh": "1m",
  "schemaVersion": 37,
  "style": "dark",
  "tags": ["application", "version", "monitoring"],
  "templating": {
    "list": [
      {
        "current": {
          "selected": false,
          "text": "All",
          "value": ""
        },
        "description": "Выберите источник данных Prometheus",
        "hide": 0,
        "label": "Data Source",
        "name": "datasource",
        "options": [],
        "query": "prometheus",
        "refresh": 2,
        "regex": "",
        "skipUrlSync": false,
        "type": "datasource"
      },
      {
        "current": {
          "selected": false,
          "text": "All",
          "value": ""
        },
        "description": "Выберите узел для отображения версий",
        "hide": 0,
        "label": "Node",
        "name": "nodename",
        "options": [],
        "query": "label_values(app_version_info, nodename)",
        "refresh": 2,
        "regex": "",
        "skipUrlSync": false,
        "type": "query"
      },
      {
        "current": {
          "selected": false,
          "text": "All",
          "value": ""
        },
        "description": "Выберите приложение",
        "hide": 0,
        "label": "Application",
        "name": "appname",
        "options": [],
        "query": "label_values(app_version_info{nodename=\"$nodename\"}, appname)",
        "refresh": 2,
        "regex": "",
        "skipUrlSync": false,
        "type": "query"
      }
    ]
  },
  "time": {
    "from": "now-1h",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "",
  "title": "Application Version Tracker",
  "uid": "app-version-tracker",
  "version": 1,
  "weekStart": ""
}
