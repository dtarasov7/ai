#!/usr/bin/env bash
# Пункт 2.5.2: VPA.
# Что запрашивается: все VerticalPodAutoscaler и их конфигурация.
# Как собирается: если VPA CRD установлен, выгружается `vpa` по всем namespaces в wide и YAML.
# Как анализируется: updatePolicy, resourcePolicy и recommendations проверяются по YAML; ошибка NotFound означает, что VPA API в кластере отсутствует.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "2.5.2" "Vertical Pod Autoscaler"
audit_run "VPA wide" "vpa-wide.txt" kubectl get vpa --all-namespaces -o wide
audit_run "VPA YAML" "vpa.yaml" kubectl get vpa --all-namespaces -o yaml
audit_run "VPA CRD наличие" "vpa-crd.txt" kubectl get crd verticalpodautoscalers.autoscaling.k8s.io -o yaml
audit_done
