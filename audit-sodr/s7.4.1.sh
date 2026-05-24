#!/usr/bin/env bash
# Пункт 7.4.1: Pod Security Standards по namespaces.
# Что запрашивается: baseline/restricted/privileged настройки Pod Security Admission.
# Как собирается: выгружается YAML namespaces и TSV labels pod-security.kubernetes.io/* через jq.
# Как анализируется: enforce/audit/warn labels на namespace определяют применяемые уровни PSS.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "7.4.1" "Pod Security Standards по namespaces"
audit_run "Namespaces YAML" "namespaces.yaml" kubectl get namespaces -o yaml
audit_shell "PSS labels по namespaces через jq, если jq установлен" "pod-security-standards.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tenforce\taudit\twarn\tenforce_version\taudit_version\twarn_version\n'
if command -v jq >/dev/null 2>&1; then
  kubectl get namespaces -o json | jq -r '.items[] | .metadata as $m | [$m.name, ($m.labels["pod-security.kubernetes.io/enforce"] // ""), ($m.labels["pod-security.kubernetes.io/audit"] // ""), ($m.labels["pod-security.kubernetes.io/warn"] // ""), ($m.labels["pod-security.kubernetes.io/enforce-version"] // ""), ($m.labels["pod-security.kubernetes.io/audit-version"] // ""), ($m.labels["pod-security.kubernetes.io/warn-version"] // "")] | @tsv'
else
  printf 'jq не установлен: используйте namespaces.yaml\n' >&2
fi
AUDIT_SH
audit_done
