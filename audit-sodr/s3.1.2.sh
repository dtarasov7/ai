#!/usr/bin/env bash
# Пункт 3.1.2: размер, используемое место и хранилище для каждого PVC.
# Что запрашивается: capacity/request, storageClass и фактическое использование места.
# Как собирается: читаются PVC/PV, describe PVC и kubelet stats/summary по узлам для volume usage.
# Как анализируется: размер и storageClass берутся из PVC/PV, used bytes - из kubelet volume stats или внешнего мониторинга при недоступности stats API.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "3.1.2" "PVC: размер, usage, storage"
audit_run "PVC таблица" "pvc-wide.txt" kubectl get pvc --all-namespaces -o wide
audit_run "PVC describe" "pvc-describe.txt" kubectl describe pvc --all-namespaces
audit_run "PV таблица для сопоставления backing storage" "pv-wide.txt" kubectl get pv -o wide
audit_shell "Volume stats по PVC через kubelet stats/summary и jq, если jq установлен" "pvc-usage.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'node\tnamespace\tpvc\tused_bytes\tcapacity_bytes\tavailable_bytes\n'
if command -v jq >/dev/null 2>&1; then
  for node in $(kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'); do
    kubectl get --raw "/api/v1/nodes/${node}/proxy/stats/summary" | jq -r --arg node "$node" '.pods[]? | .volume[]? | select(.pvcRef != null) | [$node, .pvcRef.namespace, .pvcRef.name, (.usedBytes // ""), (.capacityBytes // ""), (.availableBytes // "")] | @tsv' || true
  done
else
  printf 'jq не установлен: используйте pvc-wide.txt, pv-wide.txt и raw stats из s1.3.2\n' >&2
fi
AUDIT_SH
audit_done
