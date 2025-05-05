��� ���������� ����� ������, ����� �������� ��������� ���� ��������� �������:

1. **���������� ��������� ������� � �������� ����������**.
2. **���������� ������� � ����������**.
3. **�� ������ `/metrics` �������� ������������ ������**.

��� ���������������� ��� � ����� �����������:

```python
import asyncio
import os
import json
import aiohttp
from aiohttp import web
from datetime import datetime

# ������������
RADOSGW_URL = os.getenv("RADOSGW_URL", "http://localhost:8080")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
UPDATE_INTERVAL = int(os.getenv("METRICS_UPDATE_INTERVAL", "30"))

# ���������� ���������� ��� �������� ������
cached_metrics = "# Metrics not yet collected.\n"

# ����������� ������� ��� ��������� � ���������� ������
async def fetch_and_update_metrics():
    global cached_metrics
    while True:
        try:
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(ACCESS_KEY, SECRET_KEY)) as session:
                async with session.get(f"{RADOSGW_URL}/admin/metadata/user") as resp:
                    users = await resp.json()

                metrics = []
                timestamp = datetime.utcnow().isoformat()

                for user_id in users:
                    async with session.get(f"{RADOSGW_URL}/admin/user", params={"uid": user_id}) as user_resp:
                        user_data = await user_resp.json()

                    usage = user_data.get("usage", {}).get("rgw.main", {})
                    bytes_sent = usage.get("bytes_sent", 0)
                    bytes_received = usage.get("bytes_received", 0)
                    ops = usage.get("ops", 0)

                    metrics.append(f'# HELP radosgw_user_bytes_sent Bytes sent for user {user_id}')
                    metrics.append(f'# TYPE radosgw_user_bytes_sent counter')
                    metrics.append(f'radosgw_user_bytes_sent{{user="{user_id}"}} {bytes_sent}')

                    metrics.append(f'# HELP radosgw_user_bytes_received Bytes received for user {user_id}')
                    metrics.append(f'# TYPE radosgw_user_bytes_received counter')
                    metrics.append(f'radosgw_user_bytes_received{{user="{user_id}"}} {bytes_received}')

                    metrics.append(f'# HELP radosgw_user_ops Total operations for user {user_id}')
                    metrics.append(f'# TYPE radosgw_user_ops counter')
                    metrics.append(f'radosgw_user_ops{{user="{user_id}"}} {ops}')

                cached_metrics = "\n".join(metrics)
                print(f"[{timestamp}] Metrics updated successfully.")
        except Exception as e:
            cached_metrics = f"# Error collecting metrics: {str(e)}"
            print(f"[{datetime.utcnow().isoformat()}] Error updating metrics: {str(e)}")

        await asyncio.sleep(UPDATE_INTERVAL)

# HTTP ����������
async def metrics_handler(request):
    return web.Response(text=cached_metrics, content_type="text/plain")

# ������ �������
async def init_app():
    app = web.Application()
    app.add_routes([web.get('/metrics', metrics_handler)])
    return app

# �������� �������
async def main():
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()

    # ��������� ������ ���������� ������
    asyncio.create_task(fetch_and_update_metrics())

    # ��������� ������
    print("Server started at http://0.0.0.0:8000")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
```

### ��� ������������:

* ������� ���������� ��������� `METRICS_UPDATE_INTERVAL` � �������� ���������� ������ � ��������.
* ��� ������� � `/metrics` �� �������� ��������� ��������� ������� ��� �������� �� ������� � RADOS.

������, ����� � �������� ���� ��� � Dockerfile ��� ����� � systemd-��������?
