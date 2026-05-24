#!/usr/bin/env bash
# Пункт 1.2.6: список всех NetworkPolicies.
# Что запрашивается: все NetworkPolicy, если они есть.
# Как собирается: выполняется выгрузка NetworkPolicy по всем namespaces в wide и YAML.
# Как анализируется: наличие политик проверяется по списку, детальные ingress/egress правила анализируются по YAML.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.2.6" "NetworkPolicies"
audit_run "NetworkPolicies в wide формате" "networkpolicies-wide.txt" kubectl get networkpolicies --all-namespaces -o wide
audit_run "NetworkPolicies в YAML" "networkpolicies.yaml" kubectl get networkpolicies --all-namespaces -o yaml
audit_done
