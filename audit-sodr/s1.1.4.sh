#!/usr/bin/env bash
# Пункт 1.1.4: Deckhouse - версия, активные модули и конфигурация.
# Что запрашивается: версия Deckhouse, список активных модулей и конфигурационные объекты Deckhouse.
# Как собирается: пробуется локальный `deckhouse-controller version`, затем через `kubectl` собираются Deployment deckhouse, Module, ModuleConfig и близкие CRD.
# Как анализируется: версию можно брать из вывода controller или image tag, активность модулей - из статусов Module/ModuleConfig, YAML остается первичным артефактом аудита.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.1.4" "Deckhouse: версия, активные модули, конфигурация"
audit_run "Локальная версия deckhouse-controller, если утилита установлена" "deckhouse-controller-version.txt" deckhouse-controller version
audit_run "Deployment Deckhouse с image tag для определения версии" "deckhouse-deployment.yaml" kubectl -n d8-system get deployment deckhouse -o yaml
audit_run "Список модулей Deckhouse" "modules-wide.txt" kubectl get modules.deckhouse.io -o wide
audit_run "YAML модулей Deckhouse" "modules.yaml" kubectl get modules.deckhouse.io -o yaml
audit_run "Конфигурация модулей Deckhouse" "moduleconfigs.yaml" kubectl get moduleconfigs.deckhouse.io -o yaml
audit_shell "Поиск Deckhouse API resources в кластере" "deckhouse-api-resources.txt" <<'AUDIT_SH'
set -Eeuo pipefail
kubectl api-resources -o wide | grep -Ei 'deckhouse|nodegroup|module' || true
AUDIT_SH
audit_done
