#!/usr/bin/env bash
# Пункт 1.4.2: LimitRanges по всем namespaces.
# Что запрашивается: все LimitRange и их конфигурация.
# Как собирается: выгружается список LimitRange по всем namespaces в wide и YAML.
# Как анализируется: default/defaultRequest/min/max проверяются по YAML и describe.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.4.2" "LimitRanges"
audit_run "LimitRange в wide формате" "limitranges-wide.txt" kubectl get limitrange --all-namespaces -o wide
audit_run "LimitRange в YAML" "limitranges.yaml" kubectl get limitrange --all-namespaces -o yaml
audit_run "LimitRange describe" "limitranges-describe.txt" kubectl describe limitrange --all-namespaces
audit_done
