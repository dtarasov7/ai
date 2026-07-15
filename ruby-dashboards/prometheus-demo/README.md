# Rails Prometheus dashboard demo

This Docker Compose stack builds and runs a small Rails application together
with PostgreSQL, Redis, Sidekiq, prometheus_exporter, Prometheus, Grafana, and an
automatic traffic generator.

Start the stack:

```shell
docker compose up --build -d
```

Open:

- Grafana dashboards: <http://localhost:3001> (anonymous viewer or `admin` / `admin`)
- Prometheus: <http://localhost:9090>
- prometheus_exporter metrics: <http://localhost:9394/metrics>
- Rails application: <http://localhost:3000>

The traffic container continuously calls fast, slow, and failing HTTP endpoints
and enqueues fast, slow, and intentionally failing Sidekiq jobs. Stop and remove
the stack with `docker compose down`. Add `--volumes` to also remove demo data.

Prometheus enriches every scraped application metric with the target labels
`env="test"` and `group="common"`. The provisioned dashboards use them in the
dependent `job` → `env` → `group` → `instance` filter hierarchy.
