#!/usr/bin/env bash
set -Eeuo pipefail
K="${KUBECTL:-kubectl}"
NS=gatekeeper-exec-demo
TEMPLATE=d8demoexecguard
CONSTRAINT=deny-exec-demo
# Restrict cleanup to artifacts that belong to the demo.
if "$K" get d8demoexecguard.constraints.gatekeeper.sh "$CONSTRAINT" >/dev/null 2>&1; then
  [[ "$("$K" get d8demoexecguard.constraints.gatekeeper.sh "$CONSTRAINT" -o jsonpath='{.metadata.labels.gatekeeper-exec-demo}')" == 'owned' ]] || { echo 'Refusing to delete unowned constraint' >&2; exit 1; }
  "$K" delete d8demoexecguard.constraints.gatekeeper.sh "$CONSTRAINT" --wait=true
fi
if "$K" get constrainttemplate "$TEMPLATE" >/dev/null 2>&1; then
  [[ "$("$K" get constrainttemplate "$TEMPLATE" -o jsonpath='{.metadata.labels.gatekeeper-exec-demo}')" == 'owned' ]] || { echo 'Refusing to delete unowned template' >&2; exit 1; }
  "$K" delete constrainttemplate "$TEMPLATE" --wait=true
fi
if "$K" get namespace "$NS" >/dev/null 2>&1; then
  [[ "$("$K" get ns "$NS" -o jsonpath='{.metadata.labels.gatekeeper-exec-demo}')" == 'owned' ]] || { echo 'Refusing to delete unowned namespace' >&2; exit 1; }
  "$K" delete namespace "$NS" --wait=true
fi
echo 'PASS: Demo constraint, template, namespace and Pod removed.'
