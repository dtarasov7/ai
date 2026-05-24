#!/usr/bin/env bash
# Пункт 1.4.1: ResourceQuotas по всем namespaces.
# Что запрашивается: все ResourceQuota и их конфигурация.
# Как собирается: выгружается список ResourceQuota по всем namespaces в wide и YAML.
# Как анализируется: hard/used значения сравниваются по таблице, лимиты и selectors проверяются по YAML.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.4.1" "ResourceQuotas"
audit_run "ResourceQuota в wide формате" "resourcequotas-wide.txt" kubectl get resourcequota --all-namespaces -o wide
audit_run "ResourceQuota в YAML" "resourcequotas.yaml" kubectl get resourcequota --all-namespaces -o yaml
audit_done
