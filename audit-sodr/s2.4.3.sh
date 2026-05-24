#!/usr/bin/env bash
# Пункт 2.4.3: история выполнения CronJobs.
# Что запрашивается: статистика успешных и неуспешных выполнений.
# Как собирается: выгружаются Jobs по всем namespaces, их YAML и таблица CronJob с lastSchedule/suspend.
# Как анализируется: success/failure оцениваются по status.succeeded/status.failed у Job и ownerReferences на CronJob.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.4.3" "История выполнения CronJobs"
audit_run "Jobs wide" "jobs-wide.txt" kubectl get jobs --all-namespaces -o wide
audit_run "Jobs YAML" "jobs.yaml" kubectl get jobs --all-namespaces -o yaml
audit_run "CronJobs с last schedule" "cronjobs-status.txt" kubectl get cronjobs --all-namespaces -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,SCHEDULE:.spec.schedule,SUSPEND:.spec.suspend,LAST_SCHEDULE:.status.lastScheduleTime,LAST_SUCCESS:.status.lastSuccessfulTime
audit_shell "Сводка Job status через jq, если jq установлен" "jobs-history.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tjob\towner\tsucceeded\tfailed\tactive\tcompletion_time\n'
if command -v jq >/dev/null 2>&1; then
  kubectl get jobs --all-namespaces -o json | jq -r '.items[] | [.metadata.namespace, .metadata.name, ((.metadata.ownerReferences // [])[0].name // ""), (.status.succeeded // 0), (.status.failed // 0), (.status.active // 0), (.status.completionTime // "")] | @tsv'
else
  printf 'jq не установлен: используйте jobs-wide.txt и jobs.yaml\n' >&2
fi
AUDIT_SH
audit_done
