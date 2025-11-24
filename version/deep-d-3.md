{
  "dashboard": {
    "id": null,
    "title": "Application Versions Monitoring",
    "tags": ["versions", "applications", "monitoring"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Current Application Versions",
        "type": "table",
        "gridPos": {
          "h": 8,
          "w": 24,
          "x": 0,
          "y": 0
        },
        "targets": [
          {
            "expr": "app_version_info",
            "format": "table",
            "instant": true,
            "refId": "A"
          }
        ],
        "columns": [
          {
            "text": "Node",
            "value": "nodename"
          },
          {
            "text": "Application",
            "value": "appname"
          },
          {
            "text": "Current Version",
            "value": "version"
          },
          {
            "text": "Previous Version",
            "value": "prev_version"
          }
        ],
        "transformations": [
          {
            "id": "filterFieldsByName",
            "options": {
              "include": {
                "names": [
                  "nodename",
                  "appname",
                  "version",
                  "prev_version"
                ]
              }
            }
          }
        ],
        "styles": [
          {
            "alias": "Node",
            "pattern": "nodename",
            "type": "string"
          },
          {
            "alias": "Application",
            "pattern": "appname",
            "type": "string"
          },
          {
            "alias": "Current Version",
            "pattern": "version",
            "type": "string",
            "colorMode": "value",
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {
                  "color": "red",
                  "value": null
                }
              ]
            }
          },
          {
            "alias": "Previous Version",
            "pattern": "prev_version",
            "type": "string"
          }
        ]
      },
      {
        "id": 2,
        "title": "Version Change Timeline",
        "type": "timeseries",
        "gridPos": {
          "h": 8,
          "w": 24,
          "x": 0,
          "y": 8
        },
        "targets": [
          {
            "expr": "app_version_numeric",
            "legendFormat": "{{appname}} on {{nodename}}",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {
              "mode": "palette-classic"
            },
            "custom": {
              "drawStyle": "line",
              "lineInterpolation": "linear",
              "barAlignment": 0,
              "lineWidth": 2,
              "fillOpacity": 10,
              "gradientMode": "none",
              "spanNulls": false,
              "showPoints": "auto",
              "pointSize": 5,
              "stacking": {
                "mode": "none",
                "group": "A"
              },
              "axisPlacement": "auto",
              "axisLabel": "",
              "scaleDistribution": {
                "type": "linear"
              },
              "axisCenteredZero": false,
              "hideFrom": {
                "tooltip": false,
                "viz": false,
                "legend": false
              }
            },
            "unit": "short",
            "decimals": 0
          },
          "overrides": []
        },
        "options": {
          "tooltip": {
            "mode": "single"
          },
          "legend": {
            "displayMode": "list",
            "placement": "bottom",
            "calcs": []
          }
        }
      },
      {
        "id": 3,
        "title": "Version Changes History",
        "type": "table",
        "gridPos": {
          "h": 8,
          "w": 24,
          "x": 0,
          "y": 16
        },
        "targets": [
          {
            "expr": "app_version_change_time_seconds",
            "format": "table",
            "instant": false,
            "refId": "A"
          }
        ],
        "transformations": [
          {
            "id": "filterFieldsByName",
            "options": {
              "include": {
                "names": [
                  "appname",
                  "nodename",
                  "Value",
                  "Time"
                ]
              }
            }
          },
          {
            "id": "convertFieldType",
            "options": {
              "conversions": [
                {
                  "destinationType": "time",
                  "targetField": "Time"
                }
              ],
              "fields": {}
            }
          }
        ],
        "columns": [
          {
            "text": "Application",
            "value": "appname"
          },
          {
            "text": "Node",
            "value": "nodename"
          },
          {
            "text": "Change Time",
            "value": "Time"
          }
        ],
        "styles": [
          {
            "alias": "Application",
            "pattern": "appname",
            "type": "string"
          },
          {
            "alias": "Node",
            "pattern": "nodename",
            "type": "string"
          },
          {
            "alias": "Change Time",
            "pattern": "Time",
            "type": "date",
            "dateFormat": "YYYY-MM-DD HH:mm:ss"
          }
        ]
      }
    ],
    "time": {
      "from": "now-24h",
      "to": "now"
    },
    "timepicker": {},
    "templating": {
      "list": [
        {
          "name": "node",
          "type": "query",
          "datasource": {
            "type": "prometheus",
            "uid": "PBFA97CFB590B2093"
          },
          "query": {
            "query": "label_values(app_version_info, nodename)"
          },
          "refresh": 1,
          "includeAll": true,
          "multi": true,
          "allValue": ".*"
        },
        {
          "name": "application",
          "type": "query",
          "datasource": {
            "type": "prometheus",
            "uid": "PBFA97CFB590B2093"
          },
          "query": {
            "query": "label_values(app_version_info{nodename=~\"$node\"}, appname)"
          },
          "refresh": 1,
          "includeAll": true,
          "multi": true,
          "allValue": ".*"
        }
      ]
    },
    "refresh": "30s",
    "schemaVersion": 37,
    "version": 1,
    "uid": "app-versions-monitoring"
  }
}
