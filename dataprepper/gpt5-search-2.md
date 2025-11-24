Отлично! Ниже — готовый к импорту Grafana‑дашборд для наблюдения за Data Prepper по указанным префиксам метрик. Я исхожу из того, что метрики собирает Prometheus (scrape с /metrics), а в метках присутствуют job и instance. Если у вас другой источник/метки — напишите, адаптирую.

Что внутри
- Переменные: Prometheus datasource, job, instance.
- Ряды/группы панелей по префиксам:
  - ameria_executor_, ameria_server_, core_peerForwarder_
  - entry_pipeline_* (BlockingBuffer, otel_trace_source)
  - raw_pipeline_* (BlockingBuffer, opensearch, otel_trace_raw)
  - service_map_pipeline_* (BlockingBuffer, opensearch, service_map_stateful)
- Общий обзор: суммарная пропускная способность и ошибки по группам pipeline через label_replace по __name__.
- Во всех рядах есть:
  - rate-панель для счетчиков (_count|_total|...),
  - gauge-панель для «моментных» метрик,
  - попытка собрать перцентили из гистограмм (_bucket) — если их нет, панель будет пустой.

Импорт
- В Grafana: Dashboards → New → Import → вставьте JSON → выберите Prometheus datasource в переменной DS_PROMETHEUS → Import.

JSON дашборда
```json
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": { "type": "grafana", "uid": "-- Grafana --" },
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
  "refresh": "30s",
  "schemaVersion": 39,
  "style": "dark",
  "tags": ["data-prepper", "ameria"],
  "templating": {
    "list": [
      {
        "name": "DS_PROMETHEUS",
        "label": "Prometheus",
        "type": "datasource",
        "query": "prometheus",
        "current": {},
        "hide": 0
      },
      {
        "type": "query",
        "name": "job",
        "label": "job",
        "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
        "refresh": 2,
        "hide": 0,
        "multi": true,
        "includeAll": true,
        "allValue": ".*",
        "query": "label_values({__name__=~\"ameria_.*|core_peerForwarder_.*|entry_pipeline_.*|raw_pipeline_.*|service_map_pipeline_.*\"}, job)"
      },
      {
        "type": "query",
        "name": "instance",
        "label": "instance",
        "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
        "refresh": 2,
        "hide": 0,
        "multi": true,
        "includeAll": true,
        "allValue": ".*",
        "query": "label_values({job=~\"$job\", __name__=~\"ameria_.*|core_peerForwarder_.*|entry_pipeline_.*|raw_pipeline_.*|service_map_pipeline_.*\"}, instance)"
      }
    ]
  },
  "time": { "from": "now-6h", "to": "now" },
  "timezone": "",
  "title": "Data Prepper (ameria) — Overview",
  "uid": "data-prepper-ameria",
  "version": 1,
  "weekStart": "",
  "panels": [
    {
      "type": "row",
      "title": "Обзор",
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 0 },
      "id": 1,
      "panels": []
    },
    {
      "id": 2,
      "type": "timeseries",
      "title": "Pipeline throughput (entry/raw/service_map) — rate",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 0, "y": 1 },
      "targets": [
        {
          "refId": "A",
          "editorMode": "code",
          "range": true,
          "expr": "sum by (group) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"(entry_pipeline_|raw_pipeline_|service_map_pipeline_).*(records|events|spans|requests|emitted|processed|received)(_total|_count)?\"}[$__rate_interval]),\n    \"group\", \"$1\", \"__name__\", \"^(entry_pipeline_|raw_pipeline_|service_map_pipeline_).*\"\n  )\n)"
        }
      ],
      "options": { "legend": { "displayMode": "list", "placement": "bottom" } }
    },
    {
      "id": 3,
      "type": "timeseries",
      "title": "Pipeline errors — rate",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 8, "y": 1 },
      "targets": [
        {
          "refId": "A",
          "editorMode": "code",
          "range": true,
          "expr": "sum by (group) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"(entry_pipeline_|raw_pipeline_|service_map_pipeline_).*(error|failure|dropped|reject|timeout)([_]?(total|count))?\"}[$__rate_interval]),\n    \"group\", \"$1\", \"__name__\", \"^(entry_pipeline_|raw_pipeline_|service_map_pipeline_).*\"\n  )\n)"
        }
      ],
      "options": { "legend": { "displayMode": "list", "placement": "bottom" } }
    },
    {
      "id": 4,
      "type": "timeseries",
      "title": "PeerForwarder — traffic rate",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 16, "y": 1 },
      "targets": [
        {
          "refId": "A",
          "editorMode": "code",
          "range": true,
          "legendFormat": "{{metric}}",
          "expr": "sum by (metric) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"core_peerForwarder_.*(requests|records|events|bytes|processed|received|emitted)(_total|_count)?\"}[$__rate_interval]),\n    \"metric\", \"$1\", \"__name__\", \"^core_peerForwarder_(.*)\"\n  )\n)"
        }
      ],
      "options": { "legend": { "displayMode": "list", "placement": "bottom" } }
    },

    {
      "type": "row",
      "title": "ameria_executor_",
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 9 },
      "id": 10,
      "panels": []
    },
    {
      "id": 11,
      "type": "timeseries",
      "title": "ameria_executor_ — counters (rate)",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 10 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "editorMode": "code",
          "range": true,
          "expr": "sum by (metric) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"ameria_executor_.*(total|count|requests|records|events|bytes|errors|failures|processed|emitted|received)\"}[$__rate_interval]),\n    \"metric\", \"$1\", \"__name__\", \"^ameria_executor_(.*)\"\n  )\n)"
        }
      ]
    },
    {
      "id": 12,
      "type": "timeseries",
      "title": "ameria_executor_ — gauges",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 10 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "editorMode": "code",
          "range": true,
          "expr": "avg by (metric) (\n  label_replace(\n    {job=~\"$job\", instance=~\"$instance\", __name__=~\"ameria_executor_.*\", __name__!~\".*(_bucket|_sum|_count|_total)\"},\n    \"metric\", \"$1\", \"__name__\", \"^ameria_executor_(.*)\"\n  )\n)"
        }
      ]
    },
    {
      "id": 13,
      "type": "timeseries",
      "title": "ameria_executor_ — latency quantiles (если есть _bucket)",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 18 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "p50",
          "expr": "histogram_quantile(0.50, sum by (le) (rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"ameria_executor_.*_bucket\"}[$__rate_interval])))"
        },
        {
          "refId": "B",
          "legendFormat": "p95",
          "expr": "histogram_quantile(0.95, sum by (le) (rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"ameria_executor_.*_bucket\"}[$__rate_interval])))"
        },
        {
          "refId": "C",
          "legendFormat": "p99",
          "expr": "histogram_quantile(0.99, sum by (le) (rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"ameria_executor_.*_bucket\"}[$__rate_interval])))"
        }
      ]
    },

    {
      "type": "row",
      "title": "ameria_server_",
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 26 },
      "id": 20,
      "panels": []
    },
    {
      "id": 21,
      "type": "timeseries",
      "title": "ameria_server_ — counters (rate)",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 27 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "sum by (metric) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"ameria_server_.*(total|count|requests|records|events|bytes|errors|failures|processed|emitted|received)\"}[$__rate_interval]),\n    \"metric\", \"$1\", \"__name__\", \"^ameria_server_(.*)\"\n  )\n)"
        }
      ]
    },
    {
      "id": 22,
      "type": "timeseries",
      "title": "ameria_server_ — gauges",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 27 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "avg by (metric) (\n  label_replace(\n    {job=~\"$job\", instance=~\"$instance\", __name__=~\"ameria_server_.*\", __name__!~\".*(_bucket|_sum|_count|_total)\"},\n    \"metric\", \"$1\", \"__name__\", \"^ameria_server_(.*)\"\n  )\n)"
        }
      ]
    },

    {
      "type": "row",
      "title": "core_peerForwarder_",
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 35 },
      "id": 30,
      "panels": []
    },
    {
      "id": 31,
      "type": "timeseries",
      "title": "core_peerForwarder_ — counters (rate)",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 36 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "sum by (metric) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"core_peerForwarder_.*(total|count|requests|records|events|bytes|errors|failures|processed|emitted|received)\"}[$__rate_interval]),\n    \"metric\", \"$1\", \"__name__\", \"^core_peerForwarder_(.*)\"\n  )\n)"
        }
      ]
    },
    {
      "id": 32,
      "type": "timeseries",
      "title": "core_peerForwarder_ — gauges",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 36 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "avg by (metric) (\n  label_replace(\n    {job=~\"$job\", instance=~\"$instance\", __name__=~\"core_peerForwarder_.*\", __name__!~\".*(_bucket|_sum|_count|_total)\"},\n    \"metric\", \"$1\", \"__name__\", \"^core_peerForwarder_(.*)\"\n  )\n)"
        }
      ]
    },

    {
      "type": "row",
      "title": "entry_pipeline_*",
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 44 },
      "id": 40,
      "panels": []
    },
    {
      "id": 41,
      "type": "timeseries",
      "title": "entry_pipeline_BlockingBuffer — gauges",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 0, "y": 45 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "avg by (metric) (\n  label_replace(\n    {job=~\"$job\", instance=~\"$instance\", __name__=~\"entry_pipeline_BlockingBuffer_.*\", __name__!~\".*(_bucket|_sum|_count|_total)\"},\n    \"metric\", \"$1\", \"__name__\", \"^entry_pipeline_BlockingBuffer_(.*)\"\n  )\n)"
        }
      ]
    },
    {
      "id": 42,
      "type": "timeseries",
      "title": "entry_pipeline_otel_trace_source — counters (rate)",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 8, "y": 45 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "sum by (metric) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"entry_pipeline_otel_trace_source_.*(total|count|requests|records|events|bytes|errors|failures|processed|emitted|received)\"}[$__rate_interval]),\n    \"metric\", \"$1\", \"__name__\", \"^entry_pipeline_otel_trace_source_(.*)\"\n  )\n)"
        }
      ]
    },
    {
      "id": 43,
      "type": "timeseries",
      "title": "entry_pipeline_* — latency quantiles",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 16, "y": 45 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "p95",
          "expr": "histogram_quantile(0.95, sum by (le) (rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"entry_pipeline_.*_bucket\"}[$__rate_interval])))"
        },
        {
          "refId": "B",
          "legendFormat": "p99",
          "expr": "histogram_quantile(0.99, sum by (le) (rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"entry_pipeline_.*_bucket\"}[$__rate_interval])))"
        }
      ]
    },

    {
      "type": "row",
      "title": "raw_pipeline_*",
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 53 },
      "id": 50,
      "panels": []
    },
    {
      "id": 51,
      "type": "timeseries",
      "title": "raw_pipeline_BlockingBuffer — gauges",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 0, "y": 54 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "avg by (metric) (\n  label_replace(\n    {job=~\"$job\", instance=~\"$instance\", __name__=~\"raw_pipeline_BlockingBuffer_.*\", __name__!~\".*(_bucket|_sum|_count|_total)\"},\n    \"metric\", \"$1\", \"__name__\", \"^raw_pipeline_BlockingBuffer_(.*)\"\n  )\n)"
        }
      ]
    },
    {
      "id": 52,
      "type": "timeseries",
      "title": "raw_pipeline_otel_trace_raw — counters (rate)",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 8, "y": 54 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "sum by (metric) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"raw_pipeline_otel_trace_raw_.*(total|count|requests|records|events|bytes|errors|failures|processed|emitted|received)\"}[$__rate_interval]),\n    \"metric\", \"$1\", \"__name__\", \"^raw_pipeline_otel_trace_raw_(.*)\"\n  )\n)"
        }
      ]
    },
    {
      "id": 53,
      "type": "timeseries",
      "title": "raw_pipeline_opensearch — write/IO rate (success/failure/…)",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 16, "y": 54 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "sum by (metric) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"raw_pipeline_opensearch_.*(success|failure|error|request|bulk|retry|records|events|bytes|processed|emitted|received)([_]?(total|count))?\"}[$__rate_interval]),\n    \"metric\", \"$1\", \"__name__\", \"^raw_pipeline_opensearch_(.*)\"\n  )\n)"
        }
      ]
    },

    {
      "type": "row",
      "title": "service_map_pipeline_*",
      "collapsed": false,
      "gridPos": { "h": 1, "w": 24, "x": 0, "y": 62 },
      "id": 60,
      "panels": []
    },
    {
      "id": 61,
      "type": "timeseries",
      "title": "service_map_pipeline_BlockingBuffer — gauges",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 0, "y": 63 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "avg by (metric) (\n  label_replace(\n    {job=~\"$job\", instance=~\"$instance\", __name__=~\"service_map_pipeline_BlockingBuffer_.*\", __name__!~\".*(_bucket|_sum|_count|_total)\"},\n    \"metric\", \"$1\", \"__name__\", \"^service_map_pipeline_BlockingBuffer_(.*)\"\n  )\n)"
        }
      ]
    },
    {
      "id": 62,
      "type": "timeseries",
      "title": "service_map_pipeline_opensearch — write/IO rate",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 8, "y": 63 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "sum by (metric) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"service_map_pipeline_opensearch_.*(success|failure|error|request|bulk|retry|records|events|bytes|processed|emitted|received)([_]?(total|count))?\"}[$__rate_interval]),\n    \"metric\", \"$1\", \"__name__\", \"^service_map_pipeline_opensearch_(.*)\"\n  )\n)"
        }
      ]
    },
    {
      "id": 63,
      "type": "timeseries",
      "title": "service_map_pipeline_service_map_stateful — counters (rate)",
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "gridPos": { "h": 8, "w": 8, "x": 16, "y": 63 },
      "targets": [
        {
          "refId": "A",
          "legendFormat": "{{metric}}",
          "expr": "sum by (metric) (\n  label_replace(\n    rate({job=~\"$job\", instance=~\"$instance\", __name__=~\"service_map_pipeline_service_map_stateful_.*(total|count|requests|records|events|bytes|errors|failures|processed|emitted|received)\"}[$__rate_interval]),\n    \"metric\", \"$1\", \"__name__\", \"^service_map_pipeline_service_map_stateful_(.*)\"\n  )\n)"
        }
      ]
    }
  ]
}
```

Примечания и тонкая настройка
- Если ваши метрики используют иные суффиксы для счетчиков/гистограмм, скорректируйте соответствующие regex в __name__=~"...".
- В некоторых местах я использую $__rate_interval — Grafana автоматически подбирает окно для rate. Можно зафиксировать, например [5m].
- Если нужны алерты (например, рост дропов/ошибок в opensearch), скажите — добавлю правила Alerting и отдельные Stat‑панели.
- Если вместо Prometheus у вас Tempo/OTel Collector/Influx/Локальные метки без job/instance — пришлите пример 3–5 строк метрик, быстро адаптирую дашборд.
