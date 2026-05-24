#!/usr/bin/env bash
# Пункт 2.6.2: Pod anti-affinity для всех приложений.
# Что запрашивается: настройки podAntiAffinity у workload.
# Как собирается: выгружается YAML deployments/statefulsets/daemonsets и TSV с непустым podAntiAffinity через jq.
# Как анализируется: required/preferred правила podAntiAffinity проверяются в spec.template.spec.affinity.podAntiAffinity.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.6.2" "Pod anti-affinity workload"
audit_run "Workload YAML для анализа podAntiAffinity" "workloads.yaml" kubectl get deployments,statefulsets,daemonsets --all-namespaces -o yaml
audit_shell "Список workload с podAntiAffinity через jq, если jq установлен" "pod-anti-affinity.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tkind\tname\tpodAntiAffinity_json\n'
if command -v jq >/dev/null 2>&1; then
  kubectl get deployments,statefulsets,daemonsets --all-namespaces -o json | jq -r '.items[] | select(.spec.template.spec.affinity.podAntiAffinity != null) | [.metadata.namespace, .kind, .metadata.name, (.spec.template.spec.affinity.podAntiAffinity | tostring)] | @tsv'
else
  printf 'jq не установлен: используйте workloads.yaml\n' >&2
fi
AUDIT_SH
audit_done
