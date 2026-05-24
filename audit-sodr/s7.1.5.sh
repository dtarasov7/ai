#!/usr/bin/env bash
# Пункт 7.1.5: ServiceAccounts и их назначения.
# Что запрашивается: список ServiceAccount с описанием назначения.
# Как собирается: выгружается список ServiceAccount, YAML metadata и bindings, где они используются.
# Как анализируется: назначение выводится по namespace, связанным RoleBinding/ClusterRoleBinding и workload references; финальное описание заполняется в TSV.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "7.1.5" "ServiceAccounts и назначение"
audit_run "ServiceAccounts список" "serviceaccounts.txt" kubectl get serviceaccounts --all-namespaces -o wide
audit_run "ServiceAccounts YAML" "serviceaccounts.yaml" kubectl get serviceaccounts --all-namespaces -o yaml
audit_run "RBAC bindings для анализа использования ServiceAccount" "bindings.yaml" kubectl get rolebindings,clusterrolebindings --all-namespaces -o yaml
audit_shell "Шаблон назначения ServiceAccount" "serviceaccounts-purpose-template.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tserviceaccount\tназначение\n'
kubectl get serviceaccounts --all-namespaces --no-headers 2>/dev/null | awk '{print $1 "\t" $2 "\t"}'
AUDIT_SH
audit_done
