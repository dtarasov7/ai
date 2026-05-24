#!/usr/bin/env bash
# Пункт 7.4.2: привилегированные контейнеры и runAsUser=0.
# Что запрашивается: список pod/container с privileged=true или root user.
# Как собирается: выгружается pods YAML и строится TSV по securityContext containers/initContainers/ephemeralContainers через jq.
# Как анализируется: флаги privileged, runAsUser=0, allowPrivilegeEscalation и hostNetwork/hostPID/hostIPC показывают повышенные привилегии.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "7.4.2" "Privileged/root containers"
audit_run "Pods YAML для анализа SecurityContext" "pods.yaml" kubectl get pods --all-namespaces -o yaml
audit_shell "Privileged/root containers через jq, если jq установлен" "privileged-containers.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tpod\tcontainer_type\tcontainer\tprivileged\trunAsUser\tallowPrivilegeEscalation\thostNetwork\thostPID\thostIPC\n'
if command -v jq >/dev/null 2>&1; then
  kubectl get pods --all-namespaces -o json | jq -r '
    .items[] as $pod |
    ([
      (($pod.spec.initContainers // [])[] | . + {"_type":"init"}),
      (($pod.spec.containers // [])[] | . + {"_type":"container"}),
      (($pod.spec.ephemeralContainers // [])[] | . + {"_type":"ephemeral"})
    ])[] |
    select((.securityContext.privileged // false) == true or (.securityContext.runAsUser // -1) == 0 or (.securityContext.allowPrivilegeEscalation // false) == true or ($pod.spec.hostNetwork // false) == true or ($pod.spec.hostPID // false) == true or ($pod.spec.hostIPC // false) == true) |
    [$pod.metadata.namespace, $pod.metadata.name, ._type, .name, (.securityContext.privileged // false), (.securityContext.runAsUser // ""), (.securityContext.allowPrivilegeEscalation // ""), ($pod.spec.hostNetwork // false), ($pod.spec.hostPID // false), ($pod.spec.hostIPC // false)] | @tsv'
else
  printf 'jq не установлен: используйте pods.yaml\n' >&2
fi
AUDIT_SH
audit_done
