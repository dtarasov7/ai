#!/usr/bin/env bash
# Пункт 1.2.4: TopologySpreadConstraints и taints на node groups.
# Что запрашивается: настройки распределения и taints на группах узлов.
# Как собирается: выгружаются Deckhouse NodeGroup describe/YAML, taints на Node и workload YAML для поиска topologySpreadConstraints.
# Как анализируется: taints проверяются в NodeGroup/Node spec, topologySpreadConstraints ищутся в шаблонах pod у workload и сопоставляются с группами по nodeSelector/affinity.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.2.4" "TopologySpreadConstraints и taints"
audit_run "Deckhouse NodeGroup describe" "nodegroups-describe.txt" kubectl describe nodegroups.deckhouse.io
audit_run "Deckhouse NodeGroup YAML" "nodegroups.yaml" kubectl get nodegroups.deckhouse.io -o yaml
audit_run "Taints на узлах" "node-taints.txt" kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints
audit_run "Workload YAML для анализа topologySpreadConstraints" "workloads.yaml" kubectl get deployments,statefulsets,daemonsets --all-namespaces -o yaml
audit_shell "Поиск topologySpreadConstraints в workload YAML" "topology-spread-snippets.txt" <<'AUDIT_SH'
set -Eeuo pipefail
kubectl get deployments,statefulsets,daemonsets --all-namespaces -o yaml | grep -n -A20 -B5 'topologySpreadConstraints' || true
AUDIT_SH
audit_done
