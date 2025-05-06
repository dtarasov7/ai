������ "unhashable type: 'CounterMetricFamily'" ��������� ��� ������� ������������ ������ ������� ��� ���� ������� ������ `CollectorRegistry`. ������� �������� ��� ���������:

### ������ ������������ �������:

```python
from prometheus_client import CollectorRegistry, Metric

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            start_time = time.time()
            
            # �������� �������
            metrics_list, had_to_wait = self.metrics_updater.get_metrics()
            
            # ������� ��������� ���������
            class TempCollector:
                def __init__(self, metrics):
                    self.metrics = metrics
                def collect(self):
                    return self.metrics
            
            # ������� � ��������� registry
            registry = CollectorRegistry()
            registry.register(TempCollector(metrics_list))
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            
            output = exposition.generate_latest(registry)
            self.wfile.write(output)
```

### �������������� ������� (����� ����������):

1. ������������ `AsyncMetricsUpdater`:

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
        # ���������� ������� CollectorRegistry
        registry = CollectorRegistry()
        
        # ��������� ��� ������� ����� ��������� ���������
        class TempCollector:
            def collect(self):
                return self._metrics_cache + list(self._collector_metrics.__dict__.values())
        
        registry.register(TempCollector())
        return (registry, had_to_wait)
```

2. ����� ���������� ����������:

```python
def do_GET(self):
    if self.path == '/metrics':
        registry, had_to_wait = self.metrics_updater.get_metrics()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.end_headers()
        self.wfile.write(exposition.generate_latest(registry))
```

### ������ ��� ��������:

1. Prometheus Client �������:
   - ���� ������� `CollectorRegistry` � ������������������� ������������
   - ���� ������ � ������� `collect()`, ������������ ������ ������

2. ��� ��������� `TempCollector`:
   - ���������� ������ ������
   - ��������� ��������� ��������� `collect()`
   - �� ������� ����������� ������

3. ��� ������ ��������:
   - ��� ������� ������������ ������� ��� ����� �������
   - ����������� ��� ����������������
   - ������� �������� �������������� � ������ ����� ��������

### ������ ���������:
���������, ��� ��� ������������ ������� �������� ����������� `prometheus_client.Metric` (GaugeMetricFamily, CounterMetricFamily � �.�.). ���� ���-�� ������������ ����� ������, ����� �������� �� � ��������������� ������ ������.