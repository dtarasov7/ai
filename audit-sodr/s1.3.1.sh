#!/usr/bin/env bash
# Пункт 1.3.1: полный список узлов с характеристиками.
# Что запрашивается: полный список всех Kubernetes nodes и их характеристики.
# Как собирается: сохраняются `kubectl get nodes -o wide`, capacity/allocatable, полный YAML и describe.
# Как анализируется: роли, версии, IP и ОС берутся из wide/status; CPU/RAM/storage - из capacity/allocatable и describe.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.3.1" "Узлы кластера: список и характеристики"
audit_run "Узлы в wide формате" "nodes-wide.txt" kubectl get nodes -o wide
audit_run "Capacity и allocatable по узлам" "nodes-capacity-allocatable.txt" kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU_CAP:.status.capacity.cpu,CPU_ALLOC:.status.allocatable.cpu,MEM_CAP:.status.capacity.memory,MEM_ALLOC:.status.allocatable.memory,PODS_CAP:.status.capacity.pods,PODS_ALLOC:.status.allocatable.pods,EPHEMERAL_CAP:.status.capacity.ephemeral-storage,EPHEMERAL_ALLOC:.status.allocatable.ephemeral-storage
audit_run "Полный YAML узлов" "nodes.yaml" kubectl get nodes -o yaml
audit_run "Describe всех узлов" "nodes-describe.txt" kubectl describe nodes
audit_done
