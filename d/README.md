# Grafana dashboards

The directory contains Grafana 12 dashboards using Prometheus as their
datasource. The standard variants are:

- `Ruby On Rails Prometheus Overview.json` — request volume, HTTP errors,
  request latency, SQL time, and busiest controller actions.
- `Ruby On Rails Prometheus Actions.json` — controller/action filtering,
  latency and error trends, and action rankings.
- `Ruby On Rails Prometheus Sidekiq.json` — job throughput, failures, execution
  time, queue backlog and latency, process utilization, and job rankings.

The corresponding Kubernetes variants are:

- `Ruby On Rails Kubernetes Prometheus Overview.json`
- `Ruby On Rails Kubernetes Prometheus Actions.json`
- `Ruby On Rails Kubernetes Prometheus Sidekiq.json`

The dashboards intended for applications instrumented with Yabeda are:

- `Yabeda Rails Kubernetes Overview.json` — Rails requests plus
  ActiveRecord query/pool and Puma thread metrics.
- `Yabeda Rails Kubernetes Actions.json` — controller/action drill-down for
  Yabeda Rails request metrics.
- `Yabeda Sidekiq Kubernetes.json` — worker and queue metrics from
  `yabeda-sidekiq`.
- `Yabeda AnyCable Kubernetes.json` — RPC traffic, failures, and runtime from
  `yabeda-anycable`.

All four Yabeda dashboards use the dependent hierarchy
`datasource` → `job` → `namespace` → `service` → `pod`. Domain-specific
filters follow it: controller/action, queue/worker, or
method/command/status. They are the recommended dashboards for the metric
names shown by the Yabeda samples in this repository.

They replace the `env` → `group` → `instance` target hierarchy with
`job` → `namespace` → `service` → `pod`. The `job` label distinguishes scrape
jobs or applications, while the remaining labels select Kubernetes targets.
These dashboards require all four labels to be present on the exported metric
series; retain or add `namespace`, `service`, and `pod` in the Prometheus
discovery relabeling configuration.

The `pod` target label identifies the pod scraped by Prometheus. If one central
`prometheus_exporter` aggregates observations from multiple Rails or Sidekiq
pods, it identifies only that exporter pod and cannot separate the source pods.
Use an exporter target per application pod or add a consistent source-pod label
at instrumentation time when per-pod breakdown is required.

`cluster`, `workload`, and `container` are intentionally not required
because their presence and naming vary between Kubernetes monitoring setups.
For a multi-cluster datasource, add a `cluster` variable before `namespace` if
the Prometheus installation consistently provides that label.

The Rails dashboards use these `prometheus_exporter` metric families:

- `ruby_http_requests_total`
- `ruby_http_request_duration_seconds`
- `ruby_http_request_sql_duration_seconds`

The Sidekiq dashboard additionally uses `ruby_sidekiq_*` metrics produced by
the Sidekiq middleware, process, queue, and stats collectors. Its dead-jobs
panels require the Sidekiq death handler.

Each dashboard has a Prometheus datasource variable and can be imported into
Grafana independently. In the standard variants, `job`, `env`, `group`, and
`instance` form the dependent target hierarchy. A ready-to-run validation environment is available in
[`prometheus-demo`](../prometheus-demo/README.md).
