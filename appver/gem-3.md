Отличный вопрос! Это классическая задача по отслеживанию состояний (в данном случае, версий ПО) с помощью Prometheus и Grafana. Указанные версии (Prometheus v2.49, Grafana v11) прекрасно подходят для ее решения.

Давайте разберем оба пункта по порядку и в конце соберем это в готовый JSON дашборд.

### Подготовка: Как должна выглядеть метрика

Для решения задачи нам нужна метрика, которая существует, пока приложение определенной версии работает на хосте. Обычно это gauge-метрика со значением `1`.

Назовем её `app_version_info`. Приложение должно отдавать её в следующем формате:

```
# HELP app_version_info Information about the application version.
# TYPE app_version_info gauge
app_version_info{nodename="server-01", appname="api-gateway", version="1.2.3"} 1
app_version_info{nodename="server-02", appname="api-gateway", version="1.2.3"} 1
app_version_info{nodename="server-01", appname="user-service", version="2.5.0"} 1
```

Когда `api-gateway` на `server-01` обновится до версии `1.2.4`, старая метрика (`...version="1.2.3"}`) перестанет поступать, а вместо неё появится новая (`...version="1.2.4"}`). Prometheus зафиксирует это изменение.

---

### 1. Таблица с последним изменением и предыдущей версией

Это самая сложная часть задачи, так как PromQL не очень хорошо спроектирован для поиска "предыдущего" значения метки в прошлом. Однако, с помощью мощных запросов и преобразований (transformations) в Grafana 11, мы можем добиться желаемого результата.

Мы создадим панель типа **Table** и используем один сложный PromQL-запрос, который выберет две последние версии для каждой комбинации `nodename` и `appname`.

#### PromQL-запрос

Этот запрос находит временную метку, когда каждая версия была видна в последний раз, а затем `topk(2, ...)` оставляет только две самые свежие для каждой группы `(nodename, appname)`.

```promql
topk by (nodename, appname) (
  2,
  max by (nodename, appname, version) (
    last_over_time(timestamp(app_version_info[$__range]))
  )
)
```

#### Настройка панели в Grafana

1.  Создайте новую панель и выберите визуализацию **Table**.
2.  Вставьте приведенный выше PromQL-запрос.
3.  В опциях запроса установите `Format: Table` и `Type: Range`.
4.  Теперь самое главное — **преобразования (Transformations)**. Нам нужно "развернуть" две строки, которые вернет запрос для каждого приложения, в одну строку с нужными колонками.

    *   **Transform 1: Sort data**
        *   **Sort by:** `Time`
        *   **Order:** `Descending` (сначала самая новая версия).
    *   **Transform 2: Group by**
        *   **Group by:** `nodename`, `appname` (поля, которые уникально идентифицируют наше приложение).
        *   **Calculations:**
            *   `version` -> `First` -> `current_version` (первая в отсортированном списке — текущая).
            *   `Time` -> `First` -> `last_change_time` (её время — время последнего изменения).
            *   `version` -> `Last` -> `previous_version` (последняя в отсортированном списке — предыдущая).

5.  Чтобы убрать ненужные колонки, можно добавить трансформацию **Organize fields** и скрыть все, кроме `nodename`, `appname`, `current_version`, `previous_version`, `last_change_time`.

В итоге вы получите таблицу вида:

| nodename | appname | current_version | previous_version | last_change_time |
| :--- | :--- | :--- | :--- | :--- |
| server-01 | api-gateway | 1.2.4 | 1.2.3 | 2024-05-21 10:00:00 |
| server-01 | user-service | 2.5.0 | 2.4.9 | 2024-05-20 15:30:00 |

---

### 2. История изменения версий во времени (State timeline)

Эта задача идеально решается с помощью панели **State timeline**. Она создана как раз для отображения дискретных состояний (строк, перечислений) во времени.

Проблема в том, что версия у нас находится в *метке* (`label`), а панели Grafana обычно работают со *значением* (`value`). Нам нужно "закодировать" уникальную комбинацию меток в числовое значение.

#### PromQL-запрос

Функция `group()` в PromQL создает хэш (число) от всех меток временного ряда. Каждая уникальная комбинация `(nodename, appname, version)` получит свое уникальное числовое значение.

```promql
group(app_version_info{nodename=~"$nodename", appname=~"$appname"})
```
*Здесь `$nodename` и `$appname` — это переменные дашборда для удобной фильтрации. Мы добавим их в JSON.*

#### Настройка панели в Grafana

1.  Создайте новую панель и выберите визуализацию **State timeline**.
2.  Вставьте PromQL-запрос выше.
3.  **Ключевой шаг:** Нам нужно, чтобы панель отображала не числовое значение, а текст из метки `version`. Для этого используем преобразование.
    *   Перейдите на вкладку **Transformations**.
    *   Добавьте преобразование **"Extract fields"**.
        *   **Source:** `Labels`
        *   **Format:** `version -> field version` (или просто выберите `version` из списка).
        *   Это создаст новое поле (колонку) с именем `version`, содержащее значение из соответствующей метки.

4.  **Настройка отображения:**
    *   В настройках панели (`Panel options`) найдите секцию **"State timeline"**.
    *   **Text:** Установите значение `auto` или явно выберите поле `${__field.version}`. Grafana v11 достаточно умна, чтобы подхватить строковое поле.
    *   **Color scheme:** Выберите `From thresholds (by value)`. Это будет раскрашивать каждую версию в свой цвет.

Теперь на панели вы увидите цветные полосы, где каждая полоса соответствует определенной версии ПО, и на ней будет написан номер этой версии. Переходы между цветами будут означать моменты обновления.

---

### Готовый JSON дашборда

Вот полный JSON для дашборда, который включает в себя:
*   Переменные для фильтрации по `nodename` и `appname`.
*   Панель "Таблица изменений версий" (пункт 1).
*   Панель "История версий (State Timeline)" (пункт 2).

**Как импортировать:**
1.  В Grafana перейдите в `Dashboards`.
2.  Нажмите `New` -> `Import`.
3.  Вставьте этот JSON в текстовое поле и следуйте инструкциям.

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
      "version": "10.0.0"
    },
    {
      "type": "datasource",
      "id": "prometheus",
      "name": "Prometheus",
      "version": "1.0.0"
    },
    {
      "type": "panel",
      "id": "table",
      "name": "Table",
      "version": ""
    },
    {
      "type": "panel",
      "id": "statetimeline",
      "name": "State timeline",
      "version": ""
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
  "panels": [
    {
      "id": 1,
      "title": "История версий (State Timeline)",
      "type": "statetimeline",
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": {
        "h": 9,
        "w": 24,
        "x": 0,
        "y": 0
      },
      "options": {
        "alignValue": "center",
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "rowHeight": 0.9,
        "showValue": "always",
        "tooltip": {
          "mode": "single",
          "sort": "none"
        }
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
              }
            ]
          }
        },
        "overrides": []
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "group(app_version_info{nodename=~\"$nodename\", appname=~\"$appname\"})",
          "legendFormat": "{{nodename}} - {{appname}} - {{version}}",
          "refId": "A"
        }
      ],
      "transformations": [
        {
          "id": "extractFields",
          "options": {
            "source": "labels",
            "fields": {
              "version": "version"
            }
          }
        }
      ]
    },
    {
      "id": 2,
      "title": "Таблица изменений версий",
      "type": "table",
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "gridPos": {
        "h": 9,
        "w": 24,
        "x": 0,
        "y": 9
      },
      "options": {
        "footer": {
          "countRows": false,
          "fields": "",
          "reducer": [
            "sum"
          ],
          "show": false
        },
        "showHeader": true
      },
      "fieldConfig": {
        "defaults": {
          "custom": {
            "align": "auto",
            "cellOptions": {
              "type": "auto"
            },
            "inspect": false
          },
          "mappings": []
        },
        "overrides": [
          {
            "matcher": {
              "id": "byName",
              "options": "last_change_time"
            },
            "properties": [
              {
                "id": "unit",
                "value": "time:YYYY-MM-DD HH:mm:ss"
              }
            ]
          }
        ]
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "expr": "topk by (nodename, appname) (\n  2,\n  max by (nodename, appname, version) (\n    last_over_time(timestamp(app_version_info{nodename=~\"$nodename\", appname=~\"$appname\"})[$__range])\n  )\n)",
          "format": "table",
          "instant": false,
          "refId": "A"
        }
      ],
      "transformations": [
        {
          "id": "sortBy",
          "options": {
            "fields": {},
            "sort": [
              {
                "desc": true,
                "field": "Time"
              }
            ]
          }
        },
        {
          "id": "groupBy",
          "options": {
            "fields": {
              "nodename": {
                "aggregator": "first",
                "operation": ""
              },
              "appname": {
                "aggregator": "first",
                "operation": ""
              },
              "version": {
                "aggregations": [
                  "first",
                  "last"
                ],
                "operation": "aggregate"
              },
              "Time": {
                "aggregations": [
                  "first"
                ],
                "operation": "aggregate"
              }
            }
          }
        },
        {
          "id": "organize",
          "options": {
            "indexByName": {
              "nodename": 0,
              "appname": 1,
              "First (version)": 2,
              "Last (version)": 3,
              "First (Time)": 4,
              "Time": 5,
              "Value": 6,
              "version": 7
            },
            "renameByName": {
              "First (Time)": "last_change_time",
              "First (version)": "current_version",
              "Last (version)": "previous_version",
              "Time": null,
              "Value": null,
              "version": null
            }
          }
        }
      ]
    }
  ],
  "refresh": "5m",
  "schemaVersion": 39,
  "tags": [],
  "templating": {
    "list": [
      {
        "current": {
          "selected": false,
          "text": "All",
          "value": "$__all"
        },
        "datasource": {
          "type": "prometheus",
          "uid": "${DS_PROMETHEUS}"
        },
        "definition": "label_values(app_version_info, nodename)",
        "hide": 0,
        "includeAll": true,
        "multi": true,
        "name": "nodename",
        "options": [],
        "query": {
          "query": "label_values(app_version_info, nodename)",
          "refId": "StandardVariableQuery"
        },
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
        "sort": 0,
        "type": "query"
      },
      {
        "current": {
          "selected": false,
          "text": "All",
          "value": "$__all"
        },
        "datasource": {
          "type": "prometheus",
          "uid": "${DS_PROMETHEUS}"
        },
        "definition": "label_values(app_version_info{nodename=~\"$nodename\"}, appname)",
        "hide": 0,
        "includeAll": true,
        "multi": true,
        "name": "appname",
        "options": [],
        "query": {
          "query": "label_values(app_version_info{nodename=~\"$nodename\"}, appname)",
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
    "from": "now-24h",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "browser",
  "title": "Отслеживание версий ПО",
  "uid": "version-tracking",
  "version": 1,
  "weekStart": ""
}
```
