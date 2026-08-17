# Rails Yabeda dashboard demo

This Docker Compose stack builds and runs a small Rails application together
with PostgreSQL, Redis, Sidekiq, Yabeda, Prometheus, Grafana, and an automatic
traffic generator.

Start the stack:

```shell
docker compose up --build -d
```

Open:

- Grafana dashboards: <http://localhost:3001> (anonymous viewer or `admin` / `admin`)
- Prometheus: <http://localhost:9090>
- Rails Yabeda metrics: <http://localhost:3000/metrics>
- Sidekiq Yabeda metrics: <http://localhost:9394/metrics>
- Rails application: <http://localhost:3000>

The traffic container continuously calls fast, slow, and failing HTTP endpoints
and enqueues fast, slow, and intentionally failing Sidekiq jobs. The three HTTP
endpoints also emit synthetic metrics with the same names and labels as
`yabeda-anycable`, so the AnyCable dashboard can be tested without running an
AnyCable RPC server. Stop and remove the stack with `docker compose down`. Add
`--volumes` to also remove demo data.

Prometheus scrapes Rails and Sidekiq separately and enriches their metrics with
the Kubernetes-like labels `namespace="test"`, `service`, and `pod`. Together
with Prometheus' `job` label they exercise the dependent
`job` → `namespace` → `service` → `pod` filter hierarchy used by all four
provisioned Yabeda dashboards.

The stack also loads
[`prometheus-rules/yabeda-dashboard.rules.yml`](../prometheus-rules/yabeda-dashboard.rules.yml).
Its one-minute recording group stores five-minute Rails and ActiveRecord
histogram bucket rates used by the expensive percentile panels.
