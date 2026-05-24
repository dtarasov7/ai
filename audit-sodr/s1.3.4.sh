#!/usr/bin/env bash
# Пункт 1.3.4: схема сети кластера.
# Что запрашивается: pod CIDR, service CIDR и DNS config.
# Как собирается: podCIDR берется из Node spec, DNS - из CoreDNS/kube-dns ConfigMap, service CIDR ищется в аргументах kube-apiserver.
# Как анализируется: pod CIDR сверяется по узлам, service CIDR - по `--service-cluster-ip-range`, DNS настройки - по Corefile/configmap.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.3.4" "Сетевая схема: pod CIDR, service CIDR, DNS"
audit_run "Pod CIDR по узлам" "node-pod-cidrs.txt" kubectl get nodes -o custom-columns=NAME:.metadata.name,POD_CIDR:.spec.podCIDR,POD_CIDRS:.spec.podCIDRs
audit_run "CoreDNS ConfigMap" "coredns-configmap.yaml" kubectl -n kube-system get configmap coredns -o yaml
audit_run "kube-dns ConfigMap, если используется" "kube-dns-configmap.yaml" kubectl -n kube-system get configmap kube-dns -o yaml
audit_run "kube-apiserver pod YAML для service CIDR" "kube-apiserver-pods.yaml" kubectl -n kube-system get pods -l component=kube-apiserver -o yaml
audit_shell "Поиск CIDR аргументов control plane" "control-plane-cidr-args.txt" <<'AUDIT_SH'
set -Eeuo pipefail
kubectl -n kube-system get pods -l component=kube-apiserver -o yaml | grep -E -- '--service-cluster-ip-range|--cluster-cidr|--service-node-port-range' || true
AUDIT_SH
audit_done
