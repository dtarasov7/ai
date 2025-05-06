�������� ������������ ������ ���������� ��������� ��-�� ����, ��� ��� ������ ���������� ������ ����������� ����� ����������, � ������ �� ���������. ��� ��� ��� ���������:

### ������� ��������:
1. ��� ������ ������ `update_success()`/`update_failure()` ����������� ����� �������
2. ������ ������� �������� � ������
3. ����� `collect()` ���������� ��� ����������� �������

### ������������ �������:

#### 1. ������������ ����� `CollectorMetrics`:

```python
class CollectorMetrics:
    def __init__(self):
        self._metrics = {}  # ������ ������� �������
        self._create_metrics()
    
    def _create_metrics(self):
        """�������/���������� ��� �������"""
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
            # ... ��������� ������� ...
        }
        # �������������� info-������� ���� ���
        self._metrics['info'].add_metric(["1.0", "async"], 1)

    def update_success(self, duration: float):
        self._create_metrics()  # ���������� ������� ����� �����������
        self._metrics['scrape_duration'].add_metric(["success"], duration)
        self._metrics['up'].add_metric([], 1)
        self._metrics['last_success'].add_metric([], time.time())

    def collect(self):
        """���������� ������ ������� �������"""
        return list(self._metrics.values())
```

#### 2. ��������� `AsyncMetricsUpdater`:

```python
class AsyncMetricsUpdater:
    def _update_loop(self):
        while not self._stop_event:
            try:
                self._update_in_progress.set()
                start_time = time.time()
                
                # �������� ������� ����������
                app_metrics = list(self.collector.collect())
                
                with self._lock:
                    # ��������� ������� ����������
                    self._collector_metrics.update_success(time.time() - start_time)
                    # ����������� �������
                    self._metrics_cache = app_metrics + self._collector_metrics.collect()
                
            # ... ��������� ������ ...
```

#### 3. �������� ����� `get_metrics()`:

```python
def get_metrics(self):
    if self._update_in_progress.is_set():
        self._update_in_progress.wait()
    
    with self._lock:
        return self._metrics_cache.copy()  # ���������� ����� ������� ������
```

### �������� ���������:
1. **����� ������ ����� ������ �����������** - `_create_metrics()` ����������� �������
2. **����� ���������� ��������� ������ ������** - ������ ������ ��������� ������
3. **��������� ����� `collect()`** ��� `CollectorMetrics`
4. **�������� ������������** - ������� �� ������������� �� ��������

### ���������:
������ ��� ������ ������� `/metrics` ����� ������������:
- ���������� ������� RADOSGW
- ������ ���� ��������� ������ ����������
- ���������� ��������� ����� ���������� ����������

��� ������� ��������� ������������� ������ ������ Prometheus, ��� ������� ������ ������������ ������� ��������� �������, � �� ����������� �������.
