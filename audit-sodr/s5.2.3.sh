#!/usr/bin/env bash
# Пункт 5.2.3: источники метрик Prometheus targets.
# Что запрашивается: список источников метрик/targets Prometheus.
# Как собирается: ищутся Prometheus workload/configmap, выгружаются Prometheus Operator CR (ServiceMonitor/PodMonitor/Probe/ScrapeConfig) при наличии.
# Как анализируется: targets формируются из scrape_configs или CR мониторинга; live target status может потребовать доступа к HTTP API Prometheus.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "5.2.3" "Prometheus targets"
audit_shell "Поиск Prometheus pods/services/configmaps" "prometheus-inventory.txt" <<'AUDIT_SH'
set -Eeuo pipefail
kubectl get pods,svc,configmap --all-namespaces -o wide | grep -Ei 'prometheus|victoria|vmagent|grafana-agent|metrics' || true
AUDIT_SH
audit_run "Prometheus Operator CR: Prometheus" "prometheus-cr.yaml" kubectl get prometheus --all-namespaces -o yaml
audit_run "ServiceMonitor YAML" "servicemonitors.yaml" kubectl get servicemonitor --all-namespaces -o yaml
audit_run "PodMonitor YAML" "podmonitors.yaml" kubectl get podmonitor --all-namespaces -o yaml
audit_run "Probe YAML" "probes.yaml" kubectl get probe --all-namespaces -o yaml
audit_run "ScrapeConfig YAML" "scrapeconfigs.yaml" kubectl get scrapeconfig --all-namespaces -o yaml
audit_shell "ConfigMap с prometheus в имени" "prometheus-configmaps.yaml" <<'AUDIT_SH'
set -Eeuo pipefail
for item in $(kubectl get configmap --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}' | grep -Ei 'prometheus|vmagent|scrape' || true); do
  ns="${item%%/*}"
  name="${item#*/}"
  printf '\n--- # %s/%s\n' "$ns" "$name"
  kubectl -n "$ns" get configmap "$name" -o yaml || true
done
AUDIT_SH
audit_done
