#!/usr/bin/env bash
# Пункт 2.3.2: специфические аннотации Nginx Ingress Controller.
# Что запрашивается: список использованных nginx ingress annotations.
# Как собирается: выгружается YAML Ingress и строится TSV по annotations с префиксами nginx/ingress.
# Как анализируется: проверяются ключи `nginx.ingress.kubernetes.io/*`, `nginx.org/*` и legacy ingress annotations; значения сверяются с политиками контроллера.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.3.2" "Nginx ingress annotations"
audit_run "Ingress YAML для первичного анализа annotations" "ingress.yaml" kubectl get ingress --all-namespaces -o yaml
audit_shell "TSV список nginx annotations через jq, если jq установлен" "nginx-ingress-annotations.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tingress\tannotation\tvalue\n'
if command -v jq >/dev/null 2>&1; then
  kubectl get ingress --all-namespaces -o json | jq -r '.items[] as $ing | (($ing.metadata.annotations // {}) | to_entries[]? | select(.key | test("(^nginx\\.ingress\\.kubernetes\\.io/|^nginx\\.org/|^ingress\\.kubernetes\\.io/)")) | [$ing.metadata.namespace, $ing.metadata.name, .key, .value] | @tsv)'
else
  printf 'jq не установлен: используйте ingress.yaml для ручного анализа annotations\n' >&2
fi
AUDIT_SH
audit_done
