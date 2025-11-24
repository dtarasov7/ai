Конечно! Я подготовил для вас дашборд Grafana в формате JSON, который визуализирует предоставленные метрики.

Дашборд сгруппирован по логическим блокам для удобства анализа:

1.  **Обзор (Overview)**: Ключевые показатели работы сервиса, такие как версия сборки и количество активных инстансов.
2.  **Исполнитель (Executor / Thread Pool)**: Детальная информация о пуле потоков, который выполняет основную работу. Это самая важная секция для анализа производительности и узких мест.
3.  **HTTP Сервер (Armeria Server)**: Метрики, связанные с веб-сервером, активными соединениями и кешем.
4.  **Ресурсы (System Resources)**: Потребление CPU процессом.

### Как использовать этот дашборд?

1.  Скопируйте весь JSON-код ниже.
2.  В Grafana перейдите в раздел `Dashboards`.
3.  Нажмите кнопку `New` и выберите `Import`.
4.  Вставьте скопированный JSON в поле `Import via panel json`.
5.  Выберите ваш источник данных Prometheus.
6.  Нажмите `Import`, и дашборд будет создан.

---

### Описание панелей дашборда

#### Переменные (Variables)
*   `$job`: Позволяет выбрать job из Prometheus, соответствующий вашему data-prepper (например, `data-prepper`).
*   `$instance`: Позволяет фильтровать метрики по конкретному инстансу (поду, серверу).

#### Секция: Обзор (Overview)
*   **Информация о сборке**: Таблица с версией, коммитом и временем сборки сервиса. Полезно для понимания, какая версия сейчас работает.
*   **Активные инстансы**: Количество работающих инстансов сервиса.
*   **Общая скорость выполнения задач**: Сколько задач в секунду завершается всеми инстансами. Ключевой показатель пропускной способности.

#### Секция: Исполнитель (Executor / Thread Pool)
*   **Загрузка пула потоков**: Показывает, сколько потоков активно (`active_threads`) по сравнению с общим количеством потоков в пуле (`pool_size_threads`). Помогает понять, достаточно ли потоков для обработки нагрузки.
*   **Размер очереди задач**: Количество задач, ожидающих выполнения в очереди. Если это значение постоянно растет, это явный признак того, что сервис не справляется с нагрузкой (back-pressure).
*   **Среднее время выполнения задачи**: Рассчитывается как `rate(sum) / rate(count)`. Показывает среднюю задержку обработки одной задачи. Важный показатель производительности.
*   **Максимальное время выполнения задачи**: Пиковое значение времени выполнения задачи. Помогает отслеживать аномальные задержки.

#### Секция: HTTP Сервер (Armeria Server)
*   **Активные соединения**: Текущее количество открытых клиентских соединений с сервером.
*   **Производительность кеша роутера**: Показывает скорость запросов к внутреннему кешу роутера и скорость вытеснения записей из него. Рост вытеснений может указывать на неэффективный размер кеша.

#### Секция: Ресурсы (System Resources)
*   **Использование CPU**: Утилизация CPU процессом `data-prepper` в процентах.

---

### JSON код дашборда

```json
{
  "__inputs": [
    {
      "name": "DS_PROMETHEUS",
      "label": "Prometheus",
      "description": "",
      "type": "datasource",
      "pluginId": "prometheus",
      "pluginName": "Prometheus"
    }
  ],
  "__requires": [
    {
      "type": "grafana",
      "id": "grafana",
      "name": "Grafana",
      "version": "8.0.0"
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
        "type": "dashboard"
      }
    ]
  },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "liveNow": false,
  "panels": [
    {
      "collapsed": false,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 0
      },
      "id": 20,
      "panels": [],
      "title": "Обзор (Overview)",
      "type": "row"
    },
    {
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 0,
        "y": 1
      },
      "id": 14,
      "options": {
        "showHeader": true
      },
      "pluginVersion": "9.2.5",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "format": "table",
          "instant": true,
          "legendFormat": "",
          "query": "armeria_build_info{job=\"$job\", instance=~\"$instance\"}",
          "refId": "A"
        }
      ],
      "title": "Информация о сборке",
      "transformations": [
        {
          "id": "labelsToFields",
          "options": {}
        }
      ],
      "type": "table"
    },
    {
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 8,
        "y": 1
      },
      "id": 16,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": [
            "lastNotNull"
          ],
          "fields": "",
          "values": false
        },
        "textMode": "auto"
      },
      "pluginVersion": "9.2.5",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "count(up{job=\"$job\"})",
          "legendFormat": "",
          "refId": "A"
        }
      ],
      "title": "Активные инстансы",
      "type": "stat"
    },
    {
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 16,
        "y": 1
      },
      "id": 18,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": [
            "lastNotNull"
          ],
          "fields": "",
          "values": false
        },
        "textMode": "auto"
      },
      "pluginVersion": "9.2.5",
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(armeria_executor_completed_tasks_total{job=\"$job\"}[$__rate_interval]))",
          "legendFormat": "Всего",
          "refId": "A"
        }
      ],
      "title": "Общая скорость выполнения задач (задач/сек)",
      "type": "stat"
    },
    {
      "collapsed": false,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 9
      },
      "id": 21,
      "panels": [],
      "title": "Исполнитель (Executor / Thread Pool)",
      "type": "row"
    },
    {
      "description": "Показывает, сколько потоков активно по сравнению с общим количеством в пуле. Помогает понять, достаточно ли потоков для обработки нагрузки.",
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
                "value": 80
              }
            ]
          },
          "unit": "short"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 9,
        "w": 12,
        "x": 0,
        "y": 10
      },
      "id": 2,
      "options": {
        "legend": {
          "calcs": [],
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
          "expr": "armeria_executor_active_threads{job=\"$job\", instance=~\"$instance\"}",
          "legendFormat": "active - {{instance}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "armeria_executor_pool_size_threads{job=\"$job\", instance=~\"$instance\"}",
          "legendFormat": "pool size - {{instance}}",
          "refId": "B"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "armeria_executor_pool_max_threads{job=\"$job\", instance=~\"$instance\"}",
          "legendFormat": "max size - {{instance}}",
          "refId": "C"
        }
      ],
      "title": "Загрузка пула потоков",
      "type": "timeseries"
    },
    {
      "description": "Количество задач, ожидающих выполнения в очереди. Если это значение постоянно растет, сервис не справляется с нагрузкой.",
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
                "value": 80
              }
            ]
          },
          "unit": "short"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 9,
        "w": 12,
        "x": 12,
        "y": 10
      },
      "id": 4,
      "options": {
        "legend": {
          "calcs": [],
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
          "expr": "armeria_executor_queued_tasks{job=\"$job\", instance=~\"$instance\"}",
          "legendFormat": "{{instance}}",
          "refId": "A"
        }
      ],
      "title": "Размер очереди задач",
      "type": "timeseries"
    },
    {
      "description": "Показывает среднюю задержку обработки одной задачи. Важный показатель производительности.",
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
            "fillOpacity": 0,
            "gradientMode": "none",
            "hideFrom": {
              "legend": false,
              "tooltip": false,
              "viz": false
            },
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
                "value": 80
              }
            ]
          },
          "unit": "s"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 9,
        "w": 12,
        "x": 0,
        "y": 19
      },
      "id": 6,
      "options": {
        "legend": {
          "calcs": [],
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
          "expr": "sum(rate(armeria_executor_seconds_sum{job=\"$job\", instance=~\"$instance\"}[$__rate_interval])) by (instance) / sum(rate(armeria_executor_seconds_count{job=\"$job\", instance=~\"$instance\"}[$__rate_interval])) by (instance)",
          "legendFormat": "{{instance}}",
          "refId": "A"
        }
      ],
      "title": "Среднее время выполнения задачи",
      "type": "timeseries"
    },
    {
      "description": "Помогает отслеживать аномальные задержки и выбросы.",
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
            "fillOpacity": 0,
            "gradientMode": "none",
            "hideFrom": {
              "legend": false,
              "tooltip": false,
              "viz": false
            },
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
                "value": 80
              }
            ]
          },
          "unit": "s"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 9,
        "w": 12,
        "x": 12,
        "y": 19
      },
      "id": 8,
      "options": {
        "legend": {
          "calcs": [],
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
          "expr": "armeria_executor_seconds_max{job=\"$job\", instance=~\"$instance\"}",
          "legendFormat": "{{instance}}",
          "refId": "A"
        }
      ],
      "title": "Максимальное время выполнения задачи",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 28
      },
      "id": 22,
      "panels": [],
      "title": "HTTP Сервер (Armeria Server)",
      "type": "row"
    },
    {
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
                "value": 80
              }
            ]
          },
          "unit": "short"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 9,
        "w": 12,
        "x": 0,
        "y": 29
      },
      "id": 10,
      "options": {
        "legend": {
          "calcs": [],
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
          "expr": "armeria_server_connections{job=\"$job\", instance=~\"$instance\"}",
          "legendFormat": "{{instance}}",
          "refId": "A"
        }
      ],
      "title": "Активные соединения",
      "type": "timeseries"
    },
    {
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
                "value": 80
              }
            ]
          },
          "unit": "ops"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 9,
        "w": 12,
        "x": 12,
        "y": 29
      },
      "id": 12,
      "options": {
        "legend": {
          "calcs": [],
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
          "expr": "sum(rate(armeria_server_router_virtual_host_cache_requests_total{job=\"$job\", instance=~\"$instance\"}[$__rate_interval])) by (instance)",
          "legendFormat": "requests - {{instance}}",
          "refId": "A"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "sum(rate(armeria_server_router_virtual_host_cache_evictions_total{job=\"$job\", instance=~\"$instance\"}[$__rate_interval])) by (instance)",
          "legendFormat": "evictions - {{instance}}",
          "refId": "B"
        }
      ],
      "title": "Производительность кеша роутера (запросов/сек)",
      "type": "timeseries"
    },
    {
      "collapsed": false,
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 38
      },
      "id": 23,
      "panels": [],
      "title": "Ресурсы (System Resources)",
      "type": "row"
    },
    {
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
                "value": 80
              }
            ]
          },
          "unit": "percent"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 9,
        "w": 12,
        "x": 0,
        "y": 39
      },
      "id": 24,
      "options": {
        "legend": {
          "calcs": [],
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
          "expr": "process_cpu_usage{job=\"$job\", instance=~\"$instance\"} * 100",
          "legendFormat": "{{instance}}",
          "refId": "A"
        }
      ],
      "title": "Использование CPU",
      "type": "timeseries"
    }
  ],
  "refresh": "1m",
  "schemaVersion": 37,
  "style": "dark",
  "tags": [
    "data-prepper",
    "armeria"
  ],
  "templating": {
    "list": [
      {
        "current": {},
        "datasource": {
          "type": "prometheus",
          "uid": "${DS_PROMETHEUS}"
        },
        "definition": "label_values(up, job)",
        "hide": 0,
        "includeAll": false,
        "multi": false,
        "name": "job",
        "options": [],
        "query": {
          "query": "label_values(up, job)",
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
        "definition": "label_values(up{job=\"$job\"}, instance)",
        "hide": 0,
        "includeAll": true,
        "multi": true,
        "name": "instance",
        "options": [],
        "query": {
          "query": "label_values(up{job=\"$job\"}, instance)",
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
  "title": "Data-prepper Мониторинг",
  "uid": "data-prepper-dashboard",
  "version": 1,
  "weekStart": ""
}
```