# Grafana Dashboard для Data-prepper Метрик

Вот полноценный JSON дашборд для Grafana:

```json
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": "-- Grafana --",
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
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "panels": [
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 0
      },
      "id": 100,
      "panels": [],
      "title": "📊 Overview",
      "type": "row"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [],
          "max": 100,
          "min": 0,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "yellow",
                "value": 60
              },
              {
                "color": "red",
                "value": 80
              }
            ]
          },
          "unit": "percent"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 0,
        "y": 1
      },
      "id": 1,
      "options": {
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        },
        "showThresholdLabels": false,
        "showThresholdMarkers": true
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "process_cpu_usage * 100",
          "refId": "A"
        }
      ],
      "title": "CPU Usage",
      "type": "gauge"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
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
        }
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 6,
        "y": 1
      },
      "id": 2,
      "options": {
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        },
        "showThresholdLabels": false,
        "showThresholdMarkers": true
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "armeria_executor_active_threads",
          "legendFormat": "{{executor}}",
          "refId": "A"
        }
      ],
      "title": "Active Threads",
      "type": "gauge"
    },
    {
      "datasource": "Prometheus",
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
                "value": 100
              },
              {
                "color": "red",
                "value": 500
              }
            ]
          },
          "unit": "short"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 12,
        "y": 1
      },
      "id": 3,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "armeria_server_connections",
          "refId": "A"
        }
      ],
      "title": "Active Connections",
      "type": "stat"
    },
    {
      "datasource": "Prometheus",
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
              }
            ]
          },
          "unit": "short"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 18,
        "y": 1
      },
      "id": 4,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "armeria_executor_queued_tasks",
          "legendFormat": "{{executor}}",
          "refId": "A"
        }
      ],
      "title": "Queued Tasks",
      "type": "stat"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 9
      },
      "id": 101,
      "panels": [],
      "title": "🧵 Thread Pool Metrics",
      "type": "row"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 20,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true,
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
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 10
      },
      "id": 5,
      "options": {
        "legend": {
          "calcs": ["mean", "lastNotNull", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "armeria_executor_pool_core_threads",
          "legendFormat": "Core - {{executor}}",
          "refId": "A"
        },
        {
          "expr": "armeria_executor_pool_max_threads",
          "legendFormat": "Max - {{executor}}",
          "refId": "B"
        },
        {
          "expr": "armeria_executor_pool_size_threads",
          "legendFormat": "Current - {{executor}}",
          "refId": "C"
        },
        {
          "expr": "armeria_executor_active_threads",
          "legendFormat": "Active - {{executor}}",
          "refId": "D"
        }
      ],
      "title": "Thread Pool Size",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 20,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true,
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
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 10
      },
      "id": 6,
      "options": {
        "legend": {
          "calcs": ["mean", "lastNotNull"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "armeria_executor_queued_tasks",
          "legendFormat": "Queued - {{executor}}",
          "refId": "A"
        },
        {
          "expr": "armeria_executor_queue_remaining_tasks",
          "legendFormat": "Remaining Capacity - {{executor}}",
          "refId": "B"
        }
      ],
      "title": "Task Queue Status",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 18
      },
      "id": 102,
      "panels": [],
      "title": "⚙️ Task Execution Metrics",
      "type": "row"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 20,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true,
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
          "unit": "ops"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 19
      },
      "id": 7,
      "options": {
        "legend": {
          "calcs": ["mean", "lastNotNull"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(armeria_executor_completed_tasks_total[5m])",
          "legendFormat": "Completed - {{executor}}",
          "refId": "A"
        },
        {
          "expr": "rate(armeria_executor_scheduled_once_total[5m])",
          "legendFormat": "Scheduled Once - {{executor}}",
          "refId": "B"
        },
        {
          "expr": "rate(armeria_executor_scheduled_repetitively_total[5m])",
          "legendFormat": "Scheduled Repetitively - {{executor}}",
          "refId": "C"
        }
      ],
      "title": "Task Execution Rate",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 20,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true,
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
          "unit": "s"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 19
      },
      "id": 8,
      "options": {
        "legend": {
          "calcs": ["mean", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(armeria_executor_seconds_sum[5m]) / rate(armeria_executor_seconds_count[5m])",
          "legendFormat": "Avg Duration - {{executor}}",
          "refId": "A"
        },
        {
          "expr": "armeria_executor_seconds_max",
          "legendFormat": "Max Duration - {{executor}}",
          "refId": "B"
        }
      ],
      "title": "Task Execution Duration",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 20,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true,
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
          "unit": "s"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 27
      },
      "id": 9,
      "options": {
        "legend": {
          "calcs": ["mean", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(armeria_executor_idle_seconds_sum[5m]) / rate(armeria_executor_idle_seconds_count[5m])",
          "legendFormat": "Avg Idle Time - {{executor}}",
          "refId": "A"
        },
        {
          "expr": "armeria_executor_idle_seconds_max",
          "legendFormat": "Max Idle Time - {{executor}}",
          "refId": "B"
        }
      ],
      "title": "Thread Idle Time",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "bars",
            "fillOpacity": 80,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": false,
            "stacking": {
              "group": "A",
              "mode": "normal"
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
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 27
      },
      "id": 10,
      "options": {
        "legend": {
          "calcs": ["sum"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "increase(armeria_executor_completed_tasks_total[1h])",
          "legendFormat": "Completed - {{executor}}",
          "refId": "A"
        }
      ],
      "title": "Completed Tasks (Hourly)",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 35
      },
      "id": 103,
      "panels": [],
      "title": "🔌 Server Connection Metrics",
      "type": "row"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 20,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true,
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
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 36
      },
      "id": 11,
      "options": {
        "legend": {
          "calcs": ["mean", "lastNotNull", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "armeria_server_connections",
          "legendFormat": "Active Connections",
          "refId": "A"
        }
      ],
      "title": "Active Server Connections",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 20,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true,
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
          "unit": "s"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 36
      },
      "id": 12,
      "options": {
        "legend": {
          "calcs": ["mean", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(armeria_server_connections_lifespan_seconds_sum[5m]) / rate(armeria_server_connections_lifespan_seconds_count[5m])",
          "legendFormat": "Avg Lifespan",
          "refId": "A"
        },
        {
          "expr": "armeria_server_connections_lifespan_seconds_max",
          "legendFormat": "Max Lifespan",
          "refId": "B"
        }
      ],
      "title": "Connection Lifespan",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 44
      },
      "id": 104,
      "panels": [],
      "title": "💾 Cache Metrics",
      "type": "row"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 20,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true,
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
        }
      },
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 0,
        "y": 45
      },
      "id": 13,
      "options": {
        "legend": {
          "calcs": ["mean", "lastNotNull"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "armeria_server_router_virtual_host_cache_estimated_size",
          "legendFormat": "Cache Size",
          "refId": "A"
        }
      ],
      "title": "Virtual Host Cache Size",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 20,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true,
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
          "unit": "ops"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 8,
        "y": 45
      },
      "id": 14,
      "options": {
        "legend": {
          "calcs": ["mean", "lastNotNull"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(armeria_server_router_virtual_host_cache_requests_total[5m])",
          "legendFormat": "Requests/sec",
          "refId": "A"
        }
      ],
      "title": "Cache Request Rate",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 20,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true,
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
          "unit": "ops"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 16,
        "y": 45
      },
      "id": 15,
      "options": {
        "legend": {
          "calcs": ["mean", "lastNotNull"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(armeria_server_router_virtual_host_cache_evictions_total[5m])",
          "legendFormat": "Evictions/sec",
          "refId": "A"
        },
        {
          "expr": "rate(armeria_server_router_virtual_host_cache_evictions_weight_total[5m])",
          "legendFormat": "Weight Evictions/sec",
          "refId": "B"
        }
      ],
      "title": "Cache Eviction Rate",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [],
          "max": 100,
          "min": 0,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "red",
                "value": null
              },
              {
                "color": "yellow",
                "value": 50
              },
              {
                "color": "green",
                "value": 80
              }
            ]
          },
          "unit": "percent"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 0,
        "y": 53
      },
      "id": 16,
      "options": {
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        },
        "showThresholdLabels": false,
        "showThresholdMarkers": true
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "100 * (1 - (rate(armeria_server_router_virtual_host_cache_evictions_total[5m]) / rate(armeria_server_router_virtual_host_cache_requests_total[5m])))",
          "refId": "A"
        }
      ],
      "title": "Cache Hit Rate",
      "type": "gauge"
    }
  ],
  "refresh": "10s",
  "schemaVersion": 27,
  "style": "dark",
  "tags": ["data-prepper", "armeria", "monitoring"],
  "templating": {
    "list": [
      {
        "current": {
          "selected": false,
          "text": "Prometheus",
          "value": "Prometheus"
        },
        "description": null,
        "error": null,
        "hide": 0,
        "includeAll": false,
        "label": "Datasource",
        "multi": false,
        "name": "datasource",
        "options": [],
        "query": "prometheus",
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
        "type": "datasource"
      }
    ]
  },
  "time": {
    "from": "now-1h",
    "to": "now"
  },
  "timepicker": {
    "refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h"]
  },
  "timezone": "browser",
  "title": "Data-prepper Monitoring Dashboard",
  "uid": "data-prepper-armeria",
  "version": 1
}
```

## 📝 Описание панелей:

### **Overview Row:**
1. **CPU Usage** - Gauge показывающий использование CPU
2. **Active Threads** - Активные потоки в пуле
3. **Active Connections** - Текущие активные соединения
4. **Queued Tasks** - Задачи в очереди

### **Thread Pool Metrics:**
5. **Thread Pool Size** - Сравнение core/max/current/active потоков
6. **Task Queue Status** - Статус очереди задач

### **Task Execution Metrics:**
7. **Task Execution Rate** - Скорость выполнения задач
8. **Task Execution Duration** - Длительность выполнения
9. **Thread Idle Time** - Время простоя потоков
10. **Completed Tasks (Hourly)** - Завершенные задачи за час

### **Server Connection Metrics:**
11. **Active Server Connections** - Активные соединения
12. **Connection Lifespan** - Время жизни соединений

### **Cache Metrics:**
13. **Virtual Host Cache Size** - Размер кэша
14. **Cache Request Rate** - Частота запросов к кэшу
15. **Cache Eviction Rate** - Частота вытеснения из кэша
16. **Cache Hit Rate** - Процент попаданий в кэш

## 🚀 Установка:

1. Скопируйте JSON в файл `data-prepper-dashboard.json`
2. В Grafana: **Dashboards → Import → Upload JSON file**
3. Выберите Prometheus datasource
4. Нажмите **Import**

Dashboard готов к использованию! 📊
