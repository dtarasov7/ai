Отличный список метрик! На его основе можно построить очень информативный и полезный дашборд в Grafana для мониторинга Data Prepper.

Дашборд будет разбит на логические секции (rows), чтобы было удобно анализировать состояние различных компонентов сервиса:

1.  **Обзор (Overview)**: Ключевые показатели здоровья всего сервиса.
2.  **Входной конвейер (Entry Pipeline)**: Метрики, связанные с приемом данных (вероятно, от OTel-коллекторов).
3.  **Конвейеры и Буферы (Pipelines & Buffers)**: Состояние внутренних буферов, главный индикатор backpressure.
4.  **Конвейер обработки Raw данных (Raw Pipeline -> OpenSearch)**: Как "сырые" данные обрабатываются и отправляются в OpenSearch.
5.  **Конвейер Service Map (Service Map Pipeline -> OpenSearch)**: Как данные для карты сервисов обрабатываются и отправляются в OpenSearch.
6.  **Core & Web Server (Ядро и Веб-сервер)**: Низкоуровневые метрики веб-сервера Armeria и компонента PeerForwarder.

---

### Как использовать этот дашборд:

1.  В Grafana нажмите на `+` -> `Import`.
2.  Скопируйте и вставьте приведенный ниже JSON-код в текстовое поле.
3.  Нажмите `Load`.
4.  Выберите ваш источник данных Prometheus и нажмите `Import`.

Дашборд использует переменные `job` и `instance`, чтобы вы могли фильтровать данные по конкретным инстансам вашего Data Prepper.

---

### JSON для импорта в Grafana

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
      "title": "Обзор (Overview)",
      "type": "row"
    },
    {
      "description": "Общая частота входящих запросов на Data Prepper.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 0,
        "y": 1
      },
      "id": 2,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(entry_pipeline_otel_trace_source_requestsReceived_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Всего получено",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(entry_pipeline_otel_trace_source_successRequests_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Успешные",
          "refId": "B"
        }
      ],
      "title": "Входящие запросы (RPS)",
      "type": "timeseries"
    },
    {
      "description": "Процент ошибок при приеме данных. Должен быть близок к нулю.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 8,
        "y": 1
      },
      "id": 4,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "(sum(rate(entry_pipeline_otel_trace_source_badRequests_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval])) + sum(rate(entry_pipeline_otel_trace_source_requestsTooLarge_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval])) + sum(rate(entry_pipeline_otel_trace_source_internalServerError_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))) / sum(rate(entry_pipeline_otel_trace_source_requestsReceived_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval])) * 100",
          "legendFormat": "Входящие ошибки (%)",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(raw_pipeline_opensearch_documentErrors_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval])) + sum(rate(service_map_pipeline_opensearch_documentErrors_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Ошибки записи документов (RPS)",
          "refId": "B"
        }
      ],
      "title": "Уровень ошибок",
      "type": "timeseries"
    },
    {
      "description": "Среднее время обработки запроса на разных стадиях.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 16,
        "y": 1
      },
      "id": 6,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(entry_pipeline_otel_trace_source_requestProcessDuration_seconds_sum{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval])) / sum(rate(entry_pipeline_otel_trace_source_requestProcessDuration_seconds_count{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Entry Pipeline (Source)",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(raw_pipeline_opensearch_bulkRequestLatency_seconds_sum{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval])) / sum(rate(raw_pipeline_opensearch_bulkRequestLatency_seconds_count{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Raw Pipeline (OpenSearch Bulk)",
          "refId": "B"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(service_map_pipeline_opensearch_bulkRequestLatency_seconds_sum{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval])) / sum(rate(service_map_pipeline_opensearch_bulkRequestLatency_seconds_count{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "ServiceMap Pipeline (OpenSearch Bulk)",
          "refId": "C"
        }
      ],
      "title": "Среднее время обработки (Latency)",
      "type": "timeseries",
      "unit": "s"
    },
    {
      "collapsed": false,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 9
      },
      "id": 101,
      "panels": [],
      "title": "Входной конвейер (Entry Pipeline)",
      "type": "row"
    },
    {
      "description": "Детализация по типам ошибок на входе.",
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 10
      },
      "id": 8,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(entry_pipeline_otel_trace_source_badRequests_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Bad Requests - {{instance}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(entry_pipeline_otel_trace_source_requestsTooLarge_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Too Large - {{instance}}",
          "refId": "B"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(entry_pipeline_otel_trace_source_requestTimeouts_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Timeouts - {{instance}}",
          "refId": "C"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(entry_pipeline_otel_trace_source_internalServerError_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Internal Server Error - {{instance}}",
          "refId": "D"
        }
      ],
      "title": "Ошибки на входе (RPS)",
      "type": "timeseries"
    },
    {
      "description": "Средний размер входящего запроса (payload).",
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 10
      },
      "id": 10,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(entry_pipeline_otel_trace_source_payloadSize_sum{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval])) / sum(rate(entry_pipeline_otel_trace_source_payloadSize_count{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Средний размер",
          "refId": "A"
        }
      ],
      "title": "Размер входящих данных",
      "type": "timeseries",
      "unit": "bytes"
    },
    {
      "collapsed": false,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 18
      },
      "id": 102,
      "panels": [],
      "title": "Конвейеры и Буферы (Pipelines & Buffers)",
      "type": "row"
    },
    {
      "description": "Заполненность внутреннего буфера для каждого конвейера. Рост до 100% указывает на backpressure (не успеваем обрабатывать/отправлять данные).",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 0,
        "y": 19
      },
      "id": 12,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "entry_pipeline_BlockingBuffer_bufferUsage{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Entry - {{instance}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "raw_pipeline_BlockingBuffer_bufferUsage{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Raw - {{instance}}",
          "refId": "B"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "service_map_pipeline_BlockingBuffer_bufferUsage{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Service Map - {{instance}}",
          "refId": "C"
        }
      ],
      "title": "Заполненность буферов",
      "type": "timeseries",
      "unit": "percentunit"
    },
    {
      "description": "Количество записей, ожидающих обработки в буфере. Постоянный рост - плохой знак.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 8,
        "y": 19
      },
      "id": 14,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "entry_pipeline_BlockingBuffer_recordsInBuffer{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Entry - {{instance}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "raw_pipeline_BlockingBuffer_recordsInBuffer{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Raw - {{instance}}",
          "refId": "B"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "service_map_pipeline_BlockingBuffer_recordsInBuffer{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Service Map - {{instance}}",
          "refId": "C"
        }
      ],
      "title": "Записей в буфере",
      "type": "timeseries"
    },
    {
      "description": "Скорость записи и чтения из буферов. Графики должны идти близко друг к другу.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 16,
        "y": 19
      },
      "id": 16,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(entry_pipeline_BlockingBuffer_recordsWritten_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Entry Written",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(entry_pipeline_BlockingBuffer_recordsRead_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Entry Read",
          "refId": "B"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(raw_pipeline_BlockingBuffer_recordsWritten_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Raw Written",
          "refId": "C"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(raw_pipeline_BlockingBuffer_recordsRead_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Raw Read",
          "refId": "D"
        }
      ],
      "title": "Пропускная способность буферов",
      "type": "timeseries",
      "unit": "reps"
    },
    {
      "collapsed": false,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 27
      },
      "id": 103,
      "panels": [],
      "title": "Конвейер обработки Raw данных (Raw Pipeline -> OpenSearch)",
      "type": "row"
    },
    {
      "description": "Количество успешно отправленных документов в OpenSearch.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 0,
        "y": 28
      },
      "id": 18,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(raw_pipeline_opensearch_documentsSuccess_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Всего успешно - {{instance}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(raw_pipeline_opensearch_documentsSuccessFirstAttempt_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Успешно с 1-й попытки - {{instance}}",
          "refId": "B"
        }
      ],
      "title": "Raw Pipeline: Успешные документы (DPS)",
      "type": "timeseries"
    },
    {
      "description": "Количество ошибок при записи в OpenSearch.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 8,
        "y": 28
      },
      "id": 20,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(raw_pipeline_opensearch_bulkRequestErrors_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Ошибки Bulk-запросов - {{instance}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(raw_pipeline_opensearch_documentErrors_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Ошибки документов - {{instance}}",
          "refId": "B"
        }
      ],
      "title": "Raw Pipeline: Ошибки OpenSearch (RPS)",
      "type": "timeseries"
    },
    {
      "description": "Среднее время выполнения bulk-запроса в OpenSearch.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 16,
        "y": 28
      },
      "id": 22,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(raw_pipeline_opensearch_bulkRequestLatency_seconds_sum{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval])) / sum(rate(raw_pipeline_opensearch_bulkRequestLatency_seconds_count{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Avg Latency",
          "refId": "A"
        }
      ],
      "title": "Raw Pipeline: Latency Bulk-запросов",
      "type": "timeseries",
      "unit": "s"
    },
    {
      "collapsed": false,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 36
      },
      "id": 104,
      "panels": [],
      "title": "Конвейер Service Map (Service Map Pipeline -> OpenSearch)",
      "type": "row"
    },
    {
      "description": "Количество успешно отправленных документов в OpenSearch.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 0,
        "y": 37
      },
      "id": 24,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(service_map_pipeline_opensearch_documentsSuccess_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Всего успешно - {{instance}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(service_map_pipeline_opensearch_documentsSuccessFirstAttempt_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Успешно с 1-й попытки - {{instance}}",
          "refId": "B"
        }
      ],
      "title": "Service Map: Успешные документы (DPS)",
      "type": "timeseries"
    },
    {
      "description": "Количество ошибок при записи в OpenSearch.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 8,
        "y": 37
      },
      "id": 26,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(service_map_pipeline_opensearch_bulkRequestErrors_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Ошибки Bulk-запросов - {{instance}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum by (instance) (rate(service_map_pipeline_opensearch_documentErrors_total{job=~\"$job\",instance=~\"$instance\"}[$__rate_interval]))",
          "legendFormat": "Ошибки документов - {{instance}}",
          "refId": "B"
        }
      ],
      "title": "Service Map: Ошибки OpenSearch (RPS)",
      "type": "timeseries"
    },
    {
      "description": "Размер stateful-баз данных для построения Service Map.",
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 16,
        "y": 37
      },
      "id": 28,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "service_map_pipeline_service_map_stateful_spansDbSize{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Spans DB - {{instance}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "service_map_pipeline_service_map_stateful_traceGroupDbSize{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Trace Group DB - {{instance}}",
          "refId": "B"
        }
      ],
      "title": "Service Map: Размер State DB",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 45
      },
      "id": 105,
      "panels": [],
      "title": "Core & Web Server",
      "type": "row"
    },
    {
      "description": "Состояние пула потоков веб-сервера Armeria. Рост числа задач в очереди (queued) может указывать на нехватку ресурсов.",
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 46
      },
      "id": 30,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "armeria_executor_active_threads{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Active Threads - {{name}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "armeria_executor_pool_size_threads{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Pool Size - {{name}}",
          "refId": "B"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "armeria_executor_queued_tasks{job=~\"$job\",instance=~\"$instance\"}",
          "legendFormat": "Queued Tasks - {{name}}",
          "refId": "C"
        }
      ],
      "title": "Armeria: Пул потоков",
      "type": "timeseries"
    },
    {
      "description": "Использование CPU процессом Data Prepper.",
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 46
      },
      "id": 32,
      "options": {
        "legend": {
          "displayMode": "list",
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
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "process_cpu_usage{job=~\"$job\",instance=~\"$instance\"} * 100",
          "legendFormat": "{{instance}}",
          "refId": "A"
        }
      ],
      "title": "CPU Usage",
      "type": "timeseries",
      "unit": "percent"
    }
  ],
  "refresh": "30s",
  "schemaVersion": 38,
  "style": "dark",
  "tags": [
    "data-prepper"
  ],
  "templating": {
    "list": [
      {
        "current": {},
        "datasource": {
          "type": "prometheus",
          "uid": "${DS_PROMETHEUS}"
        },
        "definition": "label_values(up{job=~\"data-prepper.*\"}, job)",
        "hide": 0,
        "includeAll": true,
        "label": "Job",
        "multi": true,
        "name": "job",
        "options": [],
        "query": {
          "query": "label_values(up{job=~\"data-prepper.*\"}, job)",
          "refId": "StandardVariableQuery"
        },
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
        "sort": 0,
        "type": "query"
      },
      {
        "current": {},
        "datasource": {
          "type": "prometheus",
          "uid": "${DS_PROMETHEUS}"
        },
        "definition": "label_values(up{job=~\"$job\"}, instance)",
        "hide": 0,
        "includeAll": true,
        "label": "Instance",
        "multi": true,
        "name": "instance",
        "options": [],
        "query": {
          "query": "label_values(up{job=~\"$job\"}, instance)",
          "refId": "StandardVariableQuery"
        },
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
        "sort": 0,
        "type": "query"
      }
    ]
  },
  "time": {
    "from": "now-1h",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "browser",
  "title": "Data Prepper Overview",
  "uid": null,
  "version": 1,
  "weekStart": ""
}
```