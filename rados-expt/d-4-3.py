Проблема дублирования метрик коллектора возникает из-за того, что при каждом обновлении метрик добавляются новые экземпляры, а старые не очищаются. Вот как это исправить:

### Причина проблемы:
1. При каждом вызове `update_success()`/`update_failure()` добавляются новые метрики
2. Старые метрики остаются в памяти
3. Метод `collect()` возвращает все накопленные метрики

### Исправленное решение:

#### 1. Модифицируем класс `CollectorMetrics`:

```python
class CollectorMetrics:
    def __init__(self):
        self._metrics = {}  # Храним текущие метрики
        self._create_metrics()
    
    def _create_metrics(self):
        """Создаем/сбрасываем все метрики"""
        self._metrics = {
            'info': GaugeMetricFamily(
                "radosgw_collector_info",
                "Information about the RADOSGW collector",
                labels=["version", "mode"]
            ),
            'scrape_duration': GaugeMetricFamily(
                "radosgw_collector_scrape_duration_seconds",
                "Time taken for collector to gather metrics",
                labels=["status"]
            ),
            # ... остальные метрики ...
        }
        # Инициализируем info-метрику один раз
        self._metrics['info'].add_metric(["1.0", "async"], 1)

    def update_success(self, duration: float):
        self._create_metrics()  # Сбрасываем метрики перед обновлением
        self._metrics['scrape_duration'].add_metric(["success"], duration)
        self._metrics['up'].add_metric([], 1)
        self._metrics['last_success'].add_metric([], time.time())

    def collect(self):
        """Возвращает только текущие метрики"""
        return list(self._metrics.values())
```

#### 2. Обновляем `AsyncMetricsUpdater`:

```python
class AsyncMetricsUpdater:
    def _update_loop(self):
        while not self._stop_event:
            try:
                self._update_in_progress.set()
                start_time = time.time()
                
                # Собираем метрики приложения
                app_metrics = list(self.collector.collect())
                
                with self._lock:
                    # Обновляем метрики коллектора
                    self._collector_metrics.update_success(time.time() - start_time)
                    # Комбинируем метрики
                    self._metrics_cache = app_metrics + self._collector_metrics.collect()
                
            # ... обработка ошибок ...
```

#### 3. Упрощаем метод `get_metrics()`:

```python
def get_metrics(self):
    if self._update_in_progress.is_set():
        self._update_in_progress.wait()
    
    with self._lock:
        return self._metrics_cache.copy()  # Возвращаем копию текущих метрик
```

### Ключевые изменения:
1. **Сброс метрик перед каждым обновлением** - `_create_metrics()` пересоздает метрики
2. **Явное управление жизненным циклом метрик** - храним только последнюю версию
3. **Отдельный метод `collect()`** для `CollectorMetrics`
4. **Гарантия уникальности** - метрики не накапливаются со временем

### Результат:
Теперь при каждом запросе `/metrics` будут возвращаться:
- Актуальные метрики RADOSGW
- Только один экземпляр метрик коллектора
- Корректные временные метки последнего обновления

Это решение полностью соответствует модели работы Prometheus, где метрики должны представлять текущее состояние системы, а не накапливать историю.
