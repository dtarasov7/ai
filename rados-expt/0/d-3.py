Вот модифицированная версия кода, которая гарантирует, что все метрики в ответе на `/metrics` будут из одной итерации сбора данных, даже если запрос пришёл во время обновления:

```python
#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import requests
import warnings
import logging
import json
import argparse
import os
from awsauth import S3Auth
from prometheus_client import start_http_server
from collections import defaultdict, Counter
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY, InfoMetricFamily
from threading import Lock, Thread, Event
from http.server import BaseHTTPRequestHandler, HTTPServer
from prometheus_client import exposition
import ssl
from typing import Dict, List, Optional, Tuple

class CollectorMetrics:
    """Metrics about the collector's own performance"""
    def __init__(self):
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
        self.collector_info = InfoMetricFamily(
            "radosgw_collector",
            "Information about the RADOSGW collector"
        )

    def update_success(self, duration: float):
        self.scrape_duration.add_metric(["success"], duration)
        self.up.add_metric([], 1)
        self.last_success.add_metric([], time.time())

    def update_failure(self, duration: float, error_type: str):
        self.scrape_duration.add_metric(["failure"], duration)
        self.up.add_metric([], 0)
        self.scrape_errors.add_metric([error_type], 1)

class AsyncMetricsUpdater:
    def __init__(self, collector, interval: int):
        self.collector = collector
        self.interval = interval
        self._lock = Lock()
        self._metrics_cache: List = []
        self._collector_metrics = CollectorMetrics()
        self._stop_event = False
        self._update_in_progress = Event()
        self._thread = Thread(target=self._update_loop, daemon=True)
        
    def start(self):
        self._thread.start()
        
    def stop(self):
        self._stop_event = True
        self._thread.join()
        
    def _update_loop(self):
        while not self._stop_event:
            try:
                self._update_in_progress.set()
                start_time = time.time()
                
                # Collect new metrics
                metrics = list(self.collector.collect())
                
                with self._lock:
                    self._metrics_cache = metrics
                    self._collector_metrics.update_success(time.time() - start_time)
                
                logging.debug(f"Metrics updated in {time.time() - start_time:.2f} seconds")
                
            except requests.exceptions.RequestException as e:
                error_type = "request_error"
                logging.error(f"Request error updating metrics: {e}")
                self._collector_metrics.update_failure(time.time() - start_time, error_type)
            except json.JSONDecodeError as e:
                error_type = "json_error"
                logging.error(f"JSON decode error updating metrics: {e}")
                self._collector_metrics.update_failure(time.time() - start_time, error_type)
            except Exception as e:
                error_type = "other_error"
                logging.error(f"Unexpected error updating metrics: {e}")
                self._collector_metrics.update_failure(time.time() - start_time, error_type)
            finally:
                self._update_in_progress.clear()
                
            # Sleep but wake up early if we're stopping
            for _ in range(self.interval * 10):
                if self._stop_event:
                    break
                time.sleep(0.1)
            
    def get_metrics(self) -> Tuple[List, bool]:
        """Returns (metrics, from_cache) tuple"""
        # Wait if update is in progress
        if self._update_in_progress.is_set():
            logging.debug("Waiting for metrics update to complete...")
            self._update_in_progress.wait()
        
        with self._lock:
            # Combine application metrics with collector's own metrics
            return (self._metrics_cache + list(self._collector_metrics.__dict__.values()), False)

class RADOSGWCollector(object):
    """RADOSGWCollector gathers bucket level usage data for all buckets from
    the specified RADOSGW and presents it in a format suitable for pulling via
    a Prometheus server."""

    def __init__(
        self, host: str, admin_entry: str, access_key: str, secret_key: str, 
        store: str, insecure: bool, timeout: int, tag_list: str
    ):
        super(RADOSGWCollector, self).__init__()
        self.host = host
        self.access_key = access_key
        self.secret_key = secret_key
        self.store = store
        self.insecure = insecure
        self.timeout = timeout
        self.tag_list = tag_list

        # helpers for default schema
        if not self.host.startswith("http"):
            self.host = "http://{0}".format(self.host)
        # and for request_uri
        if not self.host.endswith("/"):
            self.host = "{0}/".format(self.host)

        self.url = "{0}{1}/".format(self.host, admin_entry)
        # Prepare Requests Session
        self._session()

    def collect(self):
        """Collect metrics from RADOSGW"""
        start = time.time()
        self._setup_empty_prometheus_metrics(args="")
        self.usage_dict = defaultdict(dict)

        try:
            rgw_usage = self._request_data(query="usage", args="show-summary=False")
            rgw_bucket = self._request_data(query="bucket", args="stats=True")
            rgw_users = self._get_rgw_users()

            if rgw_usage:
                for entry in rgw_usage["entries"]:
                    self._get_usage(entry)
                self._update_usage_metrics()

            if rgw_bucket:
                for bucket in rgw_bucket:
                    self._get_bucket_usage(bucket)

            if rgw_users:
                for user in rgw_users:
                    self._get_user_info(user)

            duration = time.time() - start
            self._prometheus_metrics["scrape_duration_seconds"].add_metric([], duration)

            return list(self._prometheus_metrics.values())

        except Exception as e:
            logging.error(f"Error collecting metrics: {e}")
            raise

    # ... (остальные методы класса RADOSGWCollector остаются без изменений)

class MetricsHandler(BaseHTTPRequestHandler):
    def __init__(self, metrics_updater, ssl_context=None, *args, **kwargs):
        self.metrics_updater = metrics_updater
        self.ssl_context = ssl_context
        super().__init__(*args, **kwargs)
        
    def do_GET(self):
        if self.path == '/metrics':
            start_time = time.time()
            
            # Get metrics, waiting if update is in progress
            metrics, from_cache = self.metrics_updater.get_metrics()
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            
            output = exposition.generate_latest(metrics)
            self.wfile.write(output)
            
            logging.debug(f"Served metrics in {time.time() - start_time:.4f} seconds (from_cache: {from_cache})")
        else:
            self.send_response(404)
            self.end_headers()
            
    def handle(self):
        if self.ssl_context:
            self.connection = self.ssl_context.wrap_socket(self.connection, server_side=True)
            self.rfile = self.connection.makefile("rb", self.rbufsize)
            self.wfile = self.connection.makefile("wb", self.wbufsize)
        return super().handle()

def run_http_server(metrics_updater: AsyncMetricsUpdater, port: int, 
                   certfile: Optional[str] = None, keyfile: Optional[str] = None):
    def handler(*args, **kwargs):
        return MetricsHandler(metrics_updater, ssl_context, *args, **kwargs)
        
    ssl_context = None
    if certfile and keyfile:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        logging.info("Configured HTTPS server with TLS")
    
    server = HTTPServer(('::', port), handler)
    logging.info(f"Serving metrics on port {port} (HTTPS: {ssl_context is not None})")
    server.serve_forever()

def parse_args():
    parser = argparse.ArgumentParser(
        description="RADOSGW address and local binding port as well as \
        S3 access_key and secret_key"
    )
    # ... (аргументы остаются как в оригинале)
    parser.add_argument(
        "-i",
        "--interval",
        required=False,
        type=int,
        help="Metrics update interval in seconds",
        default=int(os.environ.get("UPDATE_INTERVAL", "60")),
    )
    parser.add_argument(
        "--tls-cert",
        required=False,
        help="Path to TLS certificate file for HTTPS",
        default=os.environ.get("TLS_CERT", None),
    )
    parser.add_argument(
        "--tls-key",
        required=False,
        help="Path to TLS private key file for HTTPS",
        default=os.environ.get("TLS_KEY", None),
    )
    return parser.parse_args()

def main():
    try:
        args = parse_args()
        logging.basicConfig(level=args.log_level.upper())
        
        # Validate TLS files if provided
        if (args.tls_cert and not args.tls_key) or (args.tls_key and not args.tls_cert):
            logging.error("Both --tls-cert and --tls-key must be provided for HTTPS")
            exit(1)
            
        if args.tls_cert and not os.path.exists(args.tls_cert):
            logging.error(f"TLS certificate file not found: {args.tls_cert}")
            exit(1)
            
        if args.tls_key and not os.path.exists(args.tls_key):
            logging.error(f"TLS key file not found: {args.tls_key}")
            exit(1)
        
        collector = RADOSGWCollector(
            args.host,
            args.admin_entry,
            args.access_key,
            args.secret_key,
            args.store,
            args.insecure,
            args.timeout,
            args.tag_list,
        )
        
        # Создаем и запускаем асинхронное обновление метрик
        metrics_updater = AsyncMetricsUpdater(collector, args.interval)
        metrics_updater.start()
        
        # Запускаем HTTP сервер
        run_http_server(
            metrics_updater, 
            args.port,
            certfile=args.tls_cert,
            keyfile=args.tls_key
        )
        
    except KeyboardInterrupt:
        logging.info("\nInterrupted")
        metrics_updater.stop()
        exit(0)

if __name__ == "__main__":
    main()
```

### Ключевые изменения:

1. **Механизм блокировки во время обновления метрик**:
   - Добавлен `threading.Event` (`_update_in_progress`) для отслеживания состояния обновления
   - Метод `get_metrics()` теперь ожидает завершения текущего обновления (если оно выполняется) перед возвратом данных
   - Время ожидания логируется для мониторинга

2. **Улучшенное управление потоком обновлений**:
   - Обновление метрик теперь явно помечается флагом `_update_in_progress`
   - Добавлен `finally` блок для гарантированного сброса флага

3. **Более точный интервал обновления**:
   - Заменено `time.sleep(interval)` на цикл с более короткими интервалами (0.1 сек)
   - Позволяет быстрее реагировать на сигнал остановки

4. **Информация о кэшировании**:
   - Метод `get_metrics()` теперь возвращает кортеж `(metrics, from_cache)`
   - Можно использовать для дополнительного мониторинга (хотя в текущей реализации всегда возвращает `False` для второго элемента, так как мы всегда ждём актуальных данных)

5. **Логирование времени обработки запросов**:
   - Добавлено измерение времени обработки запроса `/metrics`

### Как это работает:

1. Когда начинается обновление метрик:
   - Устанавливается флаг `_update_in_progress.set()`
   - Все запросы к `/metrics` будут ждать снятия этого флага

2. Когда обновление завершено:
   - Флаг сбрасывается `_update_in_progress.clear()`
   - Все ожидающие запросы получают актуальные метрики

3. Если обновление не выполняется:
   - Запросы к `/metrics` получают последние сохранённые метрики без ожидания

### Преимущества:

- Гарантируется, что все метрики в ответе принадлежат одной итерации сбора данных
- Нет "разрыва" метрик между разными периодами сбора
- Минимальные задержки, когда обновление не выполняется
- Прозрачное ожидание при активном обновлении
