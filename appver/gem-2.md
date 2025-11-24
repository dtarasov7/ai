Конечно, вот подробное руководство по отображению истории изменения версий программного обеспечения в Grafana с использованием Prometheus и панели State timeline, а также готовый JSON-файл дашборда.

Указанные вами версии (Prometheus v2.31 и Grafana v11) полностью поддерживают необходимый функционал.

### Концепция решения

Идея состоит в том, чтобы использовать панель **State timeline** (Временная шкала состояний), которая идеально подходит для визуализации изменений дискретных состояний во времени. В вашем случае "состоянием" является версия программного обеспечения.

Метрика `app` с метками `nodename`, `appname` и `version` предоставляет все необходимые данные. Например, когда версия ПО меняется с `1.5.2` на `1.6.0`, Prometheus прекращает получать данные для временного ряда с меткой `version="1.5.2"` и начинает получать данные для нового ряда с `version="1.6.0"`. Панель State timeline отследит это и отобразит как смену состояния.

Ключевым моментом является указание Grafana использовать значение метки `version` в качестве отображаемого имени состояния.

***

### Шаг 1: PromQL запрос

Запрос будет очень простым. Нам нужно выбрать все временные ряды для конкретного приложения (`appname`) и хоста (`nodename`). Чтобы сделать дашборд интерактивным, мы будем использовать переменные Grafana `$appname` и `$nodename`.

```promql
app{appname=~"$appname", nodename=~"$nodename"}
```

Этот запрос вернет набор временных рядов, где каждый уникальный набор меток (включая `version`) будет отдельным рядом.

### Шаг 2: Настройка панели Grafana

1.  **Создайте новую панель** и выберите тип визуализации **State timeline**.
2.  **В редакторе запросов** введите указанный выше PromQL-запрос.
3.  **Настройте легенду (самый важный шаг)**: в поле **Legend** (Легенда) введите `{{version}}`. Эта конструкция заставит Grafana для каждого временного ряда отображать в качестве имени значение его метки `version`.
4.  **Настройка отображения**: в опциях панели (справа) можно настроить внешний вид. Например, в разделе **Value mappings** (Сопоставления значений) можно задать конкретные цвета для определенных версий, если это необходимо. Однако панель автоматически присвоит свой цвет каждой новой версии.

В результате панель State timeline будет отображать полосы разного цвета для каждой версии ПО. Текст на этих полосах будет соответствовать номеру версии, а длина полосы — времени, в течение которого эта версия была активна.

***

### Шаг 3: JSON модель дашборда

Ниже представлен готовый JSON-код для дашборда. Он включает в себя:

*   Две переменные (`appname` и `nodename`) для удобной фильтрации.
*   Одну панель типа **State timeline**, настроенную для отображения истории версий.

**Как импортировать дашборд:**

1.  Скопируйте весь JSON-код ниже.
2.  В Grafana перейдите в раздел **Dashboards**.
3.  Нажмите **New** и выберите **Import**.
4.  Вставьте скопированный JSON-код в текстовое поле и нажмите **Load**.
5.  Выберите ваш источник данных Prometheus и завершите импорт.

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
      "version": "11.0.0"
    },
    {
      "type": "datasource",
      "id": "prometheus",
      "name": "Prometheus",
      "version": "1.0.0"
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
      "title": "История версий ПО: $appname на $nodename",
      "type": "statetimeline",
      "datasource": {
        "type": "prometheus",
        "uid": "${DS_PROMETHEUS}"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "align": "auto",
            "displayMode": "auto"
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
        "mergeValues": true,
        "rowHeight": 0.9,
        "showValue": "always",
        "tooltip": {
          "mode": "single",
          "sort": "none"
        }
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "${DS_PROMETHEUS}"
          },
          "editorMode": "code",
          "expr": "app{appname=~\"$appname\", nodename=~\"$nodename\"}",
          "legendFormat": "{{version}}",
          "range": true,
          "refId": "A"
        }
      ]
    }
  ],
  "refresh": "",
  "schemaVersion": 39,
  "style": "dark",
  "tags": [
    "prometheus",
    "version-tracking"
  ],
  "templating": {
    "list": [
      {
        "current": {},
        "datasource": {
          "type": "prometheus",
          "uid": "${DS_PROMETHEUS}"
        },
        "definition": "label_values(app, appname)",
        "hide": 0,
        "includeAll": false,
        "multi": false,
        "name": "appname",
        "options": [],
        "query": {
          "query": "label_values(app, appname)",
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
        "definition": "label_values(app{appname=~\"$appname\"}, nodename)",
        "hide": 0,
        "includeAll": true,
        "multi": false,
        "name": "nodename",
        "options": [],
        "query": {
          "query": "label_values(app{appname=~\"$appname\"}, nodename)",
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
  "uid": null,
  "version": 1,
  "weekStart": ""
}

```
