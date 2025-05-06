Ошибка "unhashable type: 'CounterMetricFamily'" возникает при попытке использовать объект метрики как ключ словаря внутри `CollectorRegistry`. Давайте исправим это правильно:

### Полное исправленное решение:

```python
from prometheus_client import CollectorRegistry, Metric

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            start_time = time.time()
            
            # Получаем метрики
            metrics_list, had_to_wait = self.metrics_updater.get_metrics()
            
            # Создаем временный коллектор
            class TempCollector:
                def __init__(self, metrics):
                    self.metrics = metrics
                def collect(self):
                    return self.metrics
            
            # Создаем и наполняем registry
            registry = CollectorRegistry()
            registry.register(TempCollector(metrics_list))
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            
            output = exposition.generate_latest(registry)
            self.wfile.write(output)
```

### Альтернативный вариант (более правильный):

1. Модифицируем `AsyncMetricsUpdater`:

```python
def get_metrics(self):
    wait_start = time.time()
    had_to_wait = False
    
    if self._update_in_progress.is_set():
        had_to_wait = True
        self._update_in_progress.wait()
    
    wait_time = time.time() - wait_start
    if had_to_wait and wait_time > 0:
        self._collector_metrics.update_wait_time(wait_time)
    
    with self._lock:
        # Возвращаем готовый CollectorRegistry
        registry = CollectorRegistry()
        
        # Добавляем все метрики через временный коллектор
        class TempCollector:
            def collect(self):
                return self._metrics_cache + list(self._collector_metrics.__dict__.values())
        
        registry.register(TempCollector())
        return (registry, had_to_wait)
```

2. Тогда обработчик упрощается:

```python
def do_GET(self):
    if self.path == '/metrics':
        registry, had_to_wait = self.metrics_updater.get_metrics()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.end_headers()
        self.wfile.write(exposition.generate_latest(registry))
```

### Почему это работает:

1. Prometheus Client ожидает:
   - Либо готовый `CollectorRegistry` с зарегистрированными коллекторами
   - Либо объект с методом `collect()`, возвращающий список метрик

2. Наш временный `TempCollector`:
   - Обертывает список метрик
   - Реализует требуемый интерфейс `collect()`
   - Не требует хеширования метрик

3. Это решает проблему:
   - Нет попыток использовать метрики как ключи словаря
   - Сохраняется вся функциональность
   - Метрики остаются согласованными в рамках одной итерации

### Важное замечание:
Убедитесь, что все возвращаемые метрики являются подклассами `prometheus_client.Metric` (GaugeMetricFamily, CounterMetricFamily и т.д.). Если где-то возвращаются сырые данные, нужно обернуть их в соответствующие классы метрик.