#!/usr/bin/env bash
# Пункт 1.2.5: конфигурация CNI.
# Что запрашивается: какой CNI используется (Flannel, Cilium, Calico и т.п.) и его конфигурация.
# Как собирается: ищутся CNI pods во всех namespaces и выгружаются типовые ConfigMap для cilium/calico/flannel, включая Deckhouse namespace.
# Как анализируется: тип CNI определяется по запущенным DaemonSet/Pod и именам ConfigMap; YAML ConfigMap показывает параметры dataplane.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.2.5" "CNI: тип и конфигурация"
audit_shell "Поиск CNI pod/daemonset по именам" "cni-workloads.txt" <<'AUDIT_SH'
set -Eeuo pipefail
kubectl get pods,daemonsets --all-namespaces -o wide | grep -Ei 'cilium|calico|flannel|weave|antrea|canal|cni' || true
AUDIT_SH
audit_run "ConfigMap cilium-config в kube-system" "kube-system-cilium-config.yaml" kubectl -n kube-system get configmap cilium-config -o yaml
audit_run "ConfigMap cilium-config в d8-cni-cilium" "d8-cni-cilium-config.yaml" kubectl -n d8-cni-cilium get configmap cilium-config -o yaml
audit_run "ConfigMap calico-config" "calico-config.yaml" kubectl -n kube-system get configmap calico-config -o yaml
audit_run "ConfigMap kube-flannel-cfg" "kube-flannel-cfg.yaml" kubectl -n kube-system get configmap kube-flannel-cfg -o yaml
audit_done
