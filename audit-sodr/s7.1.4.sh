#!/usr/bin/env bash
# Пункт 7.1.4: K8s RBAC roles и bindings.
# Что запрашивается: все Role, ClusterRole, RoleBinding и ClusterRoleBinding.
# Как собирается: выгружается RBAC в таблицах и полном YAML по всем namespaces.
# Как анализируется: права проверяются по rules, subjects и roleRef; особое внимание cluster-admin и wildcard permissions.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "7.1.4" "RBAC roles and bindings"
audit_run "RBAC YAML" "rbac.yaml" kubectl get roles,clusterroles,rolebindings,clusterrolebindings --all-namespaces -o yaml
audit_run "Roles таблица" "roles.txt" kubectl get roles --all-namespaces -o wide
audit_run "ClusterRoles таблица" "clusterroles.txt" kubectl get clusterroles -o wide
audit_run "RoleBindings таблица" "rolebindings.txt" kubectl get rolebindings --all-namespaces -o wide
audit_run "ClusterRoleBindings таблица" "clusterrolebindings.txt" kubectl get clusterrolebindings -o wide
audit_done
