�� �����, � `prometheus_client` ��� ������ `InfoMetricFamily`. ��� ���������� �������������� ������ ����� ������������ `GaugeMetricFamily` � ������� labels. ��� ������������ �������:

### ������������ ��� ��� ������ ����������:

```python
class CollectorMetrics:
    """Metrics about the collector's own performance"""
    def __init__(self):
        # �������� InfoMetricFamily �� GaugeMetricFamily � labels
        self.collector_version = GaugeMetricFamily(
            "radosgw_collector_info",
            "Information about the RADOSGW collector",
            labels=["version", "mode"]
        )
        
        # ��������� ������� �������� ��� ���������
        self.scrape_duration = GaugeMetricFamily(
            "radosgw_collector_scrape_duration_seconds",
            "Time taken for collector to gather metrics",
            labels=["status"]
        )
        # ... ��������� ������� ...
```

### ����������� ����� �������������:

```python
def update_success(self, duration: float):
    # ��������� ���������� � ������
    self.collector_version.add_metric(
        ["1.0", "async"], 
        1  # �������� ������ 1 ��� info-������
    )
    self.scrape_duration.add_metric(["success"], duration)
    self.up.add_metric([], 1)
    self.last_success.add_metric([], time.time())
```

### ������ ��� ��������:

1. � Prometheus ��� ������������ ���� ��� info-������
2. �������� ������� - ������������ Gauge �� ��������� 1 � labels ��� �������� ����������
3. ������ ������� � Prometheus:
   ```
   radosgw_collector_info{version="1.0", mode="async"} 1
   ```

### ������ ������������ ����� CollectorMetrics:

```python
class CollectorMetrics:
    """Metrics about the collector's own performance"""
    def __init__(self):
        self.collector_version = GaugeMetricFamily(
            "radosgw_collector_info",
            "Information about the RADOSGW collector",
            labels=["version", "mode"]
        )
        self.scrape_duration = GaugeMetricFamily(
            "radosgw_collector_scrape_duration_seconds",
            "Time taken for collector to gather metrics",
            labels=["status"]
        )
        self.scrape_errors = CounterMetricFamily(
            "radosgw_collector_scrape_errors_total",
            "Total number of errors encountered during scrapes",
            labels=["type"]
        )
        self.up = GaugeMetricFamily(
            "radosgw_collector_up",
            "Whether the collector was able to gather metrics (1 = success, 0 = failure)"
        )
        self.last_success = GaugeMetricFamily(
            "radosgw_collector_last_success_timestamp_seconds",
            "Unix timestamp of the last successful metrics collection"
        )
        self.scrape_wait_time = GaugeMetricFamily(
            "radosgw_collector_scrape_wait_seconds",
            "Time requests spent waiting for scrape to complete"
        )

    def update_success(self, duration: float):
        self.collector_version.add_metric(["1.0", "async"], 1)
        self.scrape_duration.add_metric(["success"], duration)
        self.up.add_metric([], 1)
        self.last_success.add_metric([], time.time())

    def update_failure(self, duration: float, error_type: str):
        self.scrape_duration.add_metric(["failure"], duration)
        self.up.add_metric([], 0)
        self.scrape_errors.add_metric([error_type], 1)

    def update_wait_time(self, wait_time: float):
        self.scrape_wait_time.add_metric([], wait_time)
```

��� ����������� ������ ��� ���������� info-������ � Prometheus, ������� ����� ��������� �������� � ���������� ����������� Python.
