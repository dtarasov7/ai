Вот модифицированная версия кода с поддержкой HTTPS и дополнительными метриками для мониторинга работы самого коллектора:

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
from threading import Lock, Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from prometheus_client import exposition
import ssl
from typing import Dict, List, Optional

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
        self._thread = Thread(target=self._update_loop, daemon=True)
        
    def start(self):
        self._thread.start()
        
    def stop(self):
        self._stop_event = True
        self._thread.join()
        
    def _update_loop(self):
        while not self._stop_event:
            try:
                start_time = time.time()
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
                
            time.sleep(self.interval)
            
    def get_metrics(self) -> List:
        with self._lock:
            # Combine application metrics with collector's own metrics
            return self._metrics_cache + list(self._collector_metrics.__dict__.values())

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
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            
            metrics = self.metrics_updater.get_metrics()
            output = exposition.generate_latest(metrics)
            self.wfile.write(output)
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

1. **Поддержка HTTPS**:
   - Добавлены параметры командной строки `--tls-cert` и `--tls-key`
   - Реализована загрузка SSL-сертификата и ключа
   - Модифицирован `MetricsHandler` для поддержки SSL
   - Добавлена проверка существования TLS-файлов при старте

2. **Метрики работы коллектора**:
   - Добавлен класс `CollectorMetrics` для отслеживания:
     - Времени сбора метрик (`radosgw_collector_scrape_duration_seconds`)
     - Ошибок (`radosgw_collector_scrape_errors_total`)
     - Статуса работы (`radosgw_collector_up`)
     - Времени последнего успешного сбора (`radosgw_collector_last_success_timestamp_seconds`)
     - Информации о коллекторе (`radosgw_collector_info`)

3. **Улучшенная обработка ошибок**:
   - Разные типы ошибок (HTTP, JSON, другие) теперь учитываются отдельно
   - Добавлено логирование ошибок с подробностями

4. **Типизация**:
   - Добавлены аннотации типов для лучшей читаемости кода

### Как использовать HTTPS:

1. Сгенерируйте сертификат и ключ (например, с помощью Let's Encrypt или self-signed):
   ```bash
   openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
   ```

2. Запустите коллектор с параметрами:
   ```bash
   python r-src.py --tls-cert cert.pem --tls-key key.pem -p 9242
   ```

3. Теперь метрики будут доступны по HTTPS:
   ```bash
   curl -k https://localhost:9242/metrics
   ```

### Новые метрики коллектора:

- `radosgw_collector_scrape_duration_seconds{status="success"}` - время успешного сбора метрик
- `radosgw_collector_scrape_duration_seconds{status="failure"}` - время неудачного сбора
- `radosgw_collector_scrape_errors_total{type="request_error"}` - ошибки запросов
- `radosgw_collector_scrape_errors_total{type="json_error"}` - ошибки парсинга JSON
- `radosgw_collector_scrape_errors_total{type="other_error"}` - прочие ошибки
- `radosgw_collector_up` - статус работы (1 = успешно, 0 = ошибка)
- `radosgw_collector_last_success_timestamp_seconds` - время последнего успеха
- `radosgw_collector_info` - информация о версии и конфигурации коллектора

Эти метрики помогут мониторить здоровье самого коллектора и оперативно выявлять проблемы.
