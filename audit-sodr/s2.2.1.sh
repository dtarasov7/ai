#!/usr/bin/env bash
# Пункт 2.2.1: список всех Helm релизов.
# Что запрашивается: все Helm releases во всех namespaces.
# Как собирается: выполняется `helm list --all-namespaces` в table и YAML форматах.
# Как анализируется: таблица показывает release/chart/app version/status, YAML удобен для последующей обработки.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.2.1" "Helm releases"
audit_run "Версия Helm client" "helm-version.txt" helm version
audit_run "Helm releases таблица" "helm-list.txt" helm list --all-namespaces
audit_run "Helm releases YAML" "helm-list.yaml" helm list --all-namespaces -o yaml
audit_done
