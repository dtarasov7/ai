#!/usr/bin/env bash
# Пункт 1.2.1: Deckhouse - полная конфигурация и enabled modules.
# Что запрашивается: параметры установки Deckhouse, включенные модули и конфигурация Deckhouse CR.
# Как собирается: выгружаются Module, ModuleConfig, NodeGroup и ConfigMap из d8-system без чтения Secret data.
# Как анализируется: enabled/disabled состояние берется из статусов Module и ModuleConfig; YAML используется для сверки настроек установки и модулей.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.2.1" "Deckhouse: полная конфигурация и enabled modules"
audit_run "Список Module с состояниями" "modules-wide.txt" kubectl get modules.deckhouse.io -o wide
audit_run "YAML Module" "modules.yaml" kubectl get modules.deckhouse.io -o yaml
audit_run "YAML ModuleConfig" "moduleconfigs.yaml" kubectl get moduleconfigs.deckhouse.io -o yaml
audit_run "YAML NodeGroup Deckhouse" "nodegroups.yaml" kubectl get nodegroups.deckhouse.io -o yaml
audit_run "ConfigMap namespace d8-system" "d8-system-configmaps.yaml" kubectl -n d8-system get configmap -o yaml
audit_shell "Обзор Deckhouse CRD/API resources" "deckhouse-resources.txt" <<'AUDIT_SH'
set -Eeuo pipefail
kubectl api-resources -o wide | grep -Ei 'deckhouse|nodegroup|module' || true
AUDIT_SH
audit_done
