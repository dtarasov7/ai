#!/usr/bin/env bash
# Пункт 3.1.3: StorageClasses в кластере.
# Что запрашивается: список используемых StorageClass.
# Как собирается: выгружается список StorageClass и полный YAML.
# Как анализируется: provisioner, reclaimPolicy, volumeBindingMode, allowVolumeExpansion и параметры backend проверяются по YAML.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "3.1.3" "StorageClasses"
audit_run "StorageClass список" "storageclasses.txt" kubectl get storageclass -o wide
audit_run "StorageClass YAML" "storageclasses.yaml" kubectl get storageclass -o yaml
audit_done
