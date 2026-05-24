#!/usr/bin/env bash
# Пункт 2.6.1: Node affinity для всех приложений.
# Что запрашивается: настройки nodeAffinity у workload.
# Как собирается: выгружается YAML deployments/statefulsets/daemonsets и TSV с непустым affinity через jq.
# Как анализируется: required/preferred правила nodeAffinity проверяются в spec.template.spec.affinity.nodeAffinity.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.6.1" "Node affinity workload"
audit_run "Workload YAML для анализа nodeAffinity" "workloads.yaml" kubectl get deployments,statefulsets,daemonsets --all-namespaces -o yaml
audit_shell "Список workload с nodeAffinity через jq, если jq установлен" "node-affinity.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tkind\tname\tnodeAffinity_json\n'
if command -v jq >/dev/null 2>&1; then
  kubectl get deployments,statefulsets,daemonsets --all-namespaces -o json | jq -r '.items[] | select(.spec.template.spec.affinity.nodeAffinity != null) | [.metadata.namespace, .kind, .metadata.name, (.spec.template.spec.affinity.nodeAffinity | tostring)] | @tsv'
else
  printf 'jq не установлен: используйте workloads.yaml\n' >&2
fi
AUDIT_SH
audit_done
