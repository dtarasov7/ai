#!/usr/bin/env bash
# Пункт 7.3.3: нарушения Gatekeeper.
# Что запрашивается: список violations или подтверждение отсутствия.
# Как собирается: выгружаются constraints и анализируется status.violations по каждому constraint resource.
# Как анализируется: непустой status.violations означает нарушение; пустой список или отсутствие resources фиксируется как отсутствие найденных нарушений.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "7.3.3" "Gatekeeper violations"
audit_shell "Gatekeeper violations через jq, если jq установлен" "gatekeeper-violations.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'resource\tnamespace\tconstraint\tviolation_namespace\tviolation_name\tmessage\n'
resources="$(kubectl api-resources --api-group=constraints.gatekeeper.sh -o name 2>/dev/null || true)"
if [[ -z "$resources" ]]; then
  printf 'Gatekeeper constraint resources не найдены\n' >&2
  exit 0
fi
if ! command -v jq >/dev/null 2>&1; then
  printf 'jq не установлен: будет сохранен только сырой список constraints\n' >&2
  for resource in $resources; do kubectl get "$resource" --all-namespaces -o yaml || true; done
  exit 0
fi
for resource in $resources; do
  kubectl get "$resource" --all-namespaces -o json | jq -r --arg resource "$resource" '.items[] as $c | ($c.status.violations // [])[]? | [$resource, ($c.metadata.namespace // ""), $c.metadata.name, (.namespace // ""), (.name // ""), (.message // "")] | @tsv' || true
done
AUDIT_SH
audit_shell "Сырой список constraints для подтверждения статуса" "constraints-status.yaml" <<'AUDIT_SH'
set -Eeuo pipefail
for resource in $(kubectl api-resources --api-group=constraints.gatekeeper.sh -o name 2>/dev/null || true); do
  printf '\n--- # %s\n' "$resource"
  kubectl get "$resource" --all-namespaces -o yaml || true
done
AUDIT_SH
audit_done
