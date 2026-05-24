#!/usr/bin/env bash
# Пункт 1.1.5: vanilla kubeadm - состав Control Plane, компоненты и версии.
# Что запрашивается: состав control plane, список системных компонентов и версии Kubernetes/узлов.
# Как собирается: читаются версии кластера и узлов, control-plane/master узлы, static-pod компоненты в kube-system и их YAML.
# Как анализируется: состав определяется по ролям узлов и pod labels component/tier, версии - по `kubectl version` и kubeletVersion в Node status.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.1.5" "kubeadm: Control Plane, компоненты, версии"
audit_run "Версия клиента и сервера Kubernetes" "kubectl-version.yaml" kubectl version -o yaml
audit_run "Узлы control-plane по современному label" "control-plane-nodes.txt" kubectl get nodes -l node-role.kubernetes.io/control-plane -o wide
audit_run "Узлы master по старому label" "master-nodes.txt" kubectl get nodes -l node-role.kubernetes.io/master -o wide
audit_run "Версии kubelet/container runtime на всех узлах" "node-versions.txt" kubectl get nodes -o custom-columns=NAME:.metadata.name,ROLES:.metadata.labels,KUBELET:.status.nodeInfo.kubeletVersion,CONTAINER_RUNTIME:.status.nodeInfo.containerRuntimeVersion,OS:.status.nodeInfo.osImage,KERNEL:.status.nodeInfo.kernelVersion
audit_run "Компоненты control plane в kube-system" "control-plane-pods-wide.txt" kubectl -n kube-system get pods -l tier=control-plane -o wide
audit_run "YAML kube-apiserver/kube-controller-manager/kube-scheduler/etcd pod" "control-plane-pods.yaml" kubectl -n kube-system get pods -l tier=control-plane -o yaml
audit_done
