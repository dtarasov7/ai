#!/usr/bin/env bash
# Пункт 2.3.1: все Ingress ресурсы.
# Что запрашивается: YAML файл со всеми Ingress.
# Как собирается: выгружается таблица Ingress по всем namespaces и полный YAML.
# Как анализируется: hosts, ingressClass, TLS и backend service проверяются по таблице/YAML.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.3.1" "Ingress resources"
audit_run "Ingress таблица" "ingress-wide.txt" kubectl get ingress --all-namespaces -o wide
audit_run "Ingress YAML" "ingress.yaml" kubectl get ingress --all-namespaces -o yaml
audit_done
