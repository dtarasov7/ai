#!/usr/bin/env bash
# Пункт 1.2.2: список всех node groups с описанием назначения.
# Что запрашивается: имя node group, тип узлов, количество, vCPU/RAM на узел и назначение.
# Как собирается: для Deckhouse читаются NodeGroup, дополнительно собираются nodes с labels/capacity для группировки.
# Как анализируется: количество и характеристики сверяются по фактическим Node; поле назначения автоматически не выводится из Kubernetes и заполняется в подготовленном TSV.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.2.2" "Node groups: состав и назначение"
audit_run "Deckhouse NodeGroup в wide формате" "nodegroups-wide.txt" kubectl get nodegroups.deckhouse.io -o wide
audit_run "Deckhouse NodeGroup в YAML" "nodegroups.yaml" kubectl get nodegroups.deckhouse.io -o yaml
audit_run "Узлы с capacity и labels для сверки групп" "nodes-capacity-labels.txt" kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.capacity.cpu,MEMORY:.status.capacity.memory,INSTANCE:.metadata.labels.node\\.kubernetes\\.io/instance-type,NODEGROUP:.metadata.labels.node\\.deckhouse\\.io/group,ROLES:.metadata.labels --no-headers
audit_shell "Шаблон таблицы назначения node groups" "nodegroups-purpose-template.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'node_group\tтип_узлов\tколичество\tvcpu\tmemory\tназначение\n'
kubectl get nodegroups.deckhouse.io -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeType}{"\t\t\t\t"}{"\n"}{end}' 2>/dev/null || true
AUDIT_SH
audit_done
