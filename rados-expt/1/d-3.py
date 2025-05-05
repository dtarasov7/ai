#!/usr/bin/python3
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
            "Information about the RADOSGW collector",
            value={
                "version": "1.0",
                "mode": "async"
            }
        )
        self.scrape_wait_time = GaugeMetricFamily(
            "radosgw_collector_scrape_wait_seconds",
            "Time requests spent waiting for scrape to complete"
        )

    def update_success(self, duration: float):
        self.scrape_duration.add_metric(["success"], duration)
        self.up.add_metric([], 1)
        self.last_success.add_metric([], time.time())

    def update_failure(self, duration: float, error_type: str):
        self.scrape_duration.add_metric(["failure"], duration)
        self.up.add_metric([], 0)
        self.scrape_errors.add_metric([error_type], 1)

    def update_wait_time(self, wait_time: float):
        self.scrape_wait_time.add_metric([], wait_time)

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
        self._last_update_time = 0
        
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
                    self._last_update_time = time.time()
                
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
        """Returns metrics and whether request had to wait"""
        wait_start = time.time()
        had_to_wait = False
        
        # Wait if update is in progress
        if self._update_in_progress.is_set():
            had_to_wait = True
            logging.debug("Waiting for metrics update to complete...")
            self._update_in_progress.wait()
        
        wait_time = time.time() - wait_start
        if had_to_wait and wait_time > 0:
            self._collector_metrics.update_wait_time(wait_time)
        
        with self._lock:
            # Combine application metrics with collector's own metrics
            all_metrics = self._metrics_cache + list(self._collector_metrics.__dict__.values())
            return (all_metrics, had_to_wait)

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
        if not self.host.endswith("/"):
            self.host = "{0}/".format(self.host)

        self.url = "{0}{1}/".format(self.host, admin_entry)
        self._session()

    def _session(self):
        """Setup Requests connection settings."""
        self.session = requests.Session()
        self.session_adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, pool_maxsize=10
        )
        self.session.mount("http://", self.session_adapter)
        self.session.mount("https://", self.session_adapter)

        if not self.insecure:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    def collect(self):
        """Collect metrics from RADOSGW"""
        start = time.time()
        self._setup_empty_prometheus_metrics()
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

    def _setup_empty_prometheus_metrics(self):
        """Initialize all metrics we want to export."""
        b_labels = ["bucket", "owner", "category", "store"]
        if self.tag_list:
            b_labels += self.tag_list.split(",")

        self._prometheus_metrics = {
            "ops": CounterMetricFamily(
                "radosgw_usage_ops_total",
                "Number of operations",
                labels=b_labels,
            ),
            # ... (остальные метрики остаются как в оригинале)
            "scrape_duration_seconds": GaugeMetricFamily(
                "radosgw_usage_scrape_duration_seconds",
                "Amount of time each scrape takes",
                labels=[],
            ),
        }

    # ... (остальные методы _request_data, _get_usage и т.д. остаются как в оригинале)

class MetricsHandler(BaseHTTPRequestHandler):
    def __init__(self, metrics_updater, ssl_context=None, *args, **kwargs):
        self.metrics_updater = metrics_updater
        self.ssl_context = ssl_context
        super().__init__(*args, **kwargs)
        
    def do_GET(self):
        if self.path == '/metrics':
            start_time = time.time()
            
            # Get metrics, waiting if update is in progress
            metrics, had_to_wait = self.metrics_updater.get_metrics()
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            
            output = exposition.generate_latest(metrics)
            self.wfile.write(output)
            
            logging.debug(f"Served metrics in {time.time() - start_time:.4f} seconds (waited: {had_to_wait})")
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
        description="RADOSGW metrics exporter with async updates"
    )
    parser.add_argument(
        "-H", "--host",
        help="RADOSGW server URL",
        default=os.environ.get("RADOSGW_SERVER", "http://radosgw:80"),
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        help="Port to listen",
        default=int(os.environ.get("VIRTUAL_PORT", "9242")),
    )
    parser.add_argument(
        "-i", "--interval",
        type=int,
        help="Metrics update interval in seconds",
        default=int(os.environ.get("UPDATE_INTERVAL", "60")),
    )
    parser.add_argument(
        "--tls-cert",
        help="Path to TLS certificate file",
        default=os.environ.get("TLS_CERT"),
    )
    parser.add_argument(
        "--tls-key",
        help="Path to TLS private key file",
        default=os.environ.get("TLS_KEY"),
    )
    # ... (остальные аргументы остаются как в оригинале)
    return parser.parse_args()

def main():
    try:
        args = parse_args()
        logging.basicConfig(
            level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            format='%(asctime)s %(levelname)s: %(message)s'
        )
        
        # Validate TLS configuration
        if bool(args.tls_cert) != bool(args.tls_key):
            logging.error("Both --tls-cert and --tls-key must be provided for HTTPS")
            exit(1)
            
        if args.tls_cert and not (os.path.exists(args.tls_cert) and os.path.exists(args.tls_key)):
            logging.error("TLS certificate or key file not found")
            exit(1)
        
        collector = RADOSGWCollector(
            args.host,
            os.environ.get("ADMIN_ENTRY", "admin"),
            os.environ.get("ACCESS_KEY", ""),
            os.environ.get("SECRET_KEY", ""),
            os.environ.get("STORE", "default"),
            not os.environ.get("INSECURE", "").lower() in ("false", "0", "no"),
            int(os.environ.get("TIMEOUT", "60")),
            os.environ.get("TAG_LIST", ""),
        )
        
        metrics_updater = AsyncMetricsUpdater(collector, args.interval)
        metrics_updater.start()
        
        run_http_server(
            metrics_updater, 
            args.port,
            certfile=args.tls_cert,
            keyfile=args.tls_key
        )
        
    except KeyboardInterrupt:
        logging.info("\nShutting down...")
        metrics_updater.stop()
        exit(0)

if __name__ == "__main__":
    main()
