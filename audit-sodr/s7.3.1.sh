#!/usr/bin/env bash
# Пункт 7.3.1: Gatekeeper ConstraintTemplates.
# Что запрашивается: какие ConstraintTemplate настроены.
# Как собирается: выгружается список и YAML constrainttemplates.templates.gatekeeper.sh.
# Как анализируется: проверяются CRD kind, schema и Rego targets в spec.targets.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "7.3.1" "Gatekeeper ConstraintTemplates"
audit_run "ConstraintTemplates список" "constrainttemplates.txt" kubectl get constrainttemplates -o wide
audit_run "ConstraintTemplates YAML" "constrainttemplates.yaml" kubectl get constrainttemplates -o yaml
audit_done
