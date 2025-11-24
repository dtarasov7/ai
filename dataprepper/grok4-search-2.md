### Grafana Dashboard для визуализации метрик Data Prepper

На основе предоставленных префиксов метрик (ameria_executor_, ameria_server_, core_peerForwarder_, entry_pipeline_BlockingBuffer_, entry_pipeline_otel_trace_source_, raw_pipeline_BlockingBuffer_, raw_pipeline_opensearch_, raw_pipeline_otel_trace_raw_, service_map_pipeline_BlockingBuffer_, service_map_pipeline_opensearch_, service_map_pipeline_service_map_stateful_) я создал описание и JSON-конфигурацию для Grafana дашборда. Это основано на документации OpenSearch Data Prepper, где метрики экспортируются в формате Prometheus с конвенцией именования `PIPELINE_NAME_PLUGIN_NAME_METRIC_NAME` (например, `entry_pipeline_BlockingBuffer_recordsIn`). Метрики включают счётчики (counters) для записей (recordsIn/Out/Written/Read), таймеры (timeElapsed) для задержек и гейджи (gauges) для размера буфера (recordsInBuffer).

#### Общие предположения и инструкции по настройке
- **Datasource**: Prometheus (Data Prepper экспортирует метрики по умолчанию на `/metrics/sys` порт 4900). Убедитесь, что Prometheus скрейпит эти метрики.
- **Структура дашборда**: 
  - Разделы (rows) по префиксам для группировки.
  - Панели: Time series графики для ключевых метрик (throughput, latency, buffer size). Используйте запросы Prometheus вроде `rate(entry_pipeline_BlockingBuffer_recordsIn[5m])` для расчёта скоростей.
  - Временной диапазон: Автоматический, с переменными для pipeline (например, $pipeline).
  - Переменные: Добавьте dashboard variable `instance` (query: `label_values(up, instance)`) и `pipeline` (query: `label_values({__name__=~"entry_pipeline_*|raw_pipeline_*"}, pipeline)` – адаптируйте под ваши метрики).
- **Импорт**: Скопируйте JSON ниже в Grafana (Dashboard > Import > Paste JSON).
- **Кастомные префиксы**: `ameria_executor_` и `ameria_server_` кажутся кастомными (возможно, для executor пула или сервера); `core_peerForwarder_` – для peer-forwarder плагина. Я добавил панели на основе стандартных метрик (recordsIn/Out, timeElapsed и т.д.), предполагая аналогичную структуру.
- **Рекомендации**: 
  - Для буферов (BlockingBuffer_): Мониторьте `recordsInBuffer` (gauge) на предмет переполнения.
  - Для источников/синков (otel_trace_source_, opensearch_): Throughput (rate(recordsIn[5m])) и ошибки (если есть counters для ошибок).
  - Добавьте алерты в Grafana для высоких задержек или низкого throughput.
  - Если метрики не стандартные, скорректируйте запросы Prometheus на основе реальных имён (проверьте в Prometheus UI).

#### JSON для импорта в Grafana
Вот полный JSON для дашборда. Он включает 5 рядов панелей (по группам префиксов), с 3–4 панелями на ряд (графики для ключевых метрик). Общее время обновления: 30s.

```json
{
  "__inputs": [],
  "dashboard": {
    "id": null,
    "title": "Data Prepper Metrics Dashboard",
    "tags": ["data-prepper", "opentelemetry"],
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
        "title": "Ameria Executor & Server Metrics",
        "type": "row"
      },
      {
        "datasource": {
          "type": "prometheus",
          "uid": "Prometheus"
        },
        "fieldConfig": {
          "defaults": {
            "color": { "mode": "palette-classic" },
            "custom": { "axisCenteredZero": false, "hideFrom": { "legend": false, "tooltip": false, "vis": false } },
            "unit": "reqps",
            "thresholds": { "steps": [{ "color": "green", "value": null }, { "color": "red", "value": 80 }] }
          },
          "overrides": []
        },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 1 },
        "id": 2,
        "options": { "legend": { "calcs": ["lastNotNull"], "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "rate(ameria_executor_recordsIn[5m])", "legendFormat": "{{instance}} - Records In" }],
        "title": "Executor Throughput (Records In)",
        "type": "timeseries"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "custom": { "axisCenteredZero": false }, "unit": "ms", "thresholds": { "steps": [{ "color": "green", "value": null }, { "color": "yellow", "value": 100 }, { "color": "red", "value": 500 }] } }, "overrides": [] },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 1 },
        "id": 3,
        "options": { "legend": { "calcs": ["lastNotNull"], "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "ameria_executor_timeElapsed", "legendFormat": "{{instance}} - Time Elapsed" }],
        "title": "Executor Latency",
        "type": "timeseries"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "short" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 9 },
        "id": 4,
        "options": { "legend": { "calcs": ["lastNotNull"], "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "ameria_server_recordsOut", "legendFormat": "{{instance}} - Records Out" }],
        "title": "Server Records Out",
        "type": "timeseries"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "short" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 9 },
        "id": 5,
        "options": { "legend": { "calcs": ["lastNotNull"], "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "ameria_server_recordsIn", "legendFormat": "{{instance}} - Records In" }],
        "title": "Server Records In",
        "type": "timeseries"
      },
      {
        "collapsed": false,
        "gridPos": { "h": 1, "w": 24, "x": 0, "y": 17 },
        "id": 6,
        "panels": [],
        "title": "Core Peer Forwarder Metrics",
        "type": "row"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "reqps" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 18 },
        "id": 7,
        "options": { "legend": { "calcs": ["lastNotNull"], "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "rate(core_peerForwarder_recordsIn[5m])", "legendFormat": "{{instance}} - Forwarder Throughput" }],
        "title": "Peer Forwarder Throughput",
        "type": "timeseries"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "short" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 18 },
        "id": 8,
        "options": { "legend": { "calcs": ["lastNotNull"], "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "core_peerForwarder_recordsInBuffer", "legendFormat": "{{instance}} - Buffer Size" }],
        "title": "Peer Forwarder Buffer Size",
        "type": "timeseries"
      },
      {
        "collapsed": true,
        "gridPos": { "h": 1, "w": 24, "x": 0, "y": 26 },
        "id": 9,
        "panels": [],
        "title": "Entry Pipeline Metrics",
        "type": "row"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "reqps" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 8, "x": 0, "y": 27 },
        "id": 10,
        "options": { "legend": { "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "rate(entry_pipeline_BlockingBuffer_recordsWritten[5m])", "legendFormat": "Written" }, { "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "rate(entry_pipeline_BlockingBuffer_recordsRead[5m])", "legendFormat": "Read" }],
        "title": "Entry Pipeline Buffer Throughput",
        "type": "timeseries"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "short" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 8, "x": 8, "y": 27 },
        "id": 11,
        "options": { "legend": { "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "entry_pipeline_BlockingBuffer_recordsInBuffer", "legendFormat": "{{instance}}" }],
        "title": "Entry Pipeline Buffer Size",
        "type": "timeseries"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "ms" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 8, "x": 16, "y": 27 },
        "id": 12,
        "options": { "legend": { "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "entry_pipeline_otel_trace_source_timeElapsed", "legendFormat": "{{instance}}" }],
        "title": "OTEL Trace Source Latency",
        "type": "timeseries"
      },
      {
        "collapsed": true,
        "gridPos": { "h": 1, "w": 24, "x": 0, "y": 35 },
        "id": 13,
        "panels": [],
        "title": "Raw Pipeline Metrics",
        "type": "row"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "reqps" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 8, "x": 0, "y": 36 },
        "id": 14,
        "options": { "legend": { "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "rate(raw_pipeline_BlockingBuffer_recordsIn[5m])", "legendFormat": "In" }, { "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "rate(raw_pipeline_BlockingBuffer_recordsOut[5m])", "legendFormat": "Out" }],
        "title": "Raw Pipeline Buffer Throughput",
        "type": "timeseries"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "short" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 8, "x": 8, "y": 36 },
        "id": 15,
        "options": { "legend": { "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "raw_pipeline_opensearch_recordsIn", "legendFormat": "{{instance}}" }],
        "title": "OpenSearch Sink Records In",
        "type": "timeseries"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "ms" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 8, "x": 16, "y": 36 },
        "id": 16,
        "options": { "legend": { "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "raw_pipeline_otel_trace_raw_timeElapsed", "legendFormat": "{{instance}}" }],
        "title": "OTEL Trace Raw Latency",
        "type": "timeseries"
      },
      {
        "collapsed": true,
        "gridPos": { "h": 1, "w": 24, "x": 0, "y": 44 },
        "id": 17,
        "panels": [],
        "title": "Service Map Pipeline Metrics",
        "type": "row"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "reqps" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 8, "x": 0, "y": 45 },
        "id": 18,
        "options": { "legend": { "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "rate(service_map_pipeline_BlockingBuffer_recordsProcessed[5m])", "legendFormat": "Processed" }],
        "title": "Service Map Buffer Throughput",
        "type": "timeseries"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "short" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 8, "x": 8, "y": 45 },
        "id": 19,
        "options": { "legend": { "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "service_map_pipeline_opensearch_recordsIn", "legendFormat": "{{instance}}" }],
        "title": "Service Map OpenSearch Records In",
        "type": "timeseries"
      },
      {
        "datasource": { "type": "prometheus", "uid": "Prometheus" },
        "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "short" }, "overrides": [] },
        "gridPos": { "h": 8, "w": 8, "x": 16, "y": 45 },
        "id": 20,
        "options": { "legend": { "displayMode": "list", "placement": "bottom" }, "tooltip": { "mode": "multi" } },
        "targets": [{ "datasource": { "type": "prometheus", "uid": "Prometheus" }, "editorMode": "code", "expr": "service_map_pipeline_service_map_stateful_recordsInFlight", "legendFormat": "{{instance}}" }],
        "title": "Service Map Stateful Records In Flight",
        "type": "timeseries"
      }
    ],
    "refresh": "30s",
    "schemaVersion": 39,
    "tags": ["data-prepper"],
    "templating": {
      "list": [
        {
          "allValue": null,
          "current": {},
          "datasource": { "type": "prometheus", "uid": "Prometheus" },
          "definition": "label_values(up, instance)",
          "hide": 0,
          "includeAll": true,
          "label": "Instance",
          "multi": false,
          "name": "instance",
          "options": [],
          "query": { "query": "label_values(up, instance)", "refId": "StandardVariableQuery" },
          "refresh": 1,
          "regex": "",
          "skipUrlSync": false,
          "sort": 0,
          "type": "query"
        }
      ]
    },
    "time": { "from": "now-6h", "to": "now" },
    "timepicker": {},
    "timezone": "",
    "title": "Data Prepper Metrics",
    "uid": "data-prepper-dashboard",
    "version": 1,
    "weekStart": ""
  },
  "overwrite": false
}
```

#### Как доработать
1. **Импорт**: В Grafana перейдите в Dashboards > New > Import, вставьте JSON и выберите datasource Prometheus.
2. **Проверка запросов**: В Prometheus UI протестируйте expr (например, `entry_pipeline_BlockingBuffer_recordsIn`), чтобы убедиться в наличии метрик. Если имена отличаются, отредактируйте в Grafana.
3. **Добавление панелей**: Для ошибок добавьте панели с `writeTimeouts` или `recordsProcessed` (если доступны).
4. **Визуализация**: Используйте Stat панели для текущих значений gauge (например, buffer size) или Heatmap для latency распределений.
5. **Источники**: Эта конфигурация вдохновлена стандартными метриками Data Prepper из документации и общими практиками мониторинга OTel (например, дашборды для Collector.

Если нужны дополнения (например, для конкретных метрик или алертов), предоставьте больше деталей!
