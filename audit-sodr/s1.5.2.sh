#!/usr/bin/env bash
# Пункт 1.5.2: ValidatingWebhookConfiguration.
# Что запрашивается: все validating webhook configurations.
# Как собирается: выгружается список и полный YAML ValidatingWebhookConfiguration.
# Как анализируется: проверяются clientConfig, rules, namespace/object selectors, failurePolicy и matchPolicy.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.5.2" "Validating webhooks"
audit_run "ValidatingWebhookConfiguration список" "validatingwebhooks.txt" kubectl get validatingwebhookconfigurations -o wide
audit_run "ValidatingWebhookConfiguration YAML" "validatingwebhooks.yaml" kubectl get validatingwebhookconfigurations -o yaml
audit_done
