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
from prometheus_client import CollectorRegistry, GaugeMetricFamily, CounterMetricFamily, REGISTRY, exposition
from threading import Lock, Thread, Event
from http.server import BaseHTTPRequestHandler, HTTPServer
import ssl
from typing import Dict, List, Optional, Tuple

class CollectorMetrics:
    """Metrics about the collector's own performance"""
    def __init__(self):
        self._metrics = {}
        self._create_metrics()
    
    def _create_metrics(self):
        """Initialize/reset all metrics"""
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
            'scrape_errors': CounterMetricFamily(
                "radosgw_collector_scrape_errors_total",
                "Total number of errors encountered during scrapes",
                labels=["type"]
            ),
            'up': GaugeMetricFamily(
                "radosgw_collector_up",
                "Whether the collector was able to gather metrics (1 = success, 0 = failure)"
            ),
            'last_success': GaugeMetricFamily(
                "radosgw_collector_last_success_timestamp_seconds",
                "Unix timestamp of the last successful metrics collection"
            ),
            'scrape_wait_time': GaugeMetricFamily(
                "radosgw_collector_scrape_wait_seconds",
                "Time requests spent waiting for scrape to complete"
            )
        }
        # Initialize info metric once
        self._metrics['info'].add_metric(["1.0", "async"], 1)

    def update_success(self, duration: float):
        self._create_metrics()
        self._metrics['scrape_duration'].add_metric(["success"], duration)
        self._metrics['up'].add_metric([], 1)
        self._metrics['last_success'].add_metric([], time.time())

    def update_failure(self, duration: float, error_type: str):
        self._create_metrics()
        self._metrics['scrape_duration'].add_metric(["failure"], duration)
        self._metrics['up'].add_metric([], 0)
        self._metrics['scrape_errors'].add_metric([error_type], 1)

    def update_wait_time(self, wait_time: float):
        self._metrics['scrape_wait_time'].add_metric([], wait_time)

    def collect(self):
        """Return current metrics"""
        return list(self._metrics.values())

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
                
                # Collect application metrics
                app_metrics = list(self.collector.collect())
                
                with self._lock:
                    # Update collector metrics
                    self._collector_metrics.update_success(time.time() - start_time)
                    # Combine all metrics
                    self._metrics_cache = app_metrics + self._collector_metrics.collect()
                
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
            
    def get_metrics(self) -> List:
        """Get current metrics, waiting if update is in progress"""
        wait_start = time.time()
        had_to_wait = False
        
        if self._update_in_progress.is_set():
            had_to_wait = True
            logging.debug("Waiting for metrics update to complete...")
            self._update_in_progress.wait()
        
        wait_time = time.time() - wait_start
        if had_to_wait and wait_time > 0:
            self._collector_metrics.update_wait_time(wait_time)
        
        with self._lock:
            return self._metrics_cache.copy()

class RADOSGWCollector:
    """Collect RADOSGW metrics"""
    def __init__(self, host: str, admin_entry: str, access_key: str, 
                secret_key: str, store: str, insecure: bool, 
                timeout: int, tag_list: str):
        self.host = host
        self.access_key = access_key
        self.secret_key = secret_key
        self.store = store
        self.insecure = insecure
        self.timeout = timeout
        self.tag_list = tag_list

        if not self.host.startswith("http"):
            self.host = f"http://{self.host}"
        if not self.host.endswith("/"):
            self.host = f"{self.host}/"

        self.url = f"{self.host}{admin_entry}/"
        self._session()

    def _session(self):
        """Configure requests session"""
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, 
            pool_maxsize=10
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if not self.insecure:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    def collect(self):
        """Main collection method"""
        start = time.time()
        self._setup_empty_prometheus_metrics()
        self.usage_dict = defaultdict(dict)

        try:
            # Collect data from RadosGW
            rgw_usage = self._request_data("usage", "show-summary=False")
            rgw_bucket = self._request_data("bucket", "stats=True")
            rgw_users = self._get_rgw_users()

            if rgw_usage:
                for entry in rgw_usage.get("entries", []):
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
        """Initialize all metric containers"""
        b_labels = ["bucket", "owner", "category", "store"]
        if self.tag_list:
            b_labels += self.tag_list.split(",")

        self._prometheus_metrics = {
            "ops": CounterMetricFamily(
                "radosgw_usage_ops_total",
                "Number of operations",
                labels=b_labels,
            ),
            "successful_ops": CounterMetricFamily(
                "radosgw_usage_successful_ops_total",
                "Number of successful operations",
                labels=b_labels,
            ),
            "bytes_sent": CounterMetricFamily(
                "radosgw_usage_sent_bytes_total",
                "Bytes sent by the RADOSGW",
                labels=b_labels,
            ),
            "bytes_received": CounterMetricFamily(
                "radosgw_usage_received_bytes_total",
                "Bytes received by the RADOSGW",
                labels=b_labels,
            ),
            "bucket_usage_bytes": GaugeMetricFamily(
                "radosgw_usage_bucket_bytes",
                "Bucket used bytes",
                labels=b_labels,
            ),
            "bucket_utilized_bytes": GaugeMetricFamily(
                "radosgw_usage_bucket_utilized_bytes",
                "Bucket utilized bytes",
                labels=b_labels,
            ),
            "bucket_usage_objects": GaugeMetricFamily(
                "radosgw_usage_bucket_objects",
                "Number of objects in bucket",
                labels=b_labels,
            ),
            "bucket_quota_enabled": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_enabled",
                "Quota enabled for bucket",
                labels=b_labels,
            ),
            "bucket_quota_max_size": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_size",
                "Maximum allowed bucket size",
                labels=b_labels,
            ),
            "bucket_quota_max_size_bytes": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_size_bytes",
                "Maximum allowed bucket size in bytes",
                labels=b_labels,
            ),
            "bucket_quota_max_objects": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_size_objects",
                "Maximum allowed bucket size in number of objects",
                labels=b_labels,
            ),
            "bucket_shards": GaugeMetricFamily(
                "radosgw_usage_bucket_shards",
                "Number of shards in bucket",
                labels=b_labels,
            ),
            "user_metadata": GaugeMetricFamily(
                "radosgw_user_metadata",
                "User metadata",
                labels=["user", "display_name", "email", "storage_class", "store"],
            ),
            "user_quota_enabled": GaugeMetricFamily(
                "radosgw_usage_user_quota_enabled",
                "User quota enabled",
                labels=["user", "store"],
            ),
            "user_quota_max_size": GaugeMetricFamily(
                "radosgw_usage_user_quota_size",
                "Maximum allowed size for user",
                labels=["user", "store"],
            ),
            "user_quota_max_size_bytes": GaugeMetricFamily(
                "radosgw_usage_user_quota_size_bytes",
                "Maximum allowed size in bytes for user",
                labels=["user", "store"],
            ),
            "user_quota_max_objects": GaugeMetricFamily(
                "radosgw_usage_user_quota_size_objects",
                "Maximum allowed number of objects across all user buckets",
                labels=["user", "store"],
            ),
            "user_bucket_quota_enabled": GaugeMetricFamily(
                "radosgw_usage_user_bucket_quota_enabled",
                "User per-bucket-quota enabled",
                labels=["user", "store"],
            ),
            "user_bucket_quota_max_size": GaugeMetricFamily(
                "radosgw_usage_user_bucket_quota_size",
                "Maximum allowed size for each bucket of user",
                labels=["user", "store"],
            ),
            "user_bucket_quota_max_size_bytes": GaugeMetricFamily(
                "radosgw_usage_user_bucket_quota_size_bytes",
                "Maximum allowed size bytes size for each bucket of user",
                labels=["user", "store"],
            ),
            "user_bucket_quota_max_objects": GaugeMetricFamily(
                "radosgw_usage_user_bucket_quota_size_objects",
                "Maximum allowed number of objects in each user bucket",
                labels=["user", "store"],
            ),
            "user_total_objects": GaugeMetricFamily(
                "radosgw_usage_user_total_objects",
                "Usage of objects by user",
                labels=["user", "store"],
            ),
            "user_total_bytes": GaugeMetricFamily(
                "radosgw_usage_user_total_bytes",
                "Usage of bytes by user",
                labels=["user", "store"],
            ),
            "scrape_duration_seconds": GaugeMetricFamily(
                "radosgw_usage_scrape_duration_seconds",
                "Amount of time each scrape takes",
                labels=[],
            ),
        }

    def _request_data(self, query: str, args: str) -> Optional[Dict]:
        """Make API request to RadosGW"""
        url = f"{self.url}{query}/?format=json&{args}"
        try:
            response = self.session.get(
                url,
                verify=self.insecure,
                timeout=float(self.timeout),
                auth=S3Auth(self.access_key, self.secret_key, self.host),
            )
            if response.status_code == 200:
                return response.json()
            logging.error(f"Request failed: {response.status_code} - {response.text}")
        except Exception as e:
            logging.error(f"Request error: {e}")
        return None

    def _get_usage(self, entry: Dict):
        """Process usage data"""
        bucket_owner = entry.get("owner") or entry.get("user")
        if not bucket_owner:
            return

        if bucket_owner not in self.usage_dict:
            self.usage_dict[bucket_owner] = defaultdict(dict)

        for bucket in entry.get("buckets", []):
            bucket_name = bucket.get("bucket") or "bucket_root"
            if bucket_name not in self.usage_dict[bucket_owner]:
                self.usage_dict[bucket_owner][bucket_name] = defaultdict(dict)

            for category in bucket.get("categories", []):
                cat_name = category.get("category")
                if cat_name not in self.usage_dict[bucket_owner][bucket_name]:
                    self.usage_dict[bucket_owner][bucket_name][cat_name] = Counter()
                
                counter = self.usage_dict[bucket_owner][bucket_name][cat_name]
                counter.update({
                    "ops": category.get("ops", 0),
                    "successful_ops": category.get("successful_ops", 0),
                    "bytes_sent": category.get("bytes_sent", 0),
                    "bytes_received": category.get("bytes_received", 0),
                })

    def _update_usage_metrics(self):
        """Update Prometheus metrics from collected usage data"""
        for owner, buckets in self.usage_dict.items():
            for bucket_name, categories in buckets.items():
                for category, data in categories.items():
                    labels = [bucket_name, owner, category, self.store]
                    self._prometheus_metrics["ops"].add_metric(labels, data["ops"])
                    self._prometheus_metrics["successful_ops"].add_metric(labels, data["successful_ops"])
                    self._prometheus_metrics["bytes_sent"].add_metric(labels, data["bytes_sent"])
                    self._prometheus_metrics["bytes_received"].add_metric(labels, data["bytes_received"])

    def _get_bucket_usage(self, bucket: Dict):
        """Process bucket usage data"""
        if not isinstance(bucket, dict):
            return

        bucket_name = bucket.get("bucket")
        owner = bucket.get("owner")
        if not bucket_name or not owner:
            return

        # Extract basic bucket info
        zonegroup = bucket.get("zonegroup", "0")
        shards = bucket.get("num_shards", 0)
        usage_bytes = 0
        utilized_bytes = 0
        objects_count = 0

        # Process usage data
        if bucket.get("usage") and "rgw.main" in bucket["usage"]:
            usage = bucket["usage"]["rgw.main"]
            if "size_actual" in usage:
                usage_bytes = usage["size_actual"]
            elif "size_kb_actual" in usage:
                usage_bytes = usage["size_kb_actual"] * 1024
            
            if "size_utilized" in usage:
                utilized_bytes = usage["size_utilized"]
            
            if "num_objects" in usage:
                objects_count = usage["num_objects"]

        # Prepare labels
        labels = [bucket_name, owner, zonegroup, self.store]
        if self.tag_list and "tagset" in bucket:
            tags = bucket["tagset"]
            for tag in self.tag_list.split(","):
                if tag in tags:
                    labels.append(tags[tag])

        # Add metrics
        self._prometheus_metrics["bucket_usage_bytes"].add_metric(labels, usage_bytes)
        self._prometheus_metrics["bucket_utilized_bytes"].add_metric(labels, utilized_bytes)
        self._prometheus_metrics["bucket_usage_objects"].add_metric(labels, objects_count)
        self._prometheus_metrics["bucket_shards"].add_metric(labels, shards)

        # Add quota metrics if available
        if "bucket_quota" in bucket:
            quota = bucket["bucket_quota"]
            self._prometheus_metrics["bucket_quota_enabled"].add_metric(labels, quota["enabled"])
            self._prometheus_metrics["bucket_quota_max_size"].add_metric(labels, quota["max_size"])
            self._prometheus_metrics["bucket_quota_max_size_bytes"].add_metric(
                labels, quota["max_size_kb"] * 1024)
            self._prometheus_metrics["bucket_quota_max_objects"].add_metric(labels, quota["max_objects"])

    def _get_rgw_users(self) -> List:
        """Get list of RGW users"""
        users = self._request_data("user", "list")
        if users and "keys" in users:
            return users["keys"]
        
        # Fallback for older Ceph versions
        return self._request_data("metadata/user", "") or []

    def _get_user_info(self, user: str):
        """Get and process user info"""
        user_info = self._request_data("user", f"uid={user}&stats=True")
        if not user_info:
            return

        # Basic user info
        display_name = user_info.get("display_name", "")
        email = user_info.get("email", "")
        storage_class = user_info.get("default_storage_class", "")

        # Add user metadata metric
        self._prometheus_metrics["user_metadata"].add_metric(
            [user, display_name, email, storage_class, self.store], 1)

        # Add user stats if available
        if "stats" in user_info:
            stats = user_info["stats"]
            self._prometheus_metrics["user_total_bytes"].add_metric(
                [user, self.store], stats.get("size_actual", 0))
            self._prometheus_metrics["user_total_objects"].add_metric(
                [user, self.store], stats.get("num_objects", 0))

        # Add quota metrics
        if "user_quota" in user_info:
            quota = user_info["user_quota"]
            self._prometheus_metrics["user_quota_enabled"].add_metric(
                [user, self.store], quota["enabled"])
            self._prometheus_metrics["user_quota_max_size"].add_metric(
                [user, self.store], quota["max_size"])
            self._prometheus_metrics["user_quota_max_size_bytes"].add_metric(
                [user, self.store], quota["max_size_kb"] * 1024)
            self._prometheus_metrics["user_quota_max_objects"].add_metric(
                [user, self.store], quota["max_objects"])

        if "bucket_quota" in user_info:
            quota = user_info["bucket_quota"]
            self._prometheus_metrics["user_bucket_quota_enabled"].add_metric(
                [user, self.store], quota["enabled"])
            self._prometheus_metrics["user_bucket_quota_max_size"].add_metric(
                [user, self.store], quota["max_size"])
            self._prometheus_metrics["user_bucket_quota_max_size_bytes"].add_metric(
                [user, self.store], quota["max_size_kb"] * 1024)
            self._prometheus_metrics["user_bucket_quota_max_objects"].add_metric(
                [user, self.store], quota["max_objects"])

class MetricsHandler(BaseHTTPRequestHandler):
    def __init__(self, metrics_updater, *args, **kwargs):
        self.metrics_updater = metrics_updater
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == '/metrics':
            try:
                # Create registry and add metrics
                registry = CollectorRegistry()
                
                # Get current metrics
                metrics = self.metrics_updater.get_metrics()
                
                # Create temporary collector
                class TempCollector:
                    def collect(self):
                        return metrics
                
                registry.register(TempCollector())
                
                # Generate output
                output = exposition.generate_latest(registry)
                
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; version=0.0.4')
                self.end_headers()
                self.wfile.write(output)
                
            except Exception as e:
                logging.error(f"Failed to handle metrics request: {e}")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

def run_http_server(metrics_updater: AsyncMetricsUpdater, port: int, 
                   certfile: Optional[str] = None, keyfile: Optional[str] = None):
    """Run HTTP/HTTPS server with metrics endpoint"""
    
    def handler(*args, **kwargs):
        return MetricsHandler(metrics_updater, *args, **kwargs)
    
    # Configure SSL if certs are provided
    ssl_context = None
    if certfile and keyfile:
        if os.path.exists(certfile) and os.path.exists(keyfile):
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(certfile=certfile, keyfile=keyfile)
            logging.info(f"Configured HTTPS with cert: {certfile}, key: {keyfile}")
        else:
            logging.error("SSL files not found, falling back to HTTP")
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, handler)
    
    if ssl_context:
        httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)
        logging.info(f"Starting HTTPS server on port {port}")
    else:
        logging.info(f"Starting HTTP server on port {port}")
    
    httpd.serve_forever()

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="RADOSGW Prometheus Exporter with async updates",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Connection settings
    parser.add_argument(
        "-H", "--host",
        help="RADOSGW server host:port",
        default=os.environ.get("RADOSGW_HOST", "localhost:7480")
    )
    parser.add_argument(
        "-e", "--admin-entry",
        help="Admin API entry point",
        default=os.environ.get("ADMIN_ENTRY", "admin")
    )
    parser.add_argument(
        "-a", "--access-key",
        help="S3 access key",
        default=os.environ.get("ACCESS_KEY", "")
    )
    parser.add_argument(
        "-s", "--secret-key",
        help="S3 secret key",
        default=os.environ.get("SECRET_KEY", "")
    )
    parser.add_argument(
        "-k", "--insecure",
        help="Allow insecure SSL connections",
        action="store_true",
        default=os.environ.get("INSECURE", "false").lower() in ("true", "1", "yes")
    )
    
    # Exporter settings
    parser.add_argument(
        "-p", "--port",
        type=int,
        help="Exporter port",
        default=int(os.environ.get("EXPORTER_PORT", "9242"))
    )
    parser.add_argument(
        "-S", "--store",
        help="Store name for metrics labeling",
        default=os.environ.get("STORE_NAME", "default")
    )
    parser.add_argument(
        "-t", "--timeout",
        type=int,
        help="API request timeout in seconds",
        default=int(os.environ.get("REQUEST_TIMEOUT", "60"))
    )
    parser.add_argument(
        "-i", "--interval",
        type=int,
        help="Metrics update interval in seconds",
        default=int(os.environ.get("UPDATE_INTERVAL", "60"))
    )
    parser.add_argument(
        "-T", "--tag-list",
        help="Comma-separated list of bucket tags to include as labels",
        default=os.environ.get("BUCKET_TAGS", "")
    )
    
    # SSL settings
    parser.add_argument(
        "--tls-cert",
        help="Path to TLS certificate file",
        default=os.environ.get("TLS_CERT")
    )
    parser.add_argument(
        "--tls-key",
        help="Path to TLS private key file",
        default=os.environ.get("TLS_KEY")
    )
    
    # Logging
    parser.add_argument(
        "-l", "--log-level",
        help="Logging level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=os.environ.get("LOG_LEVEL", "INFO")
    )
    
    return parser.parse_args()

def main():
    """Main entry point"""
    try:
        args = parse_args()
        
        # Configure logging
        logging.basicConfig(
            level=args.log_level,
            format="%(asctime)s %(levelname)s: %(message)s",
            handlers=[logging.StreamHandler()]
        )
        
        # Validate SSL configuration
        if bool(args.tls_cert) != bool(args.tls_key):
            logging.error("Both --tls-cert and --tls-key must be specified for HTTPS")
            return 1
        
        # Initialize collector
        collector = RADOSGWCollector(
            host=args.host,
            admin_entry=args.admin_entry,
            access_key=args.access_key,
            secret_key=args.secret_key,
            store=args.store,
            insecure=args.insecure,
            timeout=args.timeout,
            tag_list=args.tag_list
        )
        
        # Start metrics updater
        metrics_updater = AsyncMetricsUpdater(collector, args.interval)
        metrics_updater.start()
        
        # Start HTTP server
        run_http_server(
            metrics_updater=metrics_updater,
            port=args.port,
            certfile=args.tls_cert,
            keyfile=args.tls_key
        )
        
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        metrics_updater.stop()
        return 0
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
