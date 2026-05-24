#!/usr/bin/env bash
# Пункт 2.3.6: внешне доступные сервисы и порты.
# Что запрашивается: сервисы типа LoadBalancer/NodePort и опубликованные порты.
# Как собирается: выгружается список всех Service и отдельная TSV выборка внешних Service.
# Как анализируется: внешняя доступность определяется по spec.type LoadBalancer/NodePort, портам, nodePort и external IP/hostname.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.3.6" "Внешне доступные Service"
audit_run "Все Service wide" "services-wide.txt" kubectl get svc --all-namespaces -o wide
audit_run "Все Service YAML" "services.yaml" kubectl get svc --all-namespaces -o yaml
audit_shell "LoadBalancer/NodePort services через jq, если jq установлен" "external-services.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tservice\ttype\tcluster_ip\texternal\tports\n'
if command -v jq >/dev/null 2>&1; then
  kubectl get svc --all-namespaces -o json | jq -r '.items[] | select(.spec.type == "LoadBalancer" or .spec.type == "NodePort") | [.metadata.namespace, .metadata.name, .spec.type, (.spec.clusterIP // ""), ((.status.loadBalancer.ingress // []) | map(.ip // .hostname) | join(",")), (.spec.ports | map((.name // "-") + ":" + (.port|tostring) + "->" + (.targetPort|tostring) + "/nodePort=" + ((.nodePort // "")|tostring)) | join(","))] | @tsv'
else
  printf 'jq не установлен: используйте services-wide.txt для ручной фильтрации LoadBalancer/NodePort\n' >&2
fi
AUDIT_SH
audit_done
