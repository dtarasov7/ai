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
                
            for _ in range(self.interval * 10):
                if self._stop_event:
                    break
                time.sleep(0.1)
            
    def get_metrics(self) -> Tuple[List, bool]:
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
            all_metrics = self._metrics_cache + list(self._collector_metrics.__dict__.values())
            return (all_metrics, had_to_wait)

class RADOSGWCollector(object):
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

        if not self.host.startswith("http"):
            self.host = "http://{0}".format(self.host)
        if not self.host.endswith("/"):
            self.host = "{0}/".format(self.host)

        self.url = "{0}{1}/".format(self.host, admin_entry)
        self._session()

    def _session(self):
        self.session = requests.Session()
        self.session_adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, pool_maxsize=10
        )
        self.session.mount("http://", self.session_adapter)
        self.session.mount("https://", self.session_adapter)

        if not self.insecure:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    def collect(self):
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

    def _request_data(self, query, args):
        url = "{0}{1}/?format=json&{2}".format(self.url, query, args)

        try:
            response = self.session.get(
                url,
                verify=self.insecure,
                timeout=float(self.timeout),
                auth=S3Auth(self.access_key, self.secret_key, self.host),
            )

            if response.status_code == requests.codes.ok:
                logging.debug(response)
                return response.json()
            else:
                logging.error(
                    "Request error [{0}]: {1}".format(
                        response.status_code, response.content.decode("utf-8")
                    )
                )
                return None

        except requests.exceptions.RequestException as e:
            logging.info("Request error: {0}".format(e))
            return None

    def _get_usage(self, entry):
        if "owner" in entry:
            bucket_owner = entry["owner"]
        elif "user" in entry:
            bucket_owner = entry["user"]

        if bucket_owner not in list(self.usage_dict.keys()):
            self.usage_dict[bucket_owner] = defaultdict(dict)

        for bucket in entry["buckets"]:
            logging.debug((json.dumps(bucket, indent=4, sort_keys=True)))

            if not bucket["bucket"]:
                bucket_name = "bucket_root"
            else:
                bucket_name = bucket["bucket"]

            if bucket_name not in list(self.usage_dict[bucket_owner].keys()):
                self.usage_dict[bucket_owner][bucket_name] = defaultdict(dict)

            for category in bucket["categories"]:
                category_name = category["category"]
                if category_name not in list(self.usage_dict[bucket_owner][bucket_name].keys()):
                    self.usage_dict[bucket_owner][bucket_name][category_name] = Counter()
                c = self.usage_dict[bucket_owner][bucket_name][category_name]
                c.update({
                    "ops": category["ops"],
                    "successful_ops": category["successful_ops"],
                    "bytes_sent": category["bytes_sent"],
                    "bytes_received": category["bytes_received"],
                })

    def _update_usage_metrics(self):
        for bucket_owner in list(self.usage_dict.keys()):
            for bucket_name in list(self.usage_dict[bucket_owner].keys()):
                for category in list(self.usage_dict[bucket_owner][bucket_name].keys()):
                    data_dict = self.usage_dict[bucket_owner][bucket_name][category]
                    self._prometheus_metrics["ops"].add_metric(
                        [bucket_name, bucket_owner, category, self.store],
                        data_dict["ops"],
                    )
                    self._prometheus_metrics["successful_ops"].add_metric(
                        [bucket_name, bucket_owner, category, self.store],
                        data_dict["successful_ops"],
                    )
                    self._prometheus_metrics["bytes_sent"].add_metric(
                        [bucket_name, bucket_owner, category, self.store],
                        data_dict["bytes_sent"],
                    )
                    self._prometheus_metrics["bytes_received"].add_metric(
                        [bucket_name, bucket_owner, category, self.store],
                        data_dict["bytes_received"],
                    )

    def _get_bucket_usage(self, bucket):
        logging.debug((json.dumps(bucket, indent=4, sort_keys=True)))

        if type(bucket) is dict:
            bucket_name = bucket["bucket"]
            bucket_owner = bucket["owner"]
            bucket_shards = bucket["num_shards"]
            bucket_usage_bytes = 0
            bucket_utilized_bytes = 0
            bucket_usage_objects = 0

            if bucket["usage"] and "rgw.main" in bucket["usage"]:
                if "size_actual" in bucket["usage"]["rgw.main"]:
                    bucket_usage_bytes = bucket["usage"]["rgw.main"]["size_actual"]
                elif "size_kb_actual" in bucket["usage"]["rgw.main"]:
                    usage_kb = bucket["usage"]["rgw.main"]["size_kb_actual"]
                    bucket_usage_bytes = usage_kb * 1024

                if "size_utilized" in bucket["usage"]["rgw.main"]:
                    bucket_utilized_bytes = bucket["usage"]["rgw.main"]["size_utilized"]

                if "num_objects" in bucket["usage"]["rgw.main"]:
                    bucket_usage_objects = bucket["usage"]["rgw.main"]["num_objects"]

            if "zonegroup" in bucket:
                bucket_zonegroup = bucket["zonegroup"]
            else:
                bucket_zonegroup = "0"

            taglist = []
            if "tagset" in bucket:
                bucket_tagset = bucket["tagset"]
                if self.tag_list:
                    for k in self.tag_list.split(","):
                        if k in bucket_tagset:
                            taglist.append(bucket_tagset[k])

            b_metrics = [bucket_name, bucket_owner, bucket_zonegroup, self.store]
            b_metrics = b_metrics + taglist

            self._prometheus_metrics["bucket_usage_bytes"].add_metric(
                b_metrics,
                bucket_usage_bytes,
            )
            self._prometheus_metrics["bucket_utilized_bytes"].add_metric(
                b_metrics,
                bucket_utilized_bytes,
            )
            self._prometheus_metrics["bucket_usage_objects"].add_metric(
                b_metrics,
                bucket_usage_objects,
            )

            if "bucket_quota" in bucket:
                self._prometheus_metrics["bucket_quota_enabled"].add_metric(
                    b_metrics,
                    bucket["bucket_quota"]["enabled"],
                )
                self._prometheus_metrics["bucket_quota_max_size"].add_metric(
                    b_metrics,
                    bucket["bucket_quota"]["max_size"],
                )
                self._prometheus_metrics["bucket_quota_max_size_bytes"].add_metric(
                    b_metrics,
                    bucket["bucket_quota"]["max_size_kb"] * 1024,
                )
                self._prometheus_metrics["bucket_quota_max_objects"].add_metric(
                    b_metrics,
                    bucket["bucket_quota"]["max_objects"],
                )

            self._prometheus_metrics["bucket_shards"].add_metric(
                b_metrics,
                bucket_shards,
            )

    def _get_rgw_users(self):
        rgw_users = self._request_data(query="user", args="list")

        if rgw_users and "keys" in rgw_users:
            return rgw_users["keys"]
        else:
            rgw_metadata_users = self._request_data(query="metadata/user", args="")
            return rgw_metadata_users

    def _get_user_info(self, user):
        user_info = self._request_data(
            query="user", args="uid={0}&stats=True".format(user)
        )
        logging.debug((json.dumps(user_info, indent=4, sort_keys=True)))

        if "display_name" in user_info:
            user_display_name = user_info["display_name"]
        else:
            user_display_name = ""
        if "email" in user_info:
            user_email = user_info["email"]
        else:
            user_email = ""
        if "default_storage_class" in user_info:
            user_storage_class = user_info["default_storage_class"]
        else:
            user_storage_class = ""

        self._prometheus_metrics["user_metadata"].add_metric(
            [user, user_display_name, user_email, user_storage_class, self.store], 1
        )

        if "stats" in user_info:
            self._prometheus_metrics["user_total_bytes"].add_metric(
                [user, self.store], user_info["stats"]["size_actual"]
            )
            self._prometheus_metrics["user_total_objects"].add_metric(
                [user, self.store], user_info["stats"]["num_objects"]
            )

        if "user_quota" in user_info:
            quota = user_info["user_quota"]
            self._prometheus_metrics["user_quota_enabled"].add_metric(
                [user, self.store], quota["enabled"]
            )
            self._prometheus_metrics["user_quota_max_size"].add_metric(
                [user, self.store], quota["max_size"]
            )
            self._prometheus_metrics["user_quota_max_size_bytes"].add_metric(
                [user, self.store], quota["max_size_kb"] * 1024
            )
            self._prometheus_metrics["user_quota_max_objects"].add_metric(
                [user, self.store], quota["max_objects"]
            )

        if "bucket_quota" in user_info:
            quota = user_info["bucket_quota"]
            self._prometheus_metrics["user_bucket_quota_enabled"].add_metric(
                [user, self.store], quota["enabled"]
            )
            self._prometheus_metrics["user_bucket_quota_max_size"].add_metric(
                [user, self.store], quota["max_size"]
            )
            self._prometheus_metrics["user_bucket_quota_max_size_bytes"].add_metric(
                [user, self.store], quota["max_size_kb"] * 1024
            )
            self._prometheus_metrics["user_bucket_quota_max_objects"].add_metric(
                [user, self.store], quota["max_objects"]
            )

class MetricsHandler(BaseHTTPRequestHandler):
    def __init__(self, metrics_updater, ssl_context=None, *args, **kwargs):
        self.metrics_updater = metrics_updater
        self.ssl_context = ssl_context
        super().__init__(*args, **kwargs)
        
    def do_GET(self):
        if self.path == '/metrics':
            start_time = time.time()
            
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
        "-e", "--admin-entry",
        help="Admin entry point",
        default=os.environ.get("ADMIN_ENTRY", "admin"),
    )
    parser.add_argument(
        "-a", "--access-key",
        help="S3 access key",
        default=os.environ.get("ACCESS_KEY", ""),
    )
    parser.add_argument(
        "-s", "--secret-key",
        help="S3 secret key",
        default=os.environ.get("SECRET_KEY", ""),
    )
    parser.add_argument(
        "-k", "--insecure",
        help="Allow insecure connections",
        action="store_true",
        default=os.environ.get("INSECURE", "").lower() in ("true", "1", "yes"),
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        help="Port to listen",
        default=int(os.environ.get("VIRTUAL_PORT", "9242")),
    )
    parser.add_argument(
        "-S", "--store",
        help="Store name",
        default=os.environ.get("STORE", "default"),
    )
    parser.add_argument(
        "-t", "--timeout",
        type=int,
        help="Request timeout",
        default=int(os.environ.get("TIMEOUT", "60")),
    )
    parser.add_argument(
        "-l", "--log-level",
        help="Logging level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
    )
    parser.add_argument(
        "-T", "--tag-list",
        help="Comma-separated list of tags",
        default=os.environ.get("TAG_LIST", ""),
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
    return parser.parse_args()

def main():
    try:
        args = parse_args()
        logging.basicConfig(
            level=args.log_level.upper(),
            format='%(asctime)s %(levelname)s: %(message)s'
        )
        
        if bool(args.tls_cert) != bool(args.tls_key):
            logging.error("Both --tls-cert and --tls-key must be provided for HTTPS")
            exit(1)
            
        if args.tls_cert and not (os.path.exists(args.tls_cert) and os.path.exists(args.tls_key)):
            logging.error("TLS certificate or key file not found")
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
