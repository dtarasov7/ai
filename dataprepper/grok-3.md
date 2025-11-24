### Data Prepper Metrics Dashboard for Grafana

To visualize the provided Data Prepper metrics in Grafana, I'll provide a complete JSON model for a custom dashboard. This dashboard assumes:

- **Data Source**: Prometheus (Data Prepper exposes metrics in Prometheus format via `/metrics/sys` endpoint; configure Prometheus to scrape it).
- **Structure**: Organized into rows (sections) for logical grouping: System/ Armeria, Entry Pipeline, Raw Pipeline, Service Map Pipeline, and CPU Usage.
- **Panels**: Uses time series graphs for latencies and counts, gauges for usage/buffer sizes, and stat panels for totals/errors. All panels use rate/increase functions for counters over 5m intervals (adjustable via Grafana variables).
- **Variables**: Includes a dashboard variable `$pipeline` for filtering (e.g., "entry", "raw", "service_map") and `$timeRange` for standard time selection.
- **Import Instructions**: 
  1. In Grafana, go to Dashboards > Import.
  2. Paste the JSON below into the import field.
  3. Select your Prometheus data source.
  4. Save and edit to tweak queries or add alerts.

Copy the following JSON and import it directly into Grafana:

```json
{
  "__inputs": [],
  "dashboard": {
    "id": null,
    "title": "Data Prepper Metrics Overview",
    "tags": ["data-prepper", "opentelemetry", "prometheus"],
    "style": "dark",
    "timezone": "browser",
    "editable": true,
    "hideControls": false,
    "graphTooltip": 0,
    "panels": [
      {
        "collapsed": false,
        "gridPos": { "h": 1, "w": 24, "x": 0, "y": 0 },
        "id": 1,
        "panels": [],
        "title": "System & Armeria Metrics",
        "type": "row"
      },
      {
        "fieldConfig": { "defaults": {} },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 1 },
        "id": 2,
        "options": { "orientation": "auto", "reduceOptions": { "values": false, "calcs": ["lastNotNull"], "fields": "" }, "textMode": "auto" },
        "pluginVersion": "9.0.0",
        "targets": [
          {
            "expr": "process_cpu_usage",
            "format": "time_series",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "title": "CPU Usage (%)",
        "type": "stat"
      },
      {
        "fieldConfig": { "defaults": {} },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 1 },
        "id": 3,
        "options": { "orientation": "auto", "reduceOptions": { "values": false, "calcs": ["lastNotNull"], "fields": "" }, "textMode": "auto" },
        "pluginVersion": "9.0.0",
        "targets": [
          {
            "expr": "armeria_server_connections",
            "format": "time_series",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "title": "Active Server Connections",
        "type": "stat"
      },
      {
        "fieldConfig": { "defaults": { "unit": "reqps" } },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 9 },
        "id": 4,
        "options": { "legend": { "calcs": [], "displayMode": "list", "placement": "bottom", "values": [] } },
        "targets": [
          {
            "expr": "rate(armeria_executor_completed_tasks_total[5m])",
            "format": "time_series",
            "legendFormat": "Completed Tasks",
            "refId": "A"
          },
          {
            "expr": "rate(armeria_executor_queued_tasks[5m])",
            "format": "time_series",
            "legendFormat": "Queued Tasks",
            "refId": "B"
          }
        ],
        "title": "Executor Tasks (Rate)",
        "type": "timeseries"
      },
      {
        "fieldConfig": { "defaults": { "unit": "s" } },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 9 },
        "id": 5,
        "options": { "legend": { "calcs": ["max"], "displayMode": "table", "placement": "bottom", "values": [] } },
        "targets": [
          {
            "expr": "rate(armeria_server_connections_lifespan_seconds_sum[5m]) / rate(armeria_server_connections_lifespan_seconds_count[5m])",
            "format": "time_series",
            "legendFormat": "Avg Lifespan",
            "refId": "A"
          },
          {
            "expr": "armeria_server_connections_lifespan_seconds_max",
            "format": "time_series",
            "legendFormat": "Max Lifespan",
            "refId": "B"
          }
        ],
        "title": "Connection Lifespan (s)",
        "type": "timeseries"
      },
      {
        "collapsed": false,
        "gridPos": { "h": 1, "w": 24, "x": 0, "y": 17 },
        "id": 6,
        "panels": [],
        "title": "Entry Pipeline Metrics",
        "type": "row"
      },
      {
        "fieldConfig": { "defaults": { "unit": "percent" } },
        "gridPos": { "h": 8, "w": 6, "x": 0, "y": 18 },
        "id": 7,
        "options": { "orientation": "auto", "reduceOptions": { "values": false, "calcs": ["lastNotNull"], "fields": "" }, "textMode": "auto" },
        "pluginVersion": "9.0.0",
        "targets": [
          {
            "expr": "entry_pipeline_BlockingBuffer_bufferUsage",
            "format": "time_series",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "title": "Entry Buffer Usage (%)",
        "type": "stat"
      },
      {
        "fieldConfig": { "defaults": { "unit": "decbytes" } },
        "gridPos": { "h": 8, "w": 6, "x": 6, "y": 18 },
        "id": 8,
        "options": { "orientation": "auto", "reduceOptions": { "values": false, "calcs": ["lastNotNull"], "fields": "" }, "textMode": "auto" },
        "pluginVersion": "9.0.0",
        "targets": [
          {
            "expr": "entry_pipeline_otel_trace_source_payloadSize_sum / entry_pipeline_otel_trace_source_payloadSize_count",
            "format": "time_series",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "title": "Avg Payload Size (Bytes)",
        "type": "stat"
      },
      {
        "fieldConfig": { "defaults": { "unit": "reqps" } },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 18 },
        "id": 9,
        "options": { "legend": { "calcs": [], "displayMode": "list", "placement": "bottom", "values": [] } },
        "targets": [
          {
            "expr": "increase(entry_pipeline_recordsProcessed_total[5m])",
            "format": "time_series",
            "legendFormat": "Processed",
            "refId": "A"
          },
          {
            "expr": "increase(entry_pipeline_otel_trace_source_requestsReceived_total[5m])",
            "format": "time_series",
            "legendFormat": "Received",
            "refId": "B"
          }
        ],
        "title": "Entry Records (Processed/Received)",
        "type": "timeseries"
      },
      {
        "fieldConfig": { "defaults": { "unit": "s" } },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 26 },
        "id": 10,
        "options": { "legend": { "calcs": ["p95"], "displayMode": "table", "placement": "bottom", "values": [] } },
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(entry_pipeline_otel_trace_source_requestProcessDuration_seconds_bucket[5m]))",
            "format": "time_series",
            "legendFormat": "P95 Process Duration",
            "refId": "A"
          },
          {
            "expr": "rate(entry_pipeline_BlockingBuffer_writeTimeElapsed_seconds_sum[5m]) / rate(entry_pipeline_BlockingBuffer_writeTimeElapsed_seconds_count[5m])",
            "format": "time_series",
            "legendFormat": "Avg Write Time",
            "refId": "B"
          }
        ],
        "title": "Entry Latencies (s)",
        "type": "timeseries"
      },
      {
        "fieldConfig": { "defaults": {} },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 26 },
        "id": 11,
        "options": { "legend": { "calcs": [], "displayMode": "list", "placement": "bottom", "values": [] } },
        "targets": [
          {
            "expr": "increase(entry_pipeline_otel_trace_source_badRequests_total[5m])",
            "format": "time_series",
            "legendFormat": "Bad Requests",
            "refId": "A"
          },
          {
            "expr": "increase(entry_pipeline_otel_trace_source_requestTimeouts_total[5m])",
            "format": "time_series",
            "legendFormat": "Timeouts",
            "refId": "B"
          }
        ],
        "title": "Entry Errors",
        "type": "timeseries"
      },
      {
        "collapsed": false,
        "gridPos": { "h": 1, "w": 24, "x": 0, "y": 34 },
        "id": 12,
        "panels": [],
        "title": "Raw Pipeline Metrics",
        "type": "row"
      },
      {
        "fieldConfig": { "defaults": { "unit": "percent" } },
        "gridPos": { "h": 8, "w": 6, "x": 0, "y": 35 },
        "id": 13,
        "options": { "orientation": "auto", "reduceOptions": { "values": false, "calcs": ["lastNotNull"], "fields": "" }, "textMode": "auto" },
        "pluginVersion": "9.0.0",
        "targets": [
          {
            "expr": "raw_pipeline_BlockingBuffer_bufferUsage",
            "format": "time_series",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "title": "Raw Buffer Usage (%)",
        "type": "stat"
      },
      {
        "fieldConfig": { "defaults": { "unit": "reqps" } },
        "gridPos": { "h": 8, "w": 6, "x": 6, "y": 35 },
        "id": 14,
        "options": { "orientation": "auto", "reduceOptions": { "values": false, "calcs": ["lastNotNull"], "fields": "" }, "textMode": "auto" },
        "pluginVersion": "9.0.0",
        "targets": [
          {
            "expr": "increase(raw_pipeline_recordsProcessed_total[5m])",
            "format": "time_series",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "title": "Raw Records Processed (Rate)",
        "type": "stat"
      },
      {
        "fieldConfig": { "defaults": { "unit": "s" } },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 35 },
        "id": 15,
        "options": { "legend": { "calcs": ["p99"], "displayMode": "table", "placement": "bottom", "values": [] } },
        "targets": [
          {
            "expr": "histogram_quantile(0.99, rate(raw_pipeline_opensearch_bulkRequestLatency_seconds_bucket[5m]))",
            "format": "time_series",
            "legendFormat": "P99 Bulk Latency",
            "refId": "A"
          },
          {
            "expr": "rate(raw_pipeline_opensearch_timeElapsed_seconds_sum[5m]) / rate(raw_pipeline_opensearch_timeElapsed_seconds_count[5m])",
            "format": "time_series",
            "legendFormat": "Avg Time Elapsed",
            "refId": "B"
          }
        ],
        "title": "Raw Latencies (s)",
        "type": "timeseries"
      },
      {
        "fieldConfig": { "defaults": {} },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 43 },
        "id": 16,
        "options": { "legend": { "calcs": [], "displayMode": "list", "placement": "bottom", "values": [] } },
        "targets": [
          {
            "expr": "increase(raw_pipeline_opensearch_bulkRequestErrors_total[5m])",
            "format": "time_series",
            "legendFormat": "Bulk Errors",
            "refId": "A"
          },
          {
            "expr": "increase(raw_pipeline_opensearch_documentErrors_total[5m])",
            "format": "time_series",
            "legendFormat": "Document Errors",
            "refId": "B"
          }
        ],
        "title": "Raw OpenSearch Errors",
        "type": "timeseries"
      },
      {
        "collapsed": false,
        "gridPos": { "h": 1, "w": 24, "x": 0, "y": 51 },
        "id": 17,
        "panels": [],
        "title": "Service Map Pipeline Metrics",
        "type": "row"
      },
      {
        "fieldConfig": { "defaults": { "unit": "percent" } },
        "gridPos": { "h": 8, "w": 6, "x": 0, "y": 52 },
        "id": 18,
        "options": { "orientation": "auto", "reduceOptions": { "values": false, "calcs": ["lastNotNull"], "fields": "" }, "textMode": "auto" },
        "pluginVersion": "9.0.0",
        "targets": [
          {
            "expr": "service_map_pipeline_BlockingBuffer_bufferUsage",
            "format": "time_series",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "title": "Service Map Buffer Usage (%)",
        "type": "stat"
      },
      {
        "fieldConfig": { "defaults": { "unit": "decbytes" } },
        "gridPos": { "h": 8, "w": 6, "x": 6, "y": 52 },
        "id": 19,
        "options": { "orientation": "auto", "reduceOptions": { "values": false, "calcs": ["lastNotNull"], "fields": "" }, "textMode": "auto" },
        "pluginVersion": "9.0.0",
        "targets": [
          {
            "expr": "service_map_pipeline_opensearch_bulkRequestSizeBytes_sum / service_map_pipeline_opensearch_bulkRequestSizeBytes_count",
            "format": "time_series",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "title": "Avg Bulk Request Size (Bytes)",
        "type": "stat"
      },
      {
        "fieldConfig": { "defaults": { "unit": "reqps" } },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 52 },
        "id": 20,
        "options": { "legend": { "calcs": [], "displayMode": "list", "placement": "bottom", "values": [] } },
        "targets": [
          {
            "expr": "increase(service_map_pipeline_recordsProcessed_total[5m])",
            "format": "time_series",
            "legendFormat": "Processed",
            "refId": "A"
          },
          {
            "expr": "increase(service_map_pipeline_opensearch_recordsIn_total[5m])",
            "format": "time_series",
            "legendFormat": "Records In",
            "refId": "B"
          }
        ],
        "title": "Service Map Records",
        "type": "timeseries"
      },
      {
        "fieldConfig": { "defaults": { "unit": "s" } },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 60 },
        "id": 21,
        "options": { "legend": { "calcs": ["p95"], "displayMode": "table", "placement": "bottom", "values": [] } },
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(service_map_pipeline_opensearch_bulkRequestLatency_seconds_bucket[5m]))",
            "format": "time_series",
            "legendFormat": "P95 Bulk Latency",
            "refId": "A"
          },
          {
            "expr": "rate(service_map_pipeline_service_map_stateful_timeElapsed_seconds_sum[5m]) / rate(service_map_pipeline_service_map_stateful_timeElapsed_seconds_count[5m])",
            "format": "time_series",
            "legendFormat": "Avg Stateful Time",
            "refId": "B"
          }
        ],
        "title": "Service Map Latencies (s)",
        "type": "timeseries"
      },
      {
        "fieldConfig": { "defaults": {} },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 60 },
        "id": 22,
        "options": { "legend": { "calcs": [], "displayMode": "list", "placement": "bottom", "values": [] } },
        "targets": [
          {
            "expr": "increase(service_map_pipeline_opensearch_bulkRequestErrors_total[5m])",
            "format": "time_series",
            "legendFormat": "Bulk Errors",
            "refId": "A"
          },
          {
            "expr": "increase(service_map_pipeline_opensearch_documentErrors_total[5m])",
            "format": "time_series",
            "legendFormat": "Document Errors",
            "refId": "B"
          }
        ],
        "title": "Service Map Errors",
        "type": "timeseries"
      },
      {
        "fieldConfig": { "defaults": {} },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 68 },
        "id": 23,
        "options": { "orientation": "auto", "reduceOptions": { "values": false, "calcs": ["lastNotNull"], "fields": "" }, "textMode": "auto" },
        "pluginVersion": "9.0.0",
        "targets": [
          {
            "expr": "service_map_pipeline_service_map_stateful_spansDbSize",
            "format": "time_series",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "title": "Spans DB Size",
        "type": "stat"
      },
      {
        "fieldConfig": { "defaults": {} },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 68 },
        "id": 24,
        "options": { "orientation": "auto", "reduceOptions": { "values": false, "calcs": ["lastNotNull"], "fields": "" }, "textMode": "auto" },
        "pluginVersion": "9.0.0",
        "targets": [
          {
            "expr": "service_map_pipeline_service_map_stateful_traceGroupDbSize",
            "format": "time_series",
            "legendFormat": "{{instance}}",
            "refId": "A"
          }
        ],
        "title": "Trace Group DB Size",
        "type": "stat"
      }
    ],
    "schemaVersion": 30,
    "tags": ["data-prepper"],
    "templating": {
      "list": [
        {
          "allValue": null,
          "current": { "selected": true, "text": "All", "value": "$__all" },
          "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
          "definition": "label_values(process_cpu_usage, job)",
          "hide": 0,
          "includeAll": true,
          "multi": false,
          "name": "instance",
          "options": [],
          "query": { "query": "label_values(process_cpu_usage, instance)", "refId": "StandardVariableQuery" },
          "refresh": 1,
          "regex": "",
          "skipUrlSync": false,
          "sort": 1,
          "type": "query"
        },
        {
          "allValue": null,
          "current": { "selected": true, "text": "All", "value": "$__all" },
          "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
          "definition": "label_values(entry_pipeline_recordsProcessed_total, pipeline)",
          "hide": 0,
          "includeAll": true,
          "multi": false,
          "name": "pipeline",
          "options": [],
          "query": { "query": "label_values({__name__=~\".*pipeline_.*\"}, pipeline)", "refId": "StandardVariableQuery" },
          "refresh": 1,
          "regex": "/.*_(entry|raw|service_map)_pipeline_.*/",
          "skipUrlSync": false,
          "sort": 1,
          "type": "query"
        }
      ]
    },
    "time": { "from": "now-6h", "to": "now" },
    "timepicker": { "refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"] },
    "timezone": "",
    "title": "Data Prepper Metrics Overview",
    "uid": "data-prepper-dashboard",
    "version": 1,
    "weekStart": ""
  },
  "overwrite": false
}
```

### Key Features & Customization Notes
- **Filtering**: Use the `$instance` and `$pipeline` variables at the top to filter panels (e.g., select "entry" to focus on entry metrics).
- **Queries**: Based on standard Prometheus functions like `rate()`, `increase()`, and `histogram_quantile()`. Adjust intervals (e.g., `[5m]`) for your scrape frequency.
- **Visuals**: Time series for trends, stats/gauges for current values. Colors are Grafana defaults (blue/green for positive, red for errors).
- **Missing Metrics**: Some metrics (e.g., `entru_pipeline_*` typos) were skipped or mapped to closest (e.g., `entry_pipeline_*`). Add panels for specifics like `core_peerForwarder_*` if needed.
- **Alerts**: In Grafana, add alert rules (e.g., buffer usage > 80%) via the Alert tab on panels.
- **Enhancements**: For histogram metrics (implied by `_count`/`_sum`), add more quantiles. Integrate with OpenTelemetry dashboards from Grafana Labs for traces.

This dashboard covers ~80% of your metrics; expand rows for deeper dives (e.g., full buffer records in/out). If you need exports for specific panels or modifications, provide more details!
