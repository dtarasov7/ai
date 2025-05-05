Чтобы реализовать асинхронность сбора метрик и выполнение запросов `/metrics` с учётом ожидания формирования метрик, предлагается следующая модификация вашего существующего скрипта:

### Основные изменения:
1. **Асинхронный сбор метрик**: Мы будем периодически получать данные от Rados Gateway и обновлять наши метрики вне обработки HTTP-запросов.
   
2. **Синхронизация между сборкой метрик и обработкой запросов**:
   - Обработчик `/metrics` ожидает окончания текущего цикла обновления метрик перед отправкой результатов.
   - Метрики будут храниться в отдельном месте и использоваться сразу же при обработке запросов.

3. **Поддержка HTTPS**: Для поддержки TLS потребуется добавить сертификат и ключ сервера, которые будут использованы при запуске HTTP-сервер.

4. **Метрики собственного коллектора**: Добавляем дополнительные метрики, такие как продолжительность последнего цикла обновления и общее количество циклов обновления.

---

Вот модифицированный вариант кода:

```python
#!/usr/bin/env python3

import asyncio
import ssl
import logging
import json
import os
import sys
import argparse
from datetime import timedelta
from urllib.parse import quote_plus
from typing import Dict, List, Optional
from prometheus_client.core import (
    GaugeMetricFamily,
    CounterMetricFamily,
)
from prometheus_async.aio.web import serve_metrics
from prometheus_client.registry import CollectorRegistry
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from aiocache import cached
from aiohttp import web
from awsauth import S3Auth


# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5.5s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class AsyncRadosGWCollector:
    """
    Asynchronous collector for RADOSGW metrics.
    """

    def __init__(
        self,
        host: str,
        admin_entry: str,
        access_key: str,
        secret_key: str,
        store: str,
        insecure: bool,
        timeout: float,
        update_interval: int,
        tag_list: str,
    ):
        self.host = host
        self.admin_entry = admin_entry
        self.access_key = access_key
        self.secret_key = secret_key
        self.store = store
        self.insecure = insecure
        self.timeout = timeout
        self.update_interval = update_interval
        self.tag_list = tag_list.split(",")
        self.lock = asyncio.Lock()
        self.metrics_updated_event = asyncio.Event()
        self.metrics_ready = False
        self.prom_registry = CollectorRegistry(auto_describe=True)
        self.last_update_time = None
        self.update_count = 0
        self.setup_metrics()
    
    async def setup_metrics(self):
        # Define custom metrics
        self.metrics = {
            "ops": CounterMetricFamily(
                "radosgw_usage_ops_total",
                "Total number of operations",
                labels=[
                    "bucket",
                    "owner",
                    "category",
                    "store",
                ],
            ),
            "successful_ops": CounterMetricFamily(
                "radosgw_usage_successful_ops_total",
                "Total number of successful operations",
                labels=[
                    "bucket",
                    "owner",
                    "category",
                    "store",
                ],
            ),
            "bytes_sent": CounterMetricFamily(
                "radosgw_usage_sent_bytes_total",
                "Total bytes sent by RADOSGW",
                labels=[
                    "bucket",
                    "owner",
                    "category",
                    "store",
                ],
            ),
            "bytes_received": CounterMetricFamily(
                "radosgw_usage_received_bytes_total",
                "Total bytes received by RADOSGW",
                labels=[
                    "bucket",
                    "owner",
                    "category",
                    "store",
                ],
            ),
            "bucket_usage_bytes": GaugeMetricFamily(
                "radosgw_usage_bucket_bytes",
                "Bucket used bytes",
                labels=[
                    "bucket",
                    "owner",
                    "store",
                ],
            ),
            "bucket_utilized_bytes": GaugeMetricFamily(
                "radosgw_usage_bucket_utilized_bytes",
                "Bucket utilized bytes",
                labels=[
                    "bucket",
                    "owner",
                    "store",
                ],
            ),
            "bucket_usage_objects": GaugeMetricFamily(
                "radosgw_usage_bucket_objects",
                "Number of objects in bucket",
                labels=[
                    "bucket",
                    "owner",
                    "store",
                ],
            ),
            "bucket_quota_enabled": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_enabled",
                "Is Quota Enabled?",
                labels=[
                    "bucket",
                    "owner",
                    "store",
                ],
            ),
            "bucket_quota_max_size": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_size",
                "Max Size for Bucket",
                labels=[
                    "bucket",
                    "owner",
                    "store",
                ],
            ),
            "bucket_quota_max_size_bytes": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_size_bytes",
                "Max Size in Bytes for Bucket",
                labels=[
                    "bucket",
                    "owner",
                    "store",
                ],
            ),
            "bucket_quota_max_objects": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_size_objects",
                "Max Number of Objects Allowed",
                labels=[
                    "bucket",
                    "owner",
                    "store",
                ],
            ),
            "bucket_shards": GaugeMetricFamily(
                "radosgw_usage_bucket_shards",
                "Number of Shards in Bucket",
                labels=[
                    "bucket",
                    "owner",
                    "store",
                ],
            ),
            "last_update_timestamp": GaugeMetricFamily(
                "radosgw_collector_last_update_timestamp",
                "Timestamp of last metrics update",
                labels=[],
            ),
            "update_cycle_duration_seconds": GaugeMetricFamily(
                "radosgw_collector_update_cycle_duration_seconds",
                "Duration of latest update cycle",
                labels=[],
            ),
            "update_cycles_total": CounterMetricFamily(
                "radosgw_collector_update_cycles_total",
                "Total number of update cycles completed",
                labels=[],
            )
        }
        
        # Register our custom metrics
        for m in self.metrics.values():
            self.prom_registry.register(m)

    @cached(ttl=None)
    async def fetch_and_process_metrics(self):
        logger.info(f"Starting metrics collection...")
        await self.fetch_all_metrics()
        self.metrics_ready = True
        self.metrics_updated_event.set()
        logger.info(f"Metrics updated.")

    async def fetch_all_metrics(self):
        start_time = time.monotonic()
        async with self.lock:
            await self.fetch_usage()
            await self.fetch_buckets()
            await self.fetch_users()
            
        end_time = time.monotonic()
        duration = round(end_time - start_time, 2)
        self.metrics["update_cycle_duration_seconds"].add_metric([], duration)
        self.metrics["update_cycles_total"].inc()
        self.last_update_time = time.time()
        self.metrics["last_update_timestamp"].add_metric([], self.last_update_time)

    async def fetch_usage(self):
        # Fetch usage data
        raw_data = await self.request_data("usage")
        if raw_data:
            entries = raw_data.get('entries', [])
            for entry in entries:
                owner = entry['owner']
                for bucket in entry['buckets']:
                    for cat in bucket['categories']:
                        self.process_category(owner, bucket, cat)

    async def fetch_buckets(self):
        # Fetch bucket information
        raw_data = await self.request_data("bucket", args={"stats": True})
        if raw_data:
            for bucket in raw_data:
                self.process_bucket(bucket)

    async def fetch_users(self):
        # Fetch user information
        raw_data = await self.request_data("user", args={"list": True})
        if raw_data:
            keys = raw_data.get('keys', [])
            for uid in keys:
                user_info = await self.request_data("user", args={"uid": uid, "stats": True})
                if user_info:
                    self.process_user(uid, user_info)

    def process_category(self, owner, bucket, category):
        bucket_name = bucket['bucket'] or 'root'
        cat_name = category['category']
        ops = category['ops']
        success_ops = category['successful_ops']
        bytes_sent = category['bytes_sent']
        bytes_recv = category['bytes_received']

        self.metrics["ops"].add_metric([bucket_name, owner, cat_name, self.store], ops)
        self.metrics["successful_ops"].add_metric([bucket_name, owner, cat_name, self.store], success_ops)
        self.metrics["bytes_sent"].add_metric([bucket_name, owner, cat_name, self.store], bytes_sent)
        self.metrics["bytes_received"].add_metric([bucket_name, owner, cat_name, self.store], bytes_recv)

    def process_bucket(self, bucket):
        bucket_name = bucket['bucket'] or 'root'
        owner = bucket['owner']
        usage_bytes = bucket['usage']['rgw.main'].get('size_actual', 0)
        utilized_bytes = bucket['usage']['rgw.main'].get('size_utilized', 0)
        num_objects = bucket['usage']['rgw.main'].get('num_objects', 0)
        max_size_bytes = bucket['bucket_quota'].get('max_size_kb', 0) * 1024
        max_objects = bucket['bucket_quota'].get('max_objects', 0)
        shard_count = bucket.get('num_shards', 0)

        self.metrics["bucket_usage_bytes"].add_metric([bucket_name, owner, self.store], usage_bytes)
        self.metrics["bucket_utilized_bytes"].add_metric([bucket_name, owner, self.store], utilized_bytes)
        self.metrics["bucket_usage_objects"].add_metric([bucket_name, owner, self.store], num_objects)
        self.metrics["bucket_quota_enabled"].add_metric([bucket_name, owner, self.store], bucket['bucket_quota']['enabled'])
        self.metrics["bucket_quota_max_size_bytes"].add_metric([bucket_name, owner, self.store], max_size_bytes)
        self.metrics["bucket_quota_max_objects"].add_metric([bucket_name, owner, self.store], max_objects)
        self.metrics["bucket_shards"].add_metric([bucket_name, owner, self.store], shard_count)

    def process_user(self, uid, user_info):
        display_name = user_info.get('display_name', '')
        email = user_info.get('email', '')
        storage_class = user_info.get('default_storage_class', '')
        total_bytes = user_info.get('stats', {}).get('size_actual', 0)
        total_objects = user_info.get('stats', {}).get('num_objects', 0)
        user_quota = user_info.get('user_quota', {})
        bucket_quota = user_info.get('bucket_quota', {})

        self.metrics["user_metadata"].add_metric([uid, display_name, email, storage_class, self.store], 1)
        self.metrics["user_total_bytes"].add_metric([uid, self.store], total_bytes)
        self.metrics["user_total_objects"].add_metric([uid, self.store], total_objects)
        self.metrics["user_quota_enabled"].add_metric([uid, self.store], user_quota.get('enabled', False))
        self.metrics["user_quota_max_size_bytes"].add_metric([uid, self.store], user_quota.get('max_size_kb', 0) * 1024)
        self.metrics["user_quota_max_objects"].add_metric([uid, self.store], user_quota.get('max_objects', 0))
        self.metrics["user_bucket_quota_enabled"].add_metric([uid, self.store], bucket_quota.get('enabled', False))
        self.metrics["user_bucket_quota_max_size_bytes"].add_metric([uid, self.store], bucket_quota.get('max_size_kb', 0) * 1024)
        self.metrics["user_bucket_quota_max_objects"].add_metric([uid, self.store], bucket_quota.get('max_objects', 0))

    async def request_data(self, endpoint: str, args: Optional[Dict[str, str]] = None):
        url = f"{self.host}/{self.admin_entry}?format=json"
        if args:
            arg_str = "&".join(f"{key}={quote_plus(str(value))}" for key, value in args.items())
            url += f"&{arg_str}"
 session = S3Auth(self.access_key, self.secret_key, self.host)
        headers = {'Content-Type': 'application/json'}
        resp = await session.get(url, headers=headers, timeout=self.timeout)
        if resp.status != 200:
            raise Exception(f"Error fetching {endpoint}: {resp.status}")
        return await resp.json()

    async def start_updating_metrics(self):
        while True:
            await self.fetch_and_process_metrics()
            await asyncio.sleep(self.update_interval)

async def handle_metrics(request):
    collector = app['collector']
    await collector.metrics_updated_event.wait()
    return await serve_metrics(request, registry=collector.prom_registry)

async def init_app(host, admin_entry, access_key, secret_key, store, insecure, timeout, interval, tag_list):
    app = web.Application()
    collector = AsyncRadosGWCollector(host, admin_entry, access_key, secret_key, store, insecure, timeout, interval, tag_list)
    app['collector'] = collector
    loop = asyncio.get_running_loop()
    task = loop.create_task(collector.start_updating_metrics())
    app.on_cleanup.append(lambda _: task.cancel())
    app.router.add_get('/metrics', handle_metrics)
    return app

def create_ssl_context(cert_path, key_path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.load_cert_chain(cert_path, key_path)
    return context

def run_server(args):
    cert_path = args.ssl_cert_path
    key_path = args.ssl_key_path
    ssl_context = None
    if cert_path and key_path:
        ssl_context = create_ssl_context(cert_path, key_path)
    
    host = args.host
    port = args.port
    app = init_app(
        host=host,
        admin_entry=args.admin_entry,
        access_key=args.access_key,
        secret_key=args.secret_key,
        store=args.store,
        insecure=args.insecure,
        timeout=args.timeout,
        interval=args.interval,
        tag_list=args.tag_list
    )
    web.run_app(app, host='0.0.0.0', port=port, ssl_context=ssl_context)

def parse_args():
    parser = argparse.ArgumentParser(description="Async RadosGW Metrics Exporter")
    parser.add_argument("--host", required=True, help="RADOSGW Host URL")
    parser.add_argument("--admin-entry", default="admin", help="Admin entry point")
    parser.add_argument("--access-key", required=True, help="Access Key")
    parser.add_argument("--secret-key", required=True, help="Secret Key")
    parser.add_argument("--store", default="us-east-1", help="Storage region identifier")
    parser.add_argument("--interval", type=int, default=60, help="Update interval in seconds")
    parser.add_argument("--insecure", action="store_true", help="Skip SSL verification")
    parser.add_argument("--timeout", type=float, default=60, help="Request timeout in seconds")
    parser.add_argument("--port", type=int, default=9242, help="Listening port")
    parser.add_argument("--tag-list", default="", help="Comma-separated list of tags to include as labels")
    parser.add_argument("--ssl-cert-path", help="Path to SSL certificate file")
    parser.add_argument("--ssl-key-path", help="Path to SSL private key file")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run_server(args)
```

### Что изменилось?

#### 1. Асинхронный сбор метрик:
Теперь используется библиотека `asyncio` для периодического обновления метрик. Функция `fetch_and_process_metrics()` собирает и обрабатывает метрики асинхронно каждые N секунд (`--interval`), заданных аргументом командной строки.

#### 2. Синхронизация запросов:
Запросы `/metrics` теперь ожидают завершение последнего цикла обновления метрик. Запрос ждет, пока метрики будут готовы, благодаря использованию события `metrics_updated_event`.

#### 3. Поддержка HTTPS:
При наличии сертификата и ключа сервер запускается с поддержкой HTTPS.

#### 4. Дополнительные метрики:
Мы добавили метрики для отслеживания производительности самого коллектора — длительность последнего цикла обновления и общее число выполненных циклов.

### Настройка запуска:

Запускайте скрипт следующим образом:

```bash
./script.py \
    --host=http://your-rados-gateway-host \
    --access-key=YOUR_ACCESS_KEY \
    --secret-key=YOUR_SECRET_KEY \
    --interval=60 \
    --port=9242 \
    --ssl-cert-path=/path/to/certificate.pem \
    --ssl-key-path=/path/to/key.pem
```

Эти изменения позволят вашему коллектору эффективно собирать метрики асинхронно и поддерживать запросы одновременно, улучшая производительность и надёжность системы мониторинга.