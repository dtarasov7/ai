#!/usr/bin/env bash
# Пункт 2.2.4: список кастомных ресурсов CRD.
# Что запрашивается: все CustomResourceDefinition в кластере.
# Как собирается: выгружается список CRD и полный YAML.
# Как анализируется: по таблице оцениваются группы/API versions, YAML нужен для схем, conversion webhook и served/storage versions.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.2.4" "CRD"
audit_run "CRD список" "crd-wide.txt" kubectl get crd -o wide
audit_run "CRD YAML" "crd.yaml" kubectl get crd -o yaml
audit_done
