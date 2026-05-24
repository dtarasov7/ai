#!/usr/bin/env bash
# Пункт 2.1.1: полный список pods, deployments, statefulsets, daemonsets.
# Что запрашивается: все основные workload и pod во всех namespaces.
# Как собирается: выполняется wide таблица и YAML экспорт pods/deployments/statefulsets/daemonsets.
# Как анализируется: таблица дает быстрый инвентарь, YAML нужен для детального анализа replicas, selectors, images и pod templates.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.1.1" "Pods и workload"
audit_run "Pods/deployments/statefulsets/daemonsets wide" "workloads-wide.txt" kubectl get pods,deployments,statefulsets,daemonsets --all-namespaces -o wide
audit_run "Pods/deployments/statefulsets/daemonsets YAML" "workloads.yaml" kubectl get pods,deployments,statefulsets,daemonsets --all-namespaces -o yaml
audit_run "kubectl get all для дополнительной сверки" "all-wide.txt" kubectl get all --all-namespaces -o wide
audit_done
