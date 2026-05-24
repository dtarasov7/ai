#!/usr/bin/env bash
# Пункт 8.1.3: внутренний DNS CoreDNS.
# Что запрашивается: конфигурация внутреннего DNS, в первую очередь CoreDNS.
# Как собирается: выгружается CoreDNS ConfigMap, Deployment/Pods/Service и kube-dns ConfigMap как fallback.
# Как анализируется: Corefile показывает forward/cache/rewrite/stub zones; Deployment/Service подтверждают фактически запущенный DNS.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "8.1.3" "CoreDNS configuration"
audit_run "CoreDNS ConfigMap" "coredns-configmap.yaml" kubectl -n kube-system get configmap coredns -o yaml
audit_run "CoreDNS Deployment" "coredns-deployment.yaml" kubectl -n kube-system get deployment coredns -o yaml
audit_run "CoreDNS pods" "coredns-pods.txt" kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide
audit_run "kube-dns Service" "kube-dns-service.yaml" kubectl -n kube-system get service kube-dns -o yaml
audit_run "kube-dns ConfigMap fallback" "kube-dns-configmap.yaml" kubectl -n kube-system get configmap kube-dns -o yaml
audit_done
