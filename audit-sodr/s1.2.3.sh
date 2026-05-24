#!/usr/bin/env bash
# Пункт 1.2.3: список namespaces и их назначение.
# Что запрашивается: все namespaces и описание назначения каждого namespace.
# Как собирается: выгружается таблица namespaces, labels/annotations и YAML.
# Как анализируется: системность можно оценить по labels/annotations и имени, но бизнес-назначение требует ручного подтверждения в подготовленном TSV.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.2.3" "Namespaces и назначение"
audit_run "Namespaces в wide формате" "namespaces-wide.txt" kubectl get namespaces -o wide
audit_run "Namespaces с labels" "namespaces-labels.txt" kubectl get namespaces --show-labels
audit_run "YAML namespaces" "namespaces.yaml" kubectl get namespaces -o yaml
audit_shell "Шаблон таблицы назначения namespaces" "namespaces-purpose-template.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tstatus\tage\tназначение\n'
kubectl get namespaces --no-headers 2>/dev/null | awk '{print $1 "\t" $2 "\t" $3 "\t"}'
AUDIT_SH
audit_done
