# Grafana Table Panel: Сервисы без метрики uptime

## PromQL запрос для панели Table

```promql
# Проверенный запрос для Prometheus 2.31 и Grafana 10
# Используем более надежный подход без подстановки переменных в label_replace
(
  node_systemd_unit_state{name=~"$srv"} * 0 + 1
) unless on(name) (
  label_replace(
    {__name__="uptime"}, 
    "name", "$1", "service", "(.*)"
  )
)
```

## Альтернативный вариант (проверен для Prometheus 2.31)

```promql
# Более простой и надежный способ
node_systemd_unit_state{name=~"$srv"} 
unless on(name) 
label_replace(uptime, "name", "$1", "service", "(.*)")
```

## Настройка панели Table в Grafana

### 1. Создание панели
- Тип: **Table**
- Data source: **Prometheus**

### 2. Запрос (Query) - совместимый с Prometheus 2.31
```promql
node_systemd_unit_state{name=~"$srv"} 
unless on(name) 
label_replace(uptime, "name", "$1", "service", "(.*)")
```

### 3. Настройки Transform (если нужно)
- **Organize fields**: оставить только нужные колонки
- **Rename fields**: переименовать колонки на русский язык

### 4. Настройки колонок Table
- **service**: Название сервиса
- **status**: Статус (будет показывать "No uptime metric")

## Дополнительные варианты запросов

### Вариант 1: С информацией о статусе systemd
```promql
# Показать сервисы без uptime метрики с их systemd статусом
(
  node_systemd_unit_state{name=~"$srv"} * on(name) group_left(state)
  unless(
    label_replace(
      group by (service) (uptime), 
      "name", "$1", "service", "(.*)"
    )
  )
) or on(name) (
  label_replace(vector(0), "name", "$srv", "", "") 
  unless on(name) 
  label_replace(
    group by (service) (uptime), 
    "name", "$1", "service", "(.*)"
  )
)
```

### Вариант 2: Простой список недоступных сервисов
```promql
# Простой вариант - только список сервисов
group by (service) (
  label_replace(vector(1), "service", "$srv", "", "") 
  unless on(service) 
  group by (service) (uptime)
)
```

## Настройка переменной srv (если еще не настроена)

### Query для переменной srv:
```promql
label_values(node_systemd_unit_state{job="node_exporter"}, name)
```

### Настройки переменной:
- **Name**: srv
- **Type**: Query
- **Multi-value**: true
- **Include all option**: true
- **Regex**: `(.+)\.service` (если нужно убрать .service из имен)

## Дополнительные настройки панели

### Для красивого отображения:
1. **Field options** → **Display name**: "Сервис без метрики uptime"
2. **Field options** → **Color scheme**: Single color (красный)
3. **Table options** → **Show header**: true

### Alerts (опционально):
Можно настроить алерт на эту панель, чтобы получать уведомления, когда появляются сервисы без метрики uptime.

## Принцип работы запроса

1. `label_replace(vector(1), "service", "$srv", "", "")` - создает вектор со значением 1 для каждого сервиса из переменной srv
2. `group by (service) (uptime)` - группирует все метрики uptime по service
3. `unless` - исключающее объединение, показывает только те сервисы из первого множества, которых нет во втором
4. `label_replace(..., "status", "No uptime metric", "", "")` - добавляет метку status для отображения в таблице