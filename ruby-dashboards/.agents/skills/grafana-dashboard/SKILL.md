---
name: grafana-dashboard
description: Use when creating or editing Grafana dashboard JSON for Prometheus, especially Grafana 12 dashboards with datasource variables, multi-select label filters, regex filters, PromQL panels, table drill-down links, percentage panels, time series legends, and validation.
---

# Grafana Dashboard Rules

Use this skill when building or changing Grafana dashboard JSON directly.
Assume Grafana 12 and Prometheus 2.x unless the repository says otherwise.

## Workflow

1. Inspect existing dashboards before editing.
2. Reuse the repository's datasource variable, variable names, layout style, units, thresholds, and panel patterns.
3. Prefer structured JSON edits over ad hoc string replacement.
4. Keep dashboard changes scoped to the requested behavior.
5. Validate every changed dashboard by loading it as JSON.
6. When Prometheus is available, test changed PromQL expressions against the target Prometheus API.

## Import Compatibility

- Remove Prometheus datasource entries from `__inputs` so dashboard imports do not require manual datasource selection. Remove entries with `pluginId: "prometheus"`, `pluginName: "Prometheus"`, and `name: "DS_PROMETHEUS"`.
- Set dashboard `timezone` to `"browser"`.
- Recursively rewrite Prometheus `datasource` objects throughout the dashboard JSON, including panels and targets, to:
  ```json
  {
    "type": "prometheus",
    "uid": "$datasource"
  }
  ```

## Variables

- Add or update a datasource variable named `datasource` with label `Datasource`.
- Configure the `datasource` variable with `type: "datasource"`, `query: "prometheus"`, and `current.text: "prometheus"`.
- Move the `datasource` variable to the first position in `templating.list`.
- Add a custom `interval` variable at the end of `templating.list` when it does not already exist. Use `type: "custom"`, `name: "interval"`, default values `1m, 2m, 5m, 15m, 1h, 6h, 1d`, and bind its `datasource` to `"$datasource"`.
- Normalize `templating.list[*].datasource` to `{"type": "prometheus", "uid": "$datasource"}` when the variable references Prometheus.
- Populate label variables from a metric that is guaranteed to exist for the dashboard domain.
  Example: `label_values(cgroup_memory_current_bytes, job)`.
- For dependent variables, include upstream label filters.
  Example: `label_values(cgroup_memory_current_bytes{job=~"$job"}, instance)`.
- For dashboards spanning many servers, always create this variable hierarchy immediately after the datasource variable:
  - `job`: `label_values(<base_metric>, job)`
  - `env`: `label_values(<base_metric>{job=~"$job"}, env)`
  - `group`: `label_values(<base_metric>{job=~"$job",env=~"$env"}, group)`
  - `instance`: `label_values(<base_metric>{job=~"$job",env=~"$env",group=~"$group"}, instance)`
- Make `job`, `env`, `group`, and `instance` multi-select variables with `includeAll: true`.
- Set `allValue: ".*"` for `job`, `env`, and `group` when they are used in regex matchers.
- For `instance`, do not set `allValue`. Leave Custom all value empty so `All` expands to the instances returned by the filtered `instance` query, for example all servers for the selected `job`, `env`, and `group`.
- Do not replace the `instance` All behavior with `.*`; that would bypass the hierarchy and match instances outside the selected `job`, `env`, and `group`.
- In PromQL label matchers, prefer double-quoted Grafana variables:
  `job=~"$job"`, `instance=~"$instance"`, `cgroup=~"$cgroup"`.
- If a PromQL selector has `instance=~"$instance"` or another instance variable selected by the hierarchy, do not also add `job`, `env`, or `group` matchers to that selector.
- Avoid backticks in PromQL and avoid `${var:regex}` unless it has been verified in the target Grafana/Prometheus pair. It can produce escaped regex that Prometheus rejects.
- Use a separate textbox variable for free-form regex filters, such as `cgroup_regex`, and combine it with list variables when both are present.
- Do not make drill-down links mutate broad table filters when the table must keep showing all rows. Use hidden detail variables such as `detail_instance` and `detail_cgroup` for panels below the table.

## PromQL

- Put binary filters outside range-vector functions.
  Good: `rate(a{label=~"$x"}[$__rate_interval]) and rate(a{label=~"$y"}[$__rate_interval])`.
  Bad: `rate(a{label=~"$x"}[$__rate_interval] and a{label=~"$y"}[$__rate_interval])`.
- Use `rate()` for counters shown as rates and `increase()` for event counts over a window.
- Use `sum by (...)`, `max by (...)`, or `topk($topk, ...)` deliberately; preserve labels needed by legends and joins.
- For fleet dashboards, apply both broad regex filters and explicit list filters:
  `metric{cgroup=~"$cgroup_regex"} and metric{cgroup=~"$cgroup"}`.
- Filter synthetic infinity values before plotting finite limits:
  `cgroup_memory_effective_max_bytes{...} < 1e30`.
- When a dashboard needs memory usage versus limit, prefer finite `memory.max`; fall back to finite `memory.high` only when max is unlimited.
- CPU throttled periods percent is not CPU utilization. It is:
  `100 * rate(cgroup_cpu_throttled_periods_total[...]) / rate(cgroup_cpu_periods_total[...])`.
- PSI `avg10` values are percentages; keep panels bounded from 0 to 100.

## Panels

- Use the dashboard's first viewport for high-signal stat panels: selected objects, worst memory percent, CPU usage, OOM/errors, throttling, scrape health.
- Keep table dashboards focused on inventory and drill-down. Keep fleet dashboards focused on overview and top-N trends.
- Do not duplicate low-value inventory tables inside overview dashboards unless the user explicitly asks for that.
- For all percentage panels and percentage table fields:
  - set `unit: "percent"`;
  - set `min: 0`;
  - set `max: 100`;
  - add thresholds only when they reflect operational meaning.
- For all time series panels:
  - set legend `displayMode: "table"`;
  - include `calcs: ["lastNotNull", "max"]`;
  - set `sortBy: "Max"`;
  - set `sortDesc: true`;
  - keep legend placement consistent with the existing dashboard.
- Use units consistently:
  - bytes for memory;
  - seconds for durations;
  - percent for ratios already multiplied by 100;
  - `none` or `short` for CPU cores and counts as appropriate.
- Keep time series legends specific enough to identify both instance and object when a dashboard can show multiple instances.

## Tables And Drill-Down

- Put the primary object name in the first table column when users will click or sort by it.
- Remove accidental duplicate columns such as `cgroup 2` or `instance 2` after joins.
- Use transformations intentionally: join/merge series by labels, organize fields, hide `Time` and raw value fields that are not useful to the reader.
- Preserve table sorting when users need to find worst offenders.
- Use data links on stable fields. If a field name conflicts with a dashboard variable, use indexed row fields such as `${__data.fields[0]}` and `${__data.fields[1]}`.
- For drill-down panels under a table, data links should set hidden detail variables, not the visible variables that control the table itself.

## Layout

- Keep related panels in the same row when they answer the same operational question.
- Avoid large empty rows caused by moving one panel out of a dense stat row.
- When adding panels to an existing dashboard, preserve the existing grid rhythm: usually 24 columns wide, stat panels in a short top row, time series panels in pairs.
- Prefer adding missing high-signal panels to the main overview dashboard over maintaining two dashboards with nearly identical content.

## Validation Checklist

- Load every changed dashboard JSON with a parser.
- Check that dashboard variables still resolve from existing metrics.
- Check that every changed PromQL expression uses double-quoted Grafana variables in label matchers.
- Search for bad patterns:
  - backtick matchers;
  - `rate(... and ...)` or `increase(... and ...)`;
  - `${var:regex}` in PromQL when the target stack has shown escaping problems;
  - duplicate table fields created by joins.
- Confirm all percentage panels have `min: 0` and `max: 100`.
- Confirm all time series panels have table legends with `lastNotNull`, `max`, and descending Max sort.
- Confirm Prometheus datasource objects use `{"type": "prometheus", "uid": "$datasource"}` throughout the dashboard JSON.
- Confirm Prometheus `__inputs` datasource entries were removed, `timezone` is `"browser"`, the `datasource` variable is first, and the `interval` variable is last.
- Update README or changelog when dashboard behavior, available panels, or import expectations change.
