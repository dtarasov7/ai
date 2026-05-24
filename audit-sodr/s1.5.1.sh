#!/usr/bin/env bash
# Пункт 1.5.1: MutatingWebhookConfiguration.
# Что запрашивается: все mutating webhook configurations.
# Как собирается: выгружается список и полный YAML MutatingWebhookConfiguration.
# Как анализируется: проверяются clientConfig, rules, namespace/object selectors, failurePolicy и sideEffects.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.5.1" "Mutating webhooks"
audit_run "MutatingWebhookConfiguration список" "mutatingwebhooks.txt" kubectl get mutatingwebhookconfigurations -o wide
audit_run "MutatingWebhookConfiguration YAML" "mutatingwebhooks.yaml" kubectl get mutatingwebhookconfigurations -o yaml
audit_done
