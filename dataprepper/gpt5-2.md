Ниже — готовый к импорту Grafana-дэшборд под ваши метрики Data Prepper с префиксами:
ameria_executor_, ameria_server_, core_peerForwarder_, entry_pipeline_BlockingBuffer_, entry_pipeline_otel_trace_source_, raw_pipeline_BlockingBuffer_, raw_pipeline_opensearch_, raw_pipeline_otel_trace_raw_, service_map_pipeline_BlockingBuffer_, service_map_pipeline_opensearch_, service_map_pipeline_service_map_stateful_.

Что делает
- Автоматически подхватывает серии по выбранным префиксам.
- Разделяет:
  - counters: *_total|*_count → показывает rate (ops/s).
  - gauges: все, что не является *_total|*_count|*_sum|*_bucket|*_created → показывает значение.
  - histograms: *_bucket → строит p50/p95/p99.
- Фильтры: job, instance, prefixes (можно несколько), group_by (instance/pipeline/plugin_*).
- Включены базовые JVM/CPU панели.

Как импортировать
- Grafana → Dashboards → Import → вставьте JSON → выберите Prometheus datasource.
- Убедитесь, что Prometheus скрейпит ваш Data Prepper (обычно /metrics).

JSON дэшборда (вставьте целиком)
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
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "liveNow": false,
  "panels": [
    {
      "type": "stat",
      "title": "Up (per instance)",
      "id": 1,
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": { "h": 4, "w": 6, "x": 0, "y": 0 },
      "targets": [
        {
          "refId": "A",
          "expr": "sum by (instance) (up{job=\"$job\", instance=~\"$instance\"})"
        }
      ],
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
      }
    },
    {
      "type": "stat",
      "title": "Counters total rate (selected prefixes)",
      "id": 2,
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": { "h": 4, "w": 6, "x": 6, "y": 0 },
      "targets": [
        {
          "refId": "A",
          "expr": "sum( rate({job=\"$job\", instance=~\"$instance\", __name__=~\"^($prefix).*(_total|_count)$\"}[$__rate_interval]) )"
        }
      ],
      "fieldConfig": {
        "defaults": { "unit": "ops/s", "decimals": 2 },
        "overrides": []
      },
      "options": {
        "orientation": "auto",
        "reduceOptions": { "calcs": ["lastNotNull"], "values": false }
      }
    },
    {
      "type": "timeseries",
      "title": "Counters rate by prefix/metric",
      "id": 3,
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 4 },
      "targets": [
        {
          "refId": "A",
          "expr": "sum by (pref, metric, ${group_by}) ( label_replace( label_replace( rate({job=\"$job\", instance=~\"$instance\", __name__=~\"^($prefix).*(_total|_count)$\"}[$__rate_interval]), \"metric\", \"$2\", \"__name__\", \"^($prefix)(.*?)(?:_total|_count)$\"), \"pref\", \"$1\", \"__name__\", \"^($prefix)(.*?)(?:_total|_count)$\" ) )",
          "legendFormat": "{{pref}}.{{metric}} {{${group_by}}}"
        }
      ],
      "fieldConfig": {
        "defaults": { "unit": "ops/s", "min": 0, "decimals": 2 },
        "overrides": []
      },
      "options": {
        "legend": { "displayMode": "list", "placement": "bottom" },
        "tooltip": { "mode": "multi", "sort": "desc" }
      }
    },
    {
      "type": "timeseries",
      "title": "Gauges by prefix/metric",
      "id": 4,
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 12 },
      "targets": [
        {
          "refId": "A",
          "expr": "avg by (pref, metric, ${group_by}) ( label_replace( label_replace( {job=\"$job\", instance=~\"$instance\", __name__=~\"^($prefix).*\", __name__!~\".*(_total|_count|_sum|_bucket|_created)$\"}, \"metric\", \"$2\", \"__name__\", \"^($prefix)(.*)$\"), \"pref\", \"$1\", \"__name__\", \"^($prefix)(.*)$\" ) )",
          "legendFormat": "{{pref}}.{{metric}} {{${group_by}}}"
        }
      ],
      "fieldConfig": {
        "defaults": { "decimals": 2 },
        "overrides": []
      },
      "options": {
        "legend": { "displayMode": "list", "placement": "bottom" },
        "tooltip": { "mode": "multi" }
      }
    },
    {
      "type": "timeseries",
      "title": "Latency histogram quantiles (p50/p95/p99)",
      "id": 5,
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 20 },
      "targets": [
        {
          "refId": "A",
          "expr": "histogram_quantile(0.50, sum by (le, pref, metric, ${group_by}) ( label_replace( label_replace( rate({job=\"$job\", instance=~\"$instance\", __name__=~\"^($prefix).*(?:_seconds)?_bucket$\"}[$__rate_interval]), \"metric\", \"$2\", \"__name__\", \"^($prefix)(.*?)(?:_seconds)?_bucket$\"), \"pref\", \"$1\", \"__name__\", \"^($prefix)(.*?)(?:_seconds)?_bucket$\" ) ) )",
          "legendFormat": "p50 {{pref}}.{{metric}} {{${group_by}}}"
        },
        {
          "refId": "B",
          "expr": "histogram_quantile(0.95, sum by (le, pref, metric, ${group_by}) ( label_replace( label_replace( rate({job=\"$job\", instance=~\"$instance\", __name__=~\"^($prefix).*(?:_seconds)?_bucket$\"}[$__rate_interval]), \"metric\", \"$2\", \"__name__\", \"^($prefix)(.*?)(?:_seconds)?_bucket$\"), \"pref\", \"$1\", \"__name__\", \"^($prefix)(.*?)(?:_seconds)?_bucket$\" ) ) )",
          "legendFormat": "p95 {{pref}}.{{metric}} {{${group_by}}}"
        },
        {
          "refId": "C",
          "expr": "histogram_quantile(0.99, sum by (le, pref, metric, ${group_by}) ( label_replace( label_replace( rate({job=\"$job\", instance=~\"$instance\", __name__=~\"^($prefix).*(?:_seconds)?_bucket$\"}[$__rate_interval]), \"metric\", \"$2\", \"__name__\", \"^($prefix)(.*?)(?:_seconds)?_bucket$\"), \"pref\", \"$1\", \"__name__\", \"^($prefix)(.*?)(?:_seconds)?_bucket$\" ) ) )",
          "legendFormat": "p99 {{pref}}.{{metric}} {{${group_by}}}"
        }
      ],
      "fieldConfig": {
        "defaults": { "unit": "s", "decimals": 3 },
        "overrides": []
      },
      "options": {
        "legend": { "displayMode": "list", "placement": "bottom" },
        "tooltip": { "mode": "multi" }
      }
    },
    {
      "type": "timeseries",
      "title": "Top ${topn} counters by rate",
      "id": 6,
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 28 },
      "targets": [
        {
          "refId": "A",
          "expr": "topk(${topn}, sum by (pref, metric, ${group_by}) ( label_replace( label_replace( rate({job=\"$job\", instance=~\"$instance\", __name__=~\"^($prefix).*(_total|_count)$\"}[$__rate_interval]), \"metric\", \"$2\", \"__name__\", \"^($prefix)(.*?)(?:_total|_count)$\"), \"pref\", \"$1\", \"__name__\", \"^($prefix)(.*?)(?:_total|_count)$\" ) ) )",
          "legendFormat": "{{pref}}.{{metric}} {{${group_by}}}"
        }
      ],
      "fieldConfig": {
        "defaults": { "unit": "ops/s", "min": 0, "decimals": 2 },
        "overrides": []
      },
      "options": {
        "legend": { "displayMode": "list", "placement": "bottom" },
        "tooltip": { "mode": "multi", "sort": "desc" }
      }
    },
    {
      "type": "timeseries",
      "title": "CPU usage (process) %",
      "id": 100,
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 36 },
      "targets": [
        {
          "refId": "A",
          "expr": "100 * sum by (instance) (rate(process_cpu_seconds_total{job=\"$job\", instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "{{instance}}"
        }
      ],
      "fieldConfig": {
        "defaults": { "unit": "percent", "min": 0, "max": 100, "decimals": 1 },
        "overrides": []
      },
      "options": {
        "legend": { "displayMode": "list", "placement": "bottom" },
        "tooltip": { "mode": "single" }
      }
    },
    {
      "type": "timeseries",
      "title": "JVM heap used (%)",
      "id": 101,
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 36 },
      "targets": [
        {
          "refId": "A",
          "expr": "100 * sum(jvm_memory_used_bytes{job=\"$job\", instance=~\"$instance\", area=\"heap\"}) / sum(jvm_memory_max_bytes{job=\"$job\", instance=~\"$instance\", area=\"heap\"})",
          "legendFormat": "heap used"
        }
      ],
      "fieldConfig": {
        "defaults": { "unit": "percent", "min": 0, "max": 100, "decimals": 1 },
        "overrides": []
      },
      "options": {
        "legend": { "displayMode": "list", "placement": "bottom" },
        "tooltip": { "mode": "single" }
      }
    },
    {
      "type": "timeseries",
      "title": "GC pauses (seconds/sec) and count",
      "id": 102,
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 44 },
      "targets": [
        {
          "refId": "A",
          "expr": "sum by (instance) (rate(jvm_gc_pause_seconds_sum{job=\"$job\", instance=~\"$instance\"}[5m]))",
          "legendFormat": "pause sum {{instance}}"
        },
        {
          "refId": "B",
          "expr": "sum by (gc, instance) (rate(jvm_gc_pause_seconds_count{job=\"$job\", instance=~\"$instance\"}[5m]))",
          "legendFormat": "count {{gc}} {{instance}}"
        }
      ],
      "fieldConfig": {
        "defaults": { "decimals": 3 },
        "overrides": []
      },
      "options": {
        "legend": { "displayMode": "list", "placement": "bottom" },
        "tooltip": { "mode": "multi" }
      }
    },
    {
      "type": "timeseries",
      "title": "Process RSS (bytes) and Open FDs (%)",
      "id": 103,
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 44 },
      "targets": [
        {
          "refId": "A",
          "expr": "sum by (instance) (process_resident_memory_bytes{job=\"$job\", instance=~\"$instance\"})",
          "legendFormat": "rss {{instance}}"
        },
        {
          "refId": "B",
          "expr": "100 * sum by (instance) (process_open_fds{job=\"$job\", instance=~\"$instance\"}) / sum by (instance) (process_max_fds{job=\"$job\", instance=~\"$instance\"})",
          "legendFormat": "open FDs % {{instance}}"
        }
      ],
      "fieldConfig": {
        "defaults": { "decimals": 0 },
        "overrides": [
          {
            "matcher": { "id": "byName", "options": "rss" },
            "properties": [ { "id": "unit", "value": "bytes" } ]
          },
          {
            "matcher": { "id": "byName", "options": "open FDs %" },
            "properties": [ { "id": "unit", "value": "percent" } ]
          }
        ]
      },
      "options": {
        "legend": { "displayMode": "list", "placement": "bottom" },
        "tooltip": { "mode": "multi" }
      }
    }
  ],
  "refresh": "30s",
  "schemaVersion": 38,
  "style": "dark",
  "tags": ["data-prepper", "prometheus", "ameria"],
  "templating": {
    "list": [
      {
        "name": "DS_PROMETHEUS",
        "type": "datasource",
        "label": "Prometheus",
        "query": "prometheus",
        "current": null,
        "hide": 0
      },
      {
        "name": "job",
        "type": "query",
        "label": "job",
        "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
        "definition": "label_values(up, job)",
        "query": "label_values(up, job)",
        "refresh": 2,
        "includeAll": false,
        "multi": false,
        "current": { "text": "data-prepper", "value": "data-prepper", "selected": true }
      },
      {
        "name": "instance",
        "type": "query",
        "label": "instance",
        "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
        "definition": "label_values(up{job=\"$job\"}, instance)",
        "query": "label_values(up{job=\"$job\"}, instance)",
        "refresh": 2,
        "includeAll": true,
        "multi": true,
        "current": { "text": "All", "value": "$__all", "selected": true }
      },
      {
        "name": "prefix",
        "type": "custom",
        "label": "metric prefix",
        "query": "ameria_executor_,ameria_server_,core_peerForwarder_,entry_pipeline_BlockingBuffer_,entry_pipeline_otel_trace_source_,raw_pipeline_BlockingBuffer_,raw_pipeline_opensearch_,raw_pipeline_otel_trace_raw_,service_map_pipeline_BlockingBuffer_,service_map_pipeline_opensearch_,service_map_pipeline_service_map_stateful_",
        "includeAll": true,
        "multi": true,
        "allValue": "ameria_executor_|ameria_server_|core_peerForwarder_|entry_pipeline_BlockingBuffer_|entry_pipeline_otel_trace_source_|raw_pipeline_BlockingBuffer_|raw_pipeline_opensearch_|raw_pipeline_otel_trace_raw_|service_map_pipeline_BlockingBuffer_|service_map_pipeline_opensearch_|service_map_pipeline_service_map_stateful_",
        "current": { "text": "All", "value": "$__all", "selected": true }
      },
      {
        "name": "group_by",
        "type": "custom",
        "label": "Group by label",
        "query": "instance,pipeline,plugin_id,plugin_name,plugin_type",
        "current": { "text": "instance", "value": "instance", "selected": true }
      },
      {
        "name": "topn",
        "type": "custom",
        "label": "Top K",
        "query": "5,10,20,30",
        "current": { "text": "10", "value": "10", "selected": true }
      }
    ]
  },
  "time": { "from": "now-6h", "to": "now" },
  "timepicker": {},
  "timezone": "",
  "title": "Data Prepper Metrics (Ameria prefixes)",
  "uid": "data-prepper-ameria-prefixes",
  "version": 1,
  "weekStart": ""
}
```

Примечания
- Переменная prefix выбирает один/несколько префиксов; “All” уже разворачивается в корректный regex-юнион, чтобы корректно извлекать префикс и «хвост» метрики.
- Панели для histograms появятся только если под выбранными префиксами есть *_bucket-метрики (например, *_duration_seconds_bucket).
- Если у вас нестандартные лейблы (pipeline, plugin_name и т.п.), выберите их в group_by. Если лейбла нет — панель всё равно работает, просто сгруппирует без него.
- Нагрузка: панели counters использует rate() по $__rate_interval. При очень большом числе серий можно сузить по prefix/instance или уменьшить TopK.

Хотите, я добавлю отдельные панели под конкретные метрики (например, успех/ошибка opensearch sink, размер буферов, ретраи и т.д.)? Скиньте небольшой фрагмент /metrics — подстрою легенды, юниты и алерты.
