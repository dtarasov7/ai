# Ruby Prometheus dashboards

This project contains Grafana dashboards for metrics exported from Ruby on Rails
and Sidekiq applications to Prometheus.

## Contents

- [`dashboards`](dashboards/README.md) contains the importable Grafana dashboard JSON files.
- [`prometheus-demo`](prometheus-demo/README.md) contains a complete Docker Compose
  test environment.
- `influxdb-rails` is retained as the source example used during dashboard analysis.

## Quick start

```shell
cd prometheus-demo
docker compose up --build -d
```

Open Grafana at <http://localhost:3001>. The dashboards are provisioned
automatically and demo traffic continuously populates their Rails, SQL, and
Sidekiq panels.
