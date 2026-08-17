#!/usr/bin/env bash

set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'USAGE'
Usage: collect-metric-series.sh [PROMETHEUS_URL]

Query the Prometheus HTTP API and print current Rails, ActiveRecord, Puma,
Sidekiq, and AnyCable series with all labels added during scraping.

Environment variables:
  PROMETHEUS_URL          Default URL when no positional argument is supplied.
                          Default: http://127.0.0.1:9090
  PROMQL_QUERY            Instant query used to select series.
                          Default selects rails_*, activerecord_*, puma_*,
                          sidekiq_*, and anycable_* metrics.
  MAX_SERIES_PER_METRIC   Maximum series printed for each metric name.
                          Set to 0 to print everything. Default: 5
USAGE
  exit 0
fi

prometheus_url="${1:-${PROMETHEUS_URL:-http://127.0.0.1:9090}}"
prometheus_url="${prometheus_url%/}"
default_query='{__name__=~"(rails|activerecord|puma|sidekiq|anycable)_.+"}'
promql_query="${PROMQL_QUERY:-$default_query}"
max_series="${MAX_SERIES_PER_METRIC:-5}"

if [[ ! "$max_series" =~ ^[0-9]+$ ]]; then
  echo "MAX_SERIES_PER_METRIC must be a non-negative integer" >&2
  exit 2
fi

for command in curl jq; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command not found: $command" >&2
    exit 2
  fi
done

curl \
  --fail \
  --get \
  --silent \
  --show-error \
  --connect-timeout 5 \
  --max-time 30 \
  --data-urlencode "query=$promql_query" \
  "$prometheus_url/api/v1/query" |
  jq --raw-output --argjson max_series "$max_series" '
    if .status != "success" then
      error(.error // "Prometheus API request failed")
    elif .data.resultType != "vector" then
      error("Expected an instant vector result")
    elif (.data.result | length) == 0 then
      error("No matching current series found")
    else
      .data.result
      | sort_by(.metric.__name__)
      | group_by(.metric.__name__)
      | map(if $max_series == 0 then . else .[0:$max_series] end)
      | add
      | .[]
      | . as $sample
      | ($sample.metric.__name__ // "unknown_metric") as $metric_name
      | (
          $sample.metric
          | del(.__name__)
          | to_entries
          | sort_by(.key)
          | map("\(.key)=\(.value | @json)")
          | join(",")
        ) as $labels
      | (if $labels == "" then "" else "{" + $labels + "}" end) as $label_set
      | "\($metric_name)\($label_set) \($sample.value[1])"
    end
  '
