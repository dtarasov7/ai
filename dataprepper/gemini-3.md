Конечно, вот подробный и структурированный дашборд Grafana, созданный специально для визуализации предоставленного списка метрик Data Prepper.

Дашборд сгруппирован по логическим компонентам системы (общая сводка, пайплайны, буферы, хранилища и т.д.), чтобы было легко находить проблемы и анализировать производительность.

### JSON для импорта в Grafana

Скопируйте этот JSON код и импортируйте его в Grafana (через `Dashboards` -> `Import`).

```json
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
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "panels": [
    {
      "collapsed": false,
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
                "color": "orange",
                "value": 0.7
              },
              {
                "color": "red",
                "value": 0.9
              }
            ]
          },
          "unit": "percentunit"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 7,
        "w": 4,
        "x": 0,
        "y": 1
      },
      "id": 1,
      "options": {
        "orientation": "auto",
        "reduceOptions": {
          "calcs": [
            "lastNotNull"
          ],
          "fields": "",
          "values": false
        },
        "showThresholdLabels": false,
        "showThresholdMarkers": true
      },
      "pluginVersion": "9.2.5",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "disableTextWrap": false,
          "editorMode": "builder",
          "expr": "process_cpu_usage{instance=~\"$instance\"}",
          "fullMetaSearch": false,
          "includeNulls": false,
          "instant": true,
          "legendFormat": "__auto",
          "range": true,
          "refId": "A",
          "useBackend": false
        }
      ],
      "title": "CPU Usage",
      "type": "gauge"
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
            "axisBorderShow": false,
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "legend": false,
              "tooltip": false,
              "viz": false
            },
            "insertNulls": false,
            "lineInterpolation": "linear",
            "lineWidth": 1,
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
              }
            ]
          },
          "unit": "reqps"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 7,
        "w": 10,
        "x": 4,
        "y": 1
      },
      "id": 3,
      "options": {
        "legend": {
          "calcs": [
            "mean",
            "last"
          ],
          "displayMode": "table",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "editorMode": "code",
          "expr": "rate(entry_pipeline_otel_trace_source_requestsReceived_total{instance=~\"$instance\"}[$__rate_interval])",
          "legendFormat": "Received",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "expr": "rate(entry_pipeline_otel_trace_source_successRequests_total{instance=~\"$instance\"}[$__rate_interval])",
          "hide": false,
          "legendFormat": "Success",
          "refId": "B"
        }
      ],
      "title": "Ingress Request Rate",
      "type": "timeseries"
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
            "axisBorderShow": false,
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "legend": false,
              "tooltip": false,
              "viz": false
            },
            "insertNulls": false,
            "lineInterpolation": "linear",
            "lineWidth": 1,
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
              }
            ]
          },
          "unit": "s"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 7,
        "w": 10,
        "x": 14,
        "y": 1
      },
      "id": 5,
      "options": {
        "legend": {
          "calcs": [
            "mean",
            "last",
            "max"
          ],
          "displayMode": "table",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "editorMode": "code",
          "expr": "rate(entry_pipeline_otel_trace_source_requestProcessDuration_seconds_sum{instance=~\"$instance\"}[$__rate_interval]) / rate(entry_pipeline_otel_trace_source_requestProcessDuration_seconds_count{instance=~\"$instance\"}[$__rate_interval])",
          "legendFormat": "Avg Duration",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${datasource}"
          },
          "expr": "entry_pipeline_otel_trace_source_requestProcessDuration_seconds_max{instance=~\"$instance\"}",
          "hide": false,
          "legendFormat": "Max Duration",
          "refId": "B"
        }
      ],
      "title": "Ingress Request Duration",
      "type": "timeseries"
    },
    {
      "collapsed": true,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 8
      },
      "id": 101,
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                  }
                ]
              },
              "unit": "reqps"
            },
            "overrides": []
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
              "calcs": [
                "mean",
                "last",
                "max"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "rate(entry_pipeline_recordsProcessed_total{instance=~\"$instance\"}[$__rate_interval])",
              "legendFormat": "Entry Pipeline",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(raw_pipeline_recordsProcessed_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Raw Pipeline",
              "refId": "B"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(service_map_pipeline_recordsProcessed_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Service Map Pipeline",
              "refId": "C"
            }
          ],
          "title": "Records Processed per Pipeline (rate)",
          "type": "timeseries"
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "opacity",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                  }
                ]
              },
              "unit": "short"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 12,
            "x": 12,
            "y": 9
          },
          "id": 17,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "rate(service_map_pipeline_service_map_stateful_recordsIn_total{instance=~\"$instance\"}[$__rate_interval])",
              "legendFormat": "Records In",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(service_map_pipeline_service_map_stateful_recordsOut_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Records Out",
              "refId": "B"
            }
          ],
          "title": "Service Map Processor Records In/Out",
          "type": "timeseries"
        }
      ],
      "title": "🔄 Pipeline Processing",
      "type": "row"
    },
    {
      "collapsed": false,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 9
      },
      "id": 102,
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 20,
                "gradientMode": "opacity",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                    "color": "orange",
                    "value": 0.7
                  },
                  {
                    "color": "red",
                    "value": 0.9
                  }
                ]
              },
              "unit": "percentunit"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 8,
            "x": 0,
            "y": 10
          },
          "id": 6,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last",
                "max"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "entry_pipeline_BlockingBuffer_bufferUsage{instance=~\"$instance\"}",
              "legendFormat": "Entry Pipeline",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "raw_pipeline_BlockingBuffer_bufferUsage{instance=~\"$instance\"}",
              "hide": false,
              "legendFormat": "Raw Pipeline",
              "refId": "B"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "service_map_pipeline_BlockingBuffer_bufferUsage{instance=~\"$instance\"}",
              "hide": false,
              "legendFormat": "Service Map",
              "refId": "C"
            }
          ],
          "title": "Buffer Usage",
          "type": "timeseries"
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                  }
                ]
              },
              "unit": "short"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 8,
            "x": 8,
            "y": 10
          },
          "id": 7,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last",
                "max"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "entry_pipeline_BlockingBuffer_recordsInBuffer{instance=~\"$instance\"}",
              "legendFormat": "Entry - In Buffer",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "entry_pipeline_BlockingBuffer_recordsInFlight{instance=~\"$instance\"}",
              "hide": false,
              "legendFormat": "Entry - In Flight",
              "refId": "B"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "raw_pipeline_BlockingBuffer_recordsInBuffer{instance=~\"$instance\"}",
              "hide": false,
              "legendFormat": "Raw - In Buffer",
              "refId": "C"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "raw_pipeline_BlockingBuffer_recordsInFlight{instance=~\"$instance\"}",
              "hide": false,
              "legendFormat": "Raw - In Flight",
              "refId": "D"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "service_map_pipeline_BlockingBuffer_recordsInBuffer{instance=~\"$instance\"}",
              "hide": false,
              "legendFormat": "Service Map - In Buffer",
              "refId": "E"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "service_map_pipeline_BlockingBuffer_recordsInFlight{instance=~\"$instance\"}",
              "hide": false,
              "legendFormat": "Service Map - In Flight",
              "refId": "F"
            }
          ],
          "title": "Records in Buffer/Flight",
          "type": "timeseries"
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                    "value": 1
                  }
                ]
              },
              "unit": "short"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 8,
            "x": 16,
            "y": 10
          },
          "id": 8,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last",
                "max"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "rate(entry_pipeline_BlockingBuffer_writeTimeouts_total{instance=~\"$instance\"}[$__rate_interval])",
              "legendFormat": "Entry",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(raw_pipeline_BlockingBuffer_writeTimeouts_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Raw",
              "refId": "B"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(service_map_pipeline_BlockingBuffer_writeTimeouts_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Service Map",
              "refId": "C"
            }
          ],
          "title": "Buffer Write Timeouts (rate)",
          "type": "timeseries"
        }
      ],
      "title": "📦 Buffer Metrics",
      "type": "row"
    },
    {
      "collapsed": true,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 10
      },
      "id": 103,
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                  }
                ]
              },
              "unit": "ops"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 8,
            "x": 0,
            "y": 11
          },
          "id": 9,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "rate(raw_pipeline_opensearch_documentsSuccess_total{instance=~\"$instance\"}[$__rate_interval])",
              "legendFormat": "Raw - Success",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(raw_pipeline_opensearch_documentErrors_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Raw - Errors",
              "refId": "B"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(service_map_pipeline_opensearch_documentsSuccess_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Service Map - Success",
              "refId": "C"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(service_map_pipeline_opensearch_documentErrors_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Service Map - Errors",
              "refId": "D"
            }
          ],
          "title": "OpenSearch Documents (rate)",
          "type": "timeseries"
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                  }
                ]
              },
              "unit": "s"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 8,
            "x": 8,
            "y": 11
          },
          "id": 10,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last",
                "max"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "rate(raw_pipeline_opensearch_bulkRequestLatency_seconds_sum{instance=~\"$instance\"}[$__rate_interval]) / rate(raw_pipeline_opensearch_bulkRequestLatency_seconds_count{instance=~\"$instance\"}[$__rate_interval])",
              "legendFormat": "Raw - Avg",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(service_map_pipeline_opensearch_bulkRequestLatency_seconds_sum{instance=~\"$instance\"}[$__rate_interval]) / rate(service_map_pipeline_opensearch_bulkRequestLatency_seconds_count{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Service Map - Avg",
              "refId": "C"
            }
          ],
          "title": "OpenSearch Bulk Latency",
          "type": "timeseries"
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                    "value": 1
                  }
                ]
              },
              "unit": "ops"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 8,
            "x": 16,
            "y": 11
          },
          "id": 12,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "rate(raw_pipeline_opensearch_bulkRequestErrors_total{instance=~\"$instance\"}[$__rate_interval])",
              "legendFormat": "Raw Pipeline",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(service_map_pipeline_opensearch_bulkRequestErrors_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Service Map",
              "refId": "B"
            }
          ],
          "title": "OpenSearch Bulk Errors (rate)",
          "type": "timeseries"
        }
      ],
      "title": "🔍 OpenSearch Sink",
      "type": "row"
    },
    {
      "collapsed": true,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 11
      },
      "id": 104,
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 15,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
                "pointSize": 5,
                "scaleDistribution": {
                  "type": "linear"
                },
                "showPoints": "auto",
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
              "unit": "reqps"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 12,
            "x": 0,
            "y": 12
          },
          "id": 13,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "rate(entry_pipeline_otel_trace_source_successRequests_total{instance=~\"$instance\"}[$__rate_interval])",
              "legendFormat": "Success",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(entry_pipeline_otel_trace_source_badRequests_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Bad Requests",
              "refId": "B"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(entry_pipeline_otel_trace_source_requestsTooLarge_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Too Large",
              "refId": "C"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(entry_pipeline_otel_trace_source_requestTimeouts_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Timeouts",
              "refId": "D"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(entry_pipeline_otel_trace_source_internalServerError_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Internal Errors",
              "refId": "E"
            }
          ],
          "title": "OTel Source Request Status (rate)",
          "type": "timeseries"
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                  }
                ]
              },
              "unit": "decbytes"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 12,
            "x": 12,
            "y": 12
          },
          "id": 14,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last",
                "max"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "rate(entry_pipeline_otel_trace_source_payloadSize_sum{instance=~\"$instance\"}[$__rate_interval]) / rate(entry_pipeline_otel_trace_source_payloadSize_count{instance=~\"$instance\"}[$__rate_interval])",
              "legendFormat": "Avg Payload Size",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "entry_pipeline_otel_trace_source_payloadSize_max{instance=~\"$instance\"}",
              "hide": false,
              "legendFormat": "Max Payload Size",
              "refId": "B"
            }
          ],
          "title": "OTel Source Payload Size",
          "type": "timeseries"
        }
      ],
      "title": "📥 OTel Source Metrics",
      "type": "row"
    },
    {
      "collapsed": true,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 12
      },
      "id": 105,
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
                    "color": "orange",
                    "value": 10000
                  },
                  {
                    "color": "red",
                    "value": 50000
                  }
                ]
              },
              "unit": "short"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 6,
            "x": 0,
            "y": 13
          },
          "id": 15,
          "options": {
            "orientation": "auto",
            "reduceOptions": {
              "calcs": [
                "lastNotNull"
              ],
              "fields": "",
              "values": false
            },
            "showThresholdLabels": false,
            "showThresholdMarkers": true,
            "text": {}
          },
          "pluginVersion": "9.2.5",
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "service_map_pipeline_service_map_stateful_spansDbSize{instance=~\"$instance\"}",
              "instant": true,
              "refId": "A"
            }
          ],
          "title": "Service Map Spans DB Size",
          "type": "gauge"
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
                    "color": "orange",
                    "value": 1000
                  },
                  {
                    "color": "red",
                    "value": 5000
                  }
                ]
              },
              "unit": "short"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 6,
            "x": 6,
            "y": 13
          },
          "id": 16,
          "options": {
            "orientation": "auto",
            "reduceOptions": {
              "calcs": [
                "lastNotNull"
              ],
              "fields": "",
              "values": false
            },
            "showThresholdLabels": false,
            "showThresholdMarkers": true,
            "text": {}
          },
          "pluginVersion": "9.2.5",
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "service_map_pipeline_service_map_stateful_traceGroupDbSize{instance=~\"$instance\"}",
              "instant": true,
              "refId": "A"
            }
          ],
          "title": "Service Map Trace Groups DB Size",
          "type": "gauge"
        }
      ],
      "title": "🗺️ Service Map",
      "type": "row"
    },
    {
      "collapsed": true,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 13
      },
      "id": 106,
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 15,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
                "pointSize": 5,
                "scaleDistribution": {
                  "type": "linear"
                },
                "showPoints": "auto",
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
              "unit": "reqps"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 12,
            "x": 0,
            "y": 14
          },
          "id": 18,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "rate(core_peerForwarder_requests_total{instance=~\"$instance\"}[$__rate_interval])",
              "legendFormat": "Total Requests",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(core_peerForwarder_badRequests_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Bad Requests",
              "refId": "B"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(core_peerForwarder_requestsTooLarge_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Too Large",
              "refId": "C"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(core_peerForwarder_requestsUnprocessable_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Unprocessable",
              "refId": "D"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(core_peerForwarder_requestTimeouts_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Timeouts",
              "refId": "E"
            }
          ],
          "title": "Peer Forwarder Requests (rate)",
          "type": "timeseries"
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                  }
                ]
              },
              "unit": "s"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 12,
            "x": 12,
            "y": 14
          },
          "id": 19,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last",
                "max"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "rate(core_peerForwarder_clientRequestForwardingLatency_seconds_sum{instance=~\"$instance\"}[$__rate_interval]) / rate(core_peerForwarder_clientRequestForwardingLatency_seconds_count{instance=~\"$instance\"}[$__rate_interval])",
              "legendFormat": "Client Forwarding Latency (Avg)",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(core_peerForwarder_serverRequestProcessingLatency_seconds_sum{instance=~\"$instance\"}[$__rate_interval]) / rate(core_peerForwarder_serverRequestProcessingLatency_seconds_count{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Server Processing Latency (Avg)",
              "refId": "C"
            }
          ],
          "title": "Peer Forwarder Latency",
          "type": "timeseries"
        }
      ],
      "title": "🔀 Peer Forwarder",
      "type": "row"
    },
    {
      "collapsed": true,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 14
      },
      "id": 107,
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                  }
                ]
              },
              "unit": "short"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 12,
            "x": 0,
            "y": 15
          },
          "id": 20,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last",
                "max"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "armeria_executor_active_threads{instance=~\"$instance\"}",
              "legendFormat": "Active Threads - {{name}}",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "armeria_executor_pool_size_threads{instance=~\"$instance\"}",
              "hide": false,
              "legendFormat": "Pool Size - {{name}}",
              "refId": "B"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "armeria_executor_pool_max_threads{instance=~\"$instance\"}",
              "hide": false,
              "legendFormat": "Max Pool - {{name}}",
              "refId": "C"
            }
          ],
          "title": "Armeria Executor Thread Pool",
          "type": "timeseries"
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
                "axisBorderShow": false,
                "axisCenteredZero": false,
                "axisColorMode": "text",
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "legend": false,
                  "tooltip": false,
                  "viz": false
                },
                "insertNulls": false,
                "lineInterpolation": "linear",
                "lineWidth": 1,
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
                  }
                ]
              },
              "unit": "short"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 8,
            "w": 12,
            "x": 12,
            "y": 15
          },
          "id": 21,
          "options": {
            "legend": {
              "calcs": [
                "mean",
                "last"
              ],
              "displayMode": "table",
              "placement": "bottom",
              "showLegend": true
            },
            "tooltip": {
              "mode": "multi",
              "sort": "none"
            }
          },
          "targets": [
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "editorMode": "code",
              "expr": "armeria_executor_queued_tasks{instance=~\"$instance\"}",
              "legendFormat": "Queued Tasks - {{name}}",
              "refId": "A"
            },
            {
              "datasource": {
                "type": "prometheus",
                "uid": "${datasource}"
              },
              "expr": "rate(armeria_executor_completed_tasks_total{instance=~\"$instance\"}[$__rate_interval])",
              "hide": false,
              "legendFormat": "Completed Rate - {{name}}",
              "refId": "B"
            }
          ],
          "title": "Armeria Executor Tasks",
          "type": "timeseries"
        }
      ],
      "title": "⚙️ Armeria Server",
      "type": "row"
    }
  ],
  "refresh": "30s",
  "schemaVersion": 37,
  "style": "dark",
  "tags": [
    "data-prepper",
    "opensearch",
    "otel"
  ],
  "templating": {
    "list": [
      {
        "current": {
          "selected": true,
          "text": "Prometheus",
          "value": "Prometheus"
        },
        "hide": 0,
        "includeAll": false,
        "label": "Datasource",
        "multi": false,
        "name": "datasource",
        "options": [],
        "query": "prometheus",
        "queryValue": "",
        "refresh": 1,
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
        "datasource": {
          "type": "prometheus",
          "uid": "${datasource}"
        },
        "definition": "label_values(process_cpu_usage, instance)",
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
  "timezone": "browser",
  "title": "Data Prepper Monitoring",
  "uid": "data-prepper-dashboard",
  "version": 7,
  "weekStart": ""
}
```

---

### Описание секций дашборда

Дашборд разделен на несколько логических секций (строк), которые можно сворачивать для удобства.

#### 📊 **Overview (Общая сводка)**
Здесь собраны самые важные метрики для быстрой оценки состояния сервиса.
- **CPU Usage**: Загрузка процессора. Помогает понять, не перегружен ли инстанс.
- **Ingress Request Rate**: Количество входящих запросов в секунду (полученных и успешно обработанных). Показывает общую нагрузку на сервис.
- **Ingress Request Duration**: Средняя и максимальная продолжительность обработки входящих запросов. Помогает отслеживать деградацию производительности.

#### 🔄 **Pipeline Processing (Обработка в пайплайнах)**
Этот раздел показывает, как данные проходят через различные стадии обработки.
- **Records Processed per Pipeline**: Скорость обработки записей (в rec/sec) в каждом из трех основных пайплайнов (`entry`, `raw`, `service_map`). Позволяет увидеть, где может быть "бутылочное горлышко".
- **Service Map Processor Records In/Out**: Показывает, сколько данных входит и выходит из stateful-компонента обработки карты сервисов.

#### 📦 **Buffer Metrics (Метрики буферов)**
Буферы — критически важная часть для сглаживания пиковых нагрузок. Проблемы с ними могут привести к потере данных.
- **Buffer Usage**: Процент заполнения буфера для каждого пайплайна. **Это одна из самых важных панелей.** Если буфер постоянно близок к 100%, это означает, что последующий компонент (например, OpenSearch) не справляется с потоком данных.
- **Records in Buffer/Flight**: Абсолютное количество записей в буфере и "в полете" (уже отправленных, но еще не подтвержденных).
- **Buffer Write Timeouts**: Количество таймаутов при записи в буфер. Ненулевое значение — плохой знак, указывающий на переполнение.

#### 🔍 **OpenSearch Sink (Отправка в OpenSearch)**
Метрики, связанные с конечной точкой отправки данных.
- **OpenSearch Documents (rate)**: Скорость успешной индексации документов и количество ошибок на уровне документов.
- **OpenSearch Bulk Latency**: Средняя задержка при выполнении bulk-запросов к OpenSearch. Рост этого показателя может говорить о проблемах с кластером OpenSearch.
- **OpenSearch Bulk Errors (rate)**: Количество ошибок на уровне всего bulk-запроса (например, из-за проблем с сетью или недоступности OpenSearch).

#### 📥 **OTel Source Metrics (Метрики источника OTel)**
Детальная информация о входящих запросах от OpenTelemetry коллекторов.
- **OTel Source Request Status**: Разбивка входящих запросов по статусам (успех, неверный запрос, слишком большой запрос, таймаут, внутренняя ошибка). Помогает диагностировать проблемы на стороне клиентов.
- **OTel Source Payload Size**: Средний и максимальный размер входящих запросов.

#### 🗺️ **Service Map (Карта сервисов)**
Специфичные метрики для компонента, который строит карту сервисов.
- **Service Map Spans/Trace Groups DB Size**: Размер внутренних баз данных (в памяти) для хранения информации о спанах и группах трейсов. Помогает контролировать потребление памяти.

#### 🔀 **Peer Forwarder (Перенаправление между узлами)**
Метрики для кластерного режима, когда один узел может перенаправлять данные другому.
- **Peer Forwarder Requests**: Статистика по перенаправленным запросам и ошибкам.
- **Peer Forwarder Latency**: Задержки, связанные с перенаправлением данных.

#### ⚙️ **Armeria Server (Внутренние метрики сервера)**
Низкоуровневые метрики веб-сервера Armeria, на котором работает Data Prepper. Полезны для глубокой диагностики.
- **Armeria Executor Thread Pool**: Использование пула потоков (активные, размер, максимум). Помогает понять, хватает ли ресурсов для обработки запросов.
- **Armeria Executor Tasks**: Количество задач в очереди и скорость их выполнения.

### Как использовать

1.  **Импорт**: В Grafana перейдите в `+` (Create) -> `Import`. Вставьте JSON-код выше.
2.  **Выбор DataSource**: Выберите ваш Prometheus datasource, из которого собираются метрики.
3.  **Фильтрация**: Вверху дашборда есть переменная `Instance`, которая позволяет выбрать один или несколько инстансов Data Prepper для отображения.
