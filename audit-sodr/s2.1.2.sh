#!/usr/bin/env bash
# Пункт 2.1.2: для каждого приложения имя, namespace, тип и назначение.
# Что запрашивается: таблица приложений с типом stateless/stateful/daemon и назначением.
# Как собирается: читаются deployments, statefulsets и daemonsets во всех namespaces.
# Как анализируется: тип выводится из kind ресурса; назначение не хранится в Kubernetes гарантированно и заполняется в шаблоне после сверки с владельцами систем.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.1.2" "Приложения: имя, namespace, тип, назначение"
audit_run "Workload таблица" "applications.txt" kubectl get deployments,statefulsets,daemonsets --all-namespaces -o custom-columns=KIND:.kind,NAMESPACE:.metadata.namespace,NAME:.metadata.name,READY:.status.readyReplicas,REPLICAS:.status.replicas,IMAGES:.spec.template.spec.containers[*].image
audit_run "Workload YAML для детализации" "applications.yaml" kubectl get deployments,statefulsets,daemonsets --all-namespaces -o yaml
audit_shell "Шаблон таблицы приложений с назначением" "applications-purpose-template.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tname\tkind\tтип\tназначение\n'
kubectl get deployments,statefulsets,daemonsets --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.kind}{"\t"}{.kind}{"\t"}{"\n"}{end}' 2>/dev/null | sed -e 's/Deployment/stateless/g' -e 's/StatefulSet/stateful/g' -e 's/DaemonSet/daemon/g'
AUDIT_SH
audit_done
