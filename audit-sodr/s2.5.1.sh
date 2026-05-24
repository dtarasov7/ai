#!/usr/bin/env bash
# Пункт 2.5.1: HPA.
# Что запрашивается: все HorizontalPodAutoscaler и их конфигурация.
# Как собирается: выгружается HPA по всем namespaces в wide и YAML.
# Как анализируется: min/max replicas, target metrics и текущие значения проверяются по таблице/YAML.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.5.1" "Horizontal Pod Autoscaler"
audit_run "HPA wide" "hpa-wide.txt" kubectl get hpa --all-namespaces -o wide
audit_run "HPA YAML" "hpa.yaml" kubectl get hpa --all-namespaces -o yaml
audit_done
