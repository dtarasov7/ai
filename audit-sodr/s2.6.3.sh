#!/usr/bin/env bash
# Пункт 2.6.3: nodeSelector для всех приложений.
# Что запрашивается: nodeSelector у workload.
# Как собирается: выгружается YAML deployments/statefulsets/daemonsets и TSV с непустым nodeSelector через jq.
# Как анализируется: nodeSelector проверяется в spec.template.spec.nodeSelector и сопоставляется с labels узлов.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.6.3" "nodeSelector workload"
audit_run "Workload YAML для анализа nodeSelector" "workloads.yaml" kubectl get deployments,statefulsets,daemonsets --all-namespaces -o yaml
audit_run "Labels узлов для сопоставления nodeSelector" "nodes-labels.txt" kubectl get nodes --show-labels
audit_shell "Список workload с nodeSelector через jq, если jq установлен" "node-selector.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tkind\tname\tnodeSelector_json\n'
if command -v jq >/dev/null 2>&1; then
  kubectl get deployments,statefulsets,daemonsets --all-namespaces -o json | jq -r '.items[] | select((.spec.template.spec.nodeSelector // {}) != {}) | [.metadata.namespace, .kind, .metadata.name, (.spec.template.spec.nodeSelector | tostring)] | @tsv'
else
  printf 'jq не установлен: используйте workloads.yaml\n' >&2
fi
AUDIT_SH
audit_done
