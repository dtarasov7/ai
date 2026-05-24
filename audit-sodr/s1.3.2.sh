#!/usr/bin/env bash
# Пункт 1.3.2: текущее использование ресурсов на каждом узле.
# Что запрашивается: CPU, Memory и Storage usage по каждому узлу.
# Как собирается: используется metrics API через `kubectl top nodes`, describe nodes и kubelet stats/summary по каждому узлу.
# Как анализируется: CPU/Memory берутся из metrics-server, storage - из kubelet stats/summary или внешнего мониторинга, если API stats недоступен.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.3.2" "Текущее использование ресурсов узлов"
audit_run "CPU/Memory usage по узлам через metrics-server" "top-nodes.txt" kubectl top nodes
audit_run "Describe nodes с allocatable и pressure conditions" "nodes-describe.txt" kubectl describe nodes
audit_shell "kubelet stats/summary по каждому узлу для filesystem/storage" "node-stats-summary.txt" <<'AUDIT_SH'
set -Eeuo pipefail
for node in $(kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'); do
  printf '\n===== %s =====\n' "$node"
  kubectl get --raw "/api/v1/nodes/${node}/proxy/stats/summary" || true
done
AUDIT_SH
audit_done
