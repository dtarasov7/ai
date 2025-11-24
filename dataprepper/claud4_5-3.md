# Grafana Dashboard для Data Prepper

Создам комплексный dashboard для мониторинга Data Prepper. Вот JSON конфигурация:

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
      "datasource": "$datasource",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [],
          "max": 1,
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
                "value": 0.6
              },
              {
                "color": "red",
                "value": 0.8
              }
            ]
          },
          "unit": "percentunit"
        }
      },
      "gridPos": {
        "h": 7,
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
          "expr": "process_cpu_usage{instance=~\"$instance\"}",
          "refId": "A"
        }
      ],
      "title": "CPU Usage",
      "type": "gauge"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "h": 7,
        "w": 9,
        "x": 6,
        "y": 1
      },
      "id": 2,
      "options": {
        "legend": {
          "calcs": ["mean", "last"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "armeria_server_connections{instance=~\"$instance\"}",
          "legendFormat": "Active Connections",
          "refId": "A"
        }
      ],
      "title": "Active Connections",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
          "unit": "reqps"
        }
      },
      "gridPos": {
        "h": 7,
        "w": 9,
        "x": 15,
        "y": 1
      },
      "id": 3,
      "options": {
        "legend": {
          "calcs": ["mean", "last"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(entry_pipeline_otel_trace_source_requestsReceived_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Requests/sec",
          "refId": "A"
        }
      ],
      "title": "Request Rate (Entry Pipeline)",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 8
      },
      "id": 101,
      "panels": [],
      "title": "🔄 Pipeline Processing",
      "type": "row"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
          "unit": "rps"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 9
      },
      "id": 4,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(entry_pipeline_recordsProcessed_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Entry Pipeline",
          "refId": "A"
        },
        {
          "expr": "rate(raw_pipeline_recordsProcessed_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Raw Pipeline",
          "refId": "B"
        },
        {
          "expr": "rate(service_map_pipeline_recordsProcessed_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Service Map Pipeline",
          "refId": "C"
        }
      ],
      "title": "Records Processed (rate)",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "y": 9
      },
      "id": 5,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(entry_pipeline_otel_trace_source_requestProcessDuration_seconds_sum{instance=~\"$instance\"}[5m]) / rate(entry_pipeline_otel_trace_source_requestProcessDuration_seconds_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Entry Pipeline Avg",
          "refId": "A"
        },
        {
          "expr": "entry_pipeline_otel_trace_source_requestProcessDuration_seconds_max{instance=~\"$instance\"}",
          "legendFormat": "Entry Pipeline Max",
          "refId": "B"
        }
      ],
      "title": "Request Processing Duration",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 17
      },
      "id": 102,
      "panels": [],
      "title": "📦 Buffer Metrics",
      "type": "row"
    },
    {
      "datasource": "$datasource",
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
            "gradientMode": "opacity",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
          },
          "mappings": [],
          "max": 1,
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
                "value": 0.7
              },
              {
                "color": "red",
                "value": 0.9
              }
            ]
          },
          "unit": "percentunit"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 0,
        "y": 18
      },
      "id": 6,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "entry_pipeline_BlockingBuffer_bufferUsage{instance=~\"$instance\"}",
          "legendFormat": "Entry Pipeline",
          "refId": "A"
        },
        {
          "expr": "raw_pipeline_BlockingBuffer_bufferUsage{instance=~\"$instance\"}",
          "legendFormat": "Raw Pipeline",
          "refId": "B"
        },
        {
          "expr": "service_map_pipeline_BlockingBuffer_bufferUsage{instance=~\"$instance\"}",
          "legendFormat": "Service Map",
          "refId": "C"
        }
      ],
      "title": "Buffer Usage",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "x": 8,
        "y": 18
      },
      "id": 7,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "entry_pipeline_BlockingBuffer_recordsInBuffer{instance=~\"$instance\"}",
          "legendFormat": "Entry - In Buffer",
          "refId": "A"
        },
        {
          "expr": "entry_pipeline_BlockingBuffer_recordsInFlight{instance=~\"$instance\"}",
          "legendFormat": "Entry - In Flight",
          "refId": "B"
        },
        {
          "expr": "raw_pipeline_BlockingBuffer_recordsInBuffer{instance=~\"$instance\"}",
          "legendFormat": "Raw - In Buffer",
          "refId": "C"
        },
        {
          "expr": "raw_pipeline_BlockingBuffer_recordsInFlight{instance=~\"$instance\"}",
          "legendFormat": "Raw - In Flight",
          "refId": "D"
        }
      ],
      "title": "Records in Buffer/Flight",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "w": 8,
        "x": 16,
        "y": 18
      },
      "id": 8,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(entry_pipeline_BlockingBuffer_readTimeElapsed_seconds_sum{instance=~\"$instance\"}[5m]) / rate(entry_pipeline_BlockingBuffer_readTimeElapsed_seconds_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Entry - Read Avg",
          "refId": "A"
        },
        {
          "expr": "rate(entry_pipeline_BlockingBuffer_writeTimeElapsed_seconds_sum{instance=~\"$instance\"}[5m]) / rate(entry_pipeline_BlockingBuffer_writeTimeElapsed_seconds_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Entry - Write Avg",
          "refId": "B"
        },
        {
          "expr": "rate(raw_pipeline_BlockingBuffer_readTimeElapsed_seconds_sum{instance=~\"$instance\"}[5m]) / rate(raw_pipeline_BlockingBuffer_readTimeElapsed_seconds_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Raw - Read Avg",
          "refId": "C"
        },
        {
          "expr": "rate(raw_pipeline_BlockingBuffer_WriteTimeElapsed_seconds_sum{instance=~\"$instance\"}[5m]) / rate(raw_pipeline_BlockingBuffer_WriteTimeElapsed_seconds_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Raw - Write Avg",
          "refId": "D"
        }
      ],
      "title": "Buffer Read/Write Latency",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 26
      },
      "id": 103,
      "panels": [],
      "title": "🔍 OpenSearch Sink",
      "type": "row"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "y": 27
      },
      "id": 9,
      "options": {
        "legend": {
          "calcs": ["mean", "last"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(raw_pipeline_opensearch_documentsSuccess_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Raw - Success",
          "refId": "A"
        },
        {
          "expr": "rate(raw_pipeline_opensearch_documentErrors_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Raw - Errors",
          "refId": "B"
        },
        {
          "expr": "rate(service_map_pipeline_opensearch_documentsSuccess_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Service Map - Success",
          "refId": "C"
        },
        {
          "expr": "rate(service_map_pipeline_opensearch_documentErrors_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Service Map - Errors",
          "refId": "D"
        }
      ],
      "title": "OpenSearch Documents Success/Error Rate",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "y": 27
      },
      "id": 10,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(raw_pipeline_opensearch_bulkRequestLatency_seconds_sum{instance=~\"$instance\"}[5m]) / rate(raw_pipeline_opensearch_bulkRequestLatency_seconds_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Raw Pipeline - Avg",
          "refId": "A"
        },
        {
          "expr": "raw_pipeline_opensearch_bulkRequestLatency_seconds_max{instance=~\"$instance\"}",
          "legendFormat": "Raw Pipeline - Max",
          "refId": "B"
        },
        {
          "expr": "rate(service_map_pipeline_opensearch_bulkRequestLatency_seconds_sum{instance=~\"$instance\"}[5m]) / rate(service_map_pipeline_opensearch_bulkRequestLatency_seconds_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Service Map - Avg",
          "refId": "C"
        },
        {
          "expr": "service_map_pipeline_opensearch_bulkRequestLatency_seconds_max{instance=~\"$instance\"}",
          "legendFormat": "Service Map - Max",
          "refId": "D"
        }
      ],
      "title": "OpenSearch Bulk Request Latency",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
          "unit": "decbytes"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 35
      },
      "id": 11,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(raw_pipeline_opensearch_bulkRequestSizeBytes_sum{instance=~\"$instance\"}[5m]) / rate(raw_pipeline_opensearch_bulkRequestSizeBytes_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Raw Pipeline - Avg Size",
          "refId": "A"
        },
        {
          "expr": "raw_pipeline_opensearch_bulkRequestSizeBytes_max{instance=~\"$instance\"}",
          "legendFormat": "Raw Pipeline - Max Size",
          "refId": "B"
        },
        {
          "expr": "rate(service_map_pipeline_opensearch_bulkRequestSizeBytes_sum{instance=~\"$instance\"}[5m]) / rate(service_map_pipeline_opensearch_bulkRequestSizeBytes_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Service Map - Avg Size",
          "refId": "C"
        }
      ],
      "title": "OpenSearch Bulk Request Size",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
                "value": 1
              }
            ]
          },
          "unit": "ops"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 35
      },
      "id": 12,
      "options": {
        "legend": {
          "calcs": ["mean", "last"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(raw_pipeline_opensearch_bulkRequestErrors_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Raw Pipeline - Bulk Errors",
          "refId": "A"
        },
        {
          "expr": "rate(service_map_pipeline_opensearch_bulkRequestErrors_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Service Map - Bulk Errors",
          "refId": "B"
        }
      ],
      "title": "OpenSearch Bulk Request Errors",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 43
      },
      "id": 104,
      "panels": [],
      "title": "📥 OTel Source Metrics",
      "type": "row"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
          "unit": "reqps"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 44
      },
      "id": 13,
      "options": {
        "legend": {
          "calcs": ["mean", "last"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(entry_pipeline_otel_trace_source_successRequests_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Success",
          "refId": "A"
        },
        {
          "expr": "rate(entry_pipeline_otel_trace_source_badRequests_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Bad Requests",
          "refId": "B"
        },
        {
          "expr": "rate(entry_pipeline_otel_trace_source_requestsTooLarge_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Too Large",
          "refId": "C"
        },
        {
          "expr": "rate(entry_pipeline_otel_trace_source_requestTimeouts_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Timeouts",
          "refId": "D"
        },
        {
          "expr": "rate(entry_pipeline_otel_trace_source_internalServerError_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Internal Errors",
          "refId": "E"
        }
      ],
      "title": "OTel Source Request Status",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
          "unit": "decbytes"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 44
      },
      "id": 14,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(entry_pipeline_otel_trace_source_payloadSize_sum{instance=~\"$instance\"}[5m]) / rate(entry_pipeline_otel_trace_source_payloadSize_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Avg Payload Size",
          "refId": "A"
        },
        {
          "expr": "entry_pipeline_otel_trace_source_payloadSize_max{instance=~\"$instance\"}",
          "legendFormat": "Max Payload Size",
          "refId": "B"
        }
      ],
      "title": "OTel Source Payload Size",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 52
      },
      "id": 105,
      "panels": [],
      "title": "🗺️ Service Map",
      "type": "row"
    },
    {
      "datasource": "$datasource",
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
                "value": 10000
              },
              {
                "color": "red",
                "value": 50000
              }
            ]
          },
          "unit": "short"
        }
      },
      "gridPos": {
        "h": 7,
        "w": 6,
        "x": 0,
        "y": 53
      },
      "id": 15,
      "options": {
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        },
        "showThresholdLabels": false,
        "showThresholdMarkers": true,
        "text": {}
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "service_map_pipeline_service_map_stateful_spansDbSize{instance=~\"$instance\"}",
          "refId": "A"
        }
      ],
      "title": "Service Map Spans DB Size",
      "type": "gauge"
    },
    {
      "datasource": "$datasource",
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
                "value": 1000
              },
              {
                "color": "red",
                "value": 5000
              }
            ]
          },
          "unit": "short"
        }
      },
      "gridPos": {
        "h": 7,
        "w": 6,
        "x": 6,
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
        "showThresholdMarkers": true,
        "text": {}
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "service_map_pipeline_service_map_stateful_traceGroupDbSize{instance=~\"$instance\"}",
          "refId": "A"
        }
      ],
      "title": "Service Map Trace Groups DB Size",
      "type": "gauge"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
          "unit": "rps"
        }
      },
      "gridPos": {
        "h": 7,
        "w": 12,
        "x": 12,
        "y": 53
      },
      "id": 17,
      "options": {
        "legend": {
          "calcs": ["mean", "last"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(service_map_pipeline_service_map_stateful_recordsIn_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Records In",
          "refId": "A"
        },
        {
          "expr": "rate(service_map_pipeline_service_map_stateful_recordsOut_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Records Out",
          "refId": "B"
        }
      ],
      "title": "Service Map Records In/Out",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 60
      },
      "id": 106,
      "panels": [],
      "title": "🔀 Peer Forwarder",
      "type": "row"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
          "unit": "reqps"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 61
      },
      "id": 18,
      "options": {
        "legend": {
          "calcs": ["mean", "last"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(core_peerForwarder_requests_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Total Requests",
          "refId": "A"
        },
        {
          "expr": "rate(core_peerForwarder_badRequests_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Bad Requests",
          "refId": "B"
        },
        {
          "expr": "rate(core_peerForwarder_requestsTooLarge_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Too Large",
          "refId": "C"
        },
        {
          "expr": "rate(core_peerForwarder_requestsUnprocessable_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Unprocessable",
          "refId": "D"
        },
        {
          "expr": "rate(core_peerForwarder_requestTimeouts_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Timeouts",
          "refId": "E"
        }
      ],
      "title": "Peer Forwarder Requests",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "y": 61
      },
      "id": 19,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(core_peerForwarder_clientRequestForwardingLatency_seconds_sum{instance=~\"$instance\"}[5m]) / rate(core_peerForwarder_clientRequestForwardingLatency_seconds_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Client Forwarding Latency Avg",
          "refId": "A"
        },
        {
          "expr": "core_peerForwarder_clientRequestForwardingLatency_seconds_max{instance=~\"$instance\"}",
          "legendFormat": "Client Forwarding Latency Max",
          "refId": "B"
        },
        {
          "expr": "rate(core_peerForwarder_serverRequestProcessingLatency_seconds_sum{instance=~\"$instance\"}[5m]) / rate(core_peerForwarder_serverRequestProcessingLatency_seconds_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Server Processing Latency Avg",
          "refId": "C"
        },
        {
          "expr": "core_peerForwarder_serverRequestProcessingLatency_seconds_max{instance=~\"$instance\"}",
          "legendFormat": "Server Processing Latency Max",
          "refId": "D"
        }
      ],
      "title": "Peer Forwarder Latency",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "datasource": null,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 69
      },
      "id": 107,
      "panels": [],
      "title": "⚙️ Armeria Server",
      "type": "row"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "y": 70
      },
      "id": 20,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "armeria_executor_active_threads{instance=~\"$instance\"}",
          "legendFormat": "Active Threads - {{name}}",
          "refId": "A"
        },
        {
          "expr": "armeria_executor_pool_size_threads{instance=~\"$instance\"}",
          "legendFormat": "Pool Size - {{name}}",
          "refId": "B"
        },
        {
          "expr": "armeria_executor_pool_max_threads{instance=~\"$instance\"}",
          "legendFormat": "Max Pool - {{name}}",
          "refId": "C"
        }
      ],
      "title": "Armeria Executor Thread Pool",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "y": 70
      },
      "id": 21,
      "options": {
        "legend": {
          "calcs": ["mean", "last"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "armeria_executor_queued_tasks{instance=~\"$instance\"}",
          "legendFormat": "Queued Tasks - {{name}}",
          "refId": "A"
        },
        {
          "expr": "rate(armeria_executor_completed_tasks_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Completed Tasks Rate - {{name}}",
          "refId": "B"
        }
      ],
      "title": "Armeria Executor Tasks",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "y": 78
      },
      "id": 22,
      "options": {
        "legend": {
          "calcs": ["mean", "last", "max"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "rate(armeria_server_connections_lifespan_seconds_sum{instance=~\"$instance\"}[5m]) / rate(armeria_server_connections_lifespan_seconds_count{instance=~\"$instance\"}[5m])",
          "legendFormat": "Avg Connection Lifespan",
          "refId": "A"
        },
        {
          "expr": "armeria_server_connections_lifespan_seconds_max{instance=~\"$instance\"}",
          "legendFormat": "Max Connection Lifespan",
          "refId": "B"
        }
      ],
      "title": "Armeria Connection Lifespan",
      "type": "timeseries"
    },
    {
      "datasource": "$datasource",
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
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 2,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
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
        "y": 78
      },
      "id": 23,
      "options": {
        "legend": {
          "calcs": ["mean", "last"],
          "displayMode": "table",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "multi"
        }
      },
      "targets": [
        {
          "expr": "armeria_server_router_virtual_host_cache_estimated_size{instance=~\"$instance\"}",
          "legendFormat": "Cache Size",
          "refId": "A"
        },
        {
          "expr": "rate(armeria_server_router_virtual_host_cache_evictions_total{instance=~\"$instance\"}[5m])",
          "legendFormat": "Eviction Rate",
          "refId": "B"
        },
        {
          "expr": "rate(armeria_server_router_virtual_host_cache_requests_total{instance=~\"$instance\", result=\"hit\"}[5m])",
          "legendFormat": "Cache Hits",
          "refId": "C"
        },
        {
          "expr": "rate(armeria_server_router_virtual_host_cache_requests_total{instance=~\"$instance\", result=\"miss\"}[5m])",
          "legendFormat": "Cache Misses",
          "refId": "D"
        }
      ],
      "title": "Armeria Virtual Host Cache",
      "type": "timeseries"
    }
  ],
  "refresh": "30s",
  "schemaVersion": 27,
  "style": "dark",
  "tags": ["data-prepper", "opensearch", "otel", "traces"],
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
      },
      {
        "allValue": ".*",
        "current": {
          "selected": true,
          "text": "All",
          "value": "$__all"
        },
        "datasource": "$datasource",
        "definition": "label_values(process_cpu_usage, instance)",
        "description": null,
        "error": null,
        "hide": 0,
        "includeAll": true,
        "label": "Instance",
        "multi": true,
        "name": "instance",
        "options": [],
        "query": {
          "query": "label_values(process_cpu_usage, instance)",
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
    "from": "now-1h",
    "to": "now"
  },
  "timepicker": {
    "refresh_intervals": ["10s", "30s", "1m", "5m", "15m", "30m", "1h"]
  },
  "timezone": "browser",
  "title": "Data Prepper Monitoring",
  "uid": "data-prepper-monitoring",
  "version": 1
}
```

## Основные секции dashboard:

### 📊 **Overview**
- CPU Usage (gauge)
- Active Connections
- Request Rate

### 🔄 **Pipeline Processing**
- Records Processed по всем пайплайнам
- Request Processing Duration

### 📦 **Buffer Metrics**
- Buffer Usage (процент заполнения)
- Records in Buffer/Flight
- Read/Write Latency

### 🔍 **OpenSearch Sink**
- Documents Success/Error Rate
- Bulk Request Latency
- Bulk Request Size
- Bulk Request Errors

### 📥 **OTel Source Metrics**
- Request Status (success/errors/timeouts)
- Payload Size

### 🗺️ **Service Map**
- Spans DB Size
- Trace Groups DB Size
- Records In/Out

### 🔀 **Peer Forwarder**
- Requests
- Forwarding/Processing Latency

### ⚙️ **Armeria Server**
- Thread Pool metrics
- Task metrics
- Connection Lifespan
- Virtual Host Cache

## Как импортировать:

1. В Grafana → **+** → **Import**
2. Вставьте JSON
3. Выберите Prometheus datasource
4. Нажмите **Import**

Dashboard автоматически обновляется каждые 30 секунд и поддерживает фильтрацию по instance.
