#!/usr/bin/env bash
# Пункт 3.1.1: все PVC и PV.
# Что запрашивается: таблица PersistentVolume и PersistentVolumeClaim.
# Как собирается: выгружается wide таблица PV/PVC и полный YAML.
# Как анализируется: capacity, access modes, status, claim binding и storageClass проверяются по таблице/YAML.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "3.1.1" "PV и PVC"
audit_run "PV/PVC wide" "pv-pvc-wide.txt" kubectl get pv,pvc --all-namespaces -o wide
audit_run "PV/PVC YAML" "pv-pvc.yaml" kubectl get pv,pvc --all-namespaces -o yaml
audit_done
