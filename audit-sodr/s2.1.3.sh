#!/usr/bin/env bash
# Пункт 2.1.3: текущие requests/limits для всех pod.
# Что запрашивается: namespace, pod, container, cpu/memory request и cpu/memory limit.
# Как собирается: выгружается таблица containers через custom-columns и полный JSON pods для точного анализа.
# Как анализируется: значения берутся из spec.containers[].resources; пустые поля означают, что request/limit не задан явно.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.1.3" "Requests/limits pod containers"
audit_run "Сводная таблица requests/limits по pod" "pod-requests-limits.txt" kubectl get pods --all-namespaces -o custom-columns=NAMESPACE:.metadata.namespace,POD:.metadata.name,CONTAINERS:.spec.containers[*].name,CPU_REQUESTS:.spec.containers[*].resources.requests.cpu,CPU_LIMITS:.spec.containers[*].resources.limits.cpu,MEM_REQUESTS:.spec.containers[*].resources.requests.memory,MEM_LIMITS:.spec.containers[*].resources.limits.memory
audit_run "Полный JSON pods для машинного анализа containers" "pods.json" kubectl get pods --all-namespaces -o json
audit_shell "Точная TSV таблица через jq, если jq установлен" "pod-requests-limits.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tpod\tcontainer\tcpu_request\tcpu_limit\tmemory_request\tmemory_limit\n'
if command -v jq >/dev/null 2>&1; then
  kubectl get pods --all-namespaces -o json | jq -r '.items[] as $pod | $pod.spec.containers[] | [$pod.metadata.namespace, $pod.metadata.name, .name, (.resources.requests.cpu // ""), (.resources.limits.cpu // ""), (.resources.requests.memory // ""), (.resources.limits.memory // "")] | @tsv'
else
  printf 'jq не установлен: используйте pod-requests-limits.txt или pods.json\n' >&2
fi
AUDIT_SH
audit_done
