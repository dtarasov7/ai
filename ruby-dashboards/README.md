# Ruby Prometheus dashboards

This project contains Grafana dashboards for metrics exported from Ruby on Rails
and Sidekiq applications to Prometheus.

## Contents

- [`dashboards`](dashboards/README.md) contains the importable Grafana dashboard JSON files.
- [`prometheus-rules`](prometheus-rules/README.md) contains recording rules and
  installation instructions for vanilla Kubernetes and Deckhouse.
- [`prometheus-demo`](prometheus-demo/README.md) contains a complete Docker Compose
  test environment.
- `influxdb-rails` is retained as the source example used during dashboard analysis.

## Quick start

```shell
cd prometheus-demo
docker compose up --build -d
```

Open Grafana at <http://localhost:3001>. The dashboards are provisioned
automatically and demo traffic continuously populates their Rails,
ActiveRecord, Puma, Sidekiq, and simulated AnyCable panels.

## Collecting real metric series

To capture current Yabeda Rails, ActiveRecord, Puma, and Sidekiq series from
Prometheus together with target labels added during scraping, run:

```shell
./collect-metric-series.sh http://prometheus:9090
```

The script prints up to five real samples for each metric name. To print every
matching series, set `MAX_SERIES_PER_METRIC=0`. The query can be narrowed to a
specific Kubernetes target:

```shell
PROMQL_QUERY='{__name__=~"(rails|activerecord|puma|sidekiq|anycable)_.*",namespace="production",service="backend"}' \
  ./collect-metric-series.sh http://prometheus:9090
```
