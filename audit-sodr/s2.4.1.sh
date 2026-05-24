#!/usr/bin/env bash
# Пункт 2.4.1: все CronJobs.
# Что запрашивается: YAML файл со всеми CronJob.
# Как собирается: выгружается таблица CronJob по всем namespaces и полный YAML.
# Как анализируется: расписание, suspend, concurrencyPolicy, history limits и шаблон Job проверяются по YAML.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.4.1" "CronJobs"
audit_run "CronJobs таблица" "cronjobs-wide.txt" kubectl get cronjobs --all-namespaces -o wide
audit_run "CronJobs YAML" "cronjobs.yaml" kubectl get cronjobs --all-namespaces -o yaml
audit_done
