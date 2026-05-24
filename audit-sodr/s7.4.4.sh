#!/usr/bin/env bash
# Пункт 7.4.4: PodSecurityPolicies, если используются.
# Что запрашивается: deprecated PodSecurityPolicy configuration.
# Как собирается: проверяется наличие API resource podsecuritypolicies и выполняется YAML выгрузка, если API доступен.
# Как анализируется: отсутствие resource на новых версиях Kubernetes ожидаемо; при наличии проверяются privileged, allowedHostPaths, volumes и runAs rules.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "7.4.4" "PodSecurityPolicies"
audit_shell "Проверка наличия PodSecurityPolicy API" "psp-api-resource.txt" <<'AUDIT_SH'
set -Eeuo pipefail
kubectl api-resources -o wide | grep -Ei 'podsecuritypolicies|podsecuritypolicy' || true
AUDIT_SH
audit_run "PodSecurityPolicy YAML, если API доступен" "podsecuritypolicies.yaml" kubectl get podsecuritypolicies.policy -o yaml
audit_done
