#!/usr/bin/env bash
# Пункт 7.3.2: активные Gatekeeper Constraints.
# Что запрашивается: какие Constraints активны.
# Как собирается: сначала ищутся API resources группы constraints.gatekeeper.sh, затем каждый тип выгружается в YAML.
# Как анализируется: активность и scope проверяются по spec.match, enforcementAction и статусам каждого constraint.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "7.3.2" "Gatekeeper Constraints"
audit_shell "Список API resources constraints.gatekeeper.sh" "constraint-resources.txt" <<'AUDIT_SH'
set -Eeuo pipefail
kubectl api-resources --api-group=constraints.gatekeeper.sh -o name || true
AUDIT_SH
audit_shell "YAML всех Gatekeeper Constraints по обнаруженным типам" "constraints.yaml" <<'AUDIT_SH'
set -Eeuo pipefail
resources="$(kubectl api-resources --api-group=constraints.gatekeeper.sh -o name 2>/dev/null || true)"
if [[ -z "$resources" ]]; then
  printf 'Gatekeeper constraint resources не найдены\n'
  exit 0
fi
for resource in $resources; do
  printf '\n--- # %s\n' "$resource"
  kubectl get "$resource" --all-namespaces -o yaml || true
done
AUDIT_SH
audit_done
