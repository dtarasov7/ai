#!/usr/bin/env bash
set -Eeuo pipefail

# Demo for Deckhouse Kubernetes Platform 1.73.4
K="${KUBECTL:-kubectl}"
NS="gatekeeper-exec-demo"
POD="exec-test"
TEMPLATE="d8demoexecguard"
CONSTRAINT="deny-exec-demo"
IMAGE="${DEMO_IMAGE:-busybox:1.36}"

fail() { echo "ERROR: $*" >&2; exit 1; }
command -v "$K" >/dev/null 2>&1 || fail "kubectl/d8 executable not found: $K"
"$K" cluster-info >/dev/null || fail "No access to cluster"
"$K" get crd constrainttemplates.templates.gatekeeper.sh >/dev/null 2>&1 || fail "Gatekeeper ConstraintTemplate CRD missing; enable admission-policy-engine"
"$K" get validatingwebhookconfigurations -o yaml | grep -q 'pods/exec' || fail "No admission webhook for pods/exec found; check Deckhouse v1.73.4 and admission-policy-engine"
if "$K" get ns "$NS" >/dev/null 2>&1; then
  [[ "$("$K" get ns "$NS" -o jsonpath='{.metadata.labels.gatekeeper-exec-demo}')" == 'owned' ]] || fail "Namespace $NS exists and is not owned by this demo"
else
  "$K" create namespace "$NS"
  "$K" label namespace "$NS" gatekeeper-exec-demo=owned
fi

# Create the Pod without a restrictive exec policy to prove that RBAC allows exec.
cat <<YAML | "$K" -n "$NS" apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  labels:
    app: gatekeeper-exec-demo
spec:
  terminationGracePeriodSeconds: 0
  containers:
    - name: app
      image: $IMAGE
      imagePullPolicy: IfNotPresent
      command: ["/bin/sh", "-c", "while true; do sleep 3600; done"]
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault
YAML
"$K" -n "$NS" wait --for=condition=Ready "pod/$POD" --timeout=180s || fail "Test pod is not Ready; check image access and pod events"

# When rerunning after successful setup, remove our constraint temporarily for baseline.
if "$K" get d8demoexecguard.constraints.gatekeeper.sh "$CONSTRAINT" >/dev/null 2>&1; then
  "$K" delete d8demoexecguard.constraints.gatekeeper.sh "$CONSTRAINT" --wait=true
fi

echo 'Checking baseline: kubectl exec MUST work without the demo policy...'
BASELINE="$("$K" -n "$NS" exec "$POD" -- /bin/sh -c 'echo BASELINE_EXEC_OK' 2>&1)" || fail "Baseline exec failed, cannot prove Gatekeeper denial: $BASELINE"
[[ "$BASELINE" == *BASELINE_EXEC_OK* ]] || fail "Unexpected baseline exec output: $BASELINE"
echo "PASS: $BASELINE"

cat <<'YAML' | "$K" apply -f -
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: d8demoexecguard
  labels:
    gatekeeper-exec-demo: owned
spec:
  crd:
    spec:
      names:
        kind: D8DemoExecGuard
      validation:
        openAPIV3Schema:
          type: object
          properties:
            forbiddenNamespaces:
              type: array
              items:
                type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package d8.demoexecguard

        violation[{"msg": msg}] {
          input.review.operation == "CONNECT"
          input.review.resource.resource == "pods"
          sr := object.get(input.review, "requestSubResource", object.get(input.review, "subResource", ""))
          sr == "exec"
          input.review.namespace == input.parameters.forbiddenNamespaces[_]
          msg := "DEMO_GATEKEEPER_EXEC_DENIED: kubectl exec is prohibited by Gatekeeper"
        }
YAML

"$K" wait --for=condition=Established crd/d8demoexecguards.constraints.gatekeeper.sh --timeout=120s || fail "Constraint CRD not established"
# Ensure the ConstraintTemplate itself is accepted by Gatekeeper.
# Gatekeeper exposes .status.created rather than a universal "Ready" condition.
TEMPLATE_READY=0
for attempt in $(seq 1 30); do
  CREATED="$("$K" get constrainttemplate "$TEMPLATE" -o jsonpath='{.status.created}' 2>/dev/null || true)"
  if [[ "$CREATED" == 'true' ]]; then TEMPLATE_READY=1; break; fi
  sleep 2
done
[[ $TEMPLATE_READY -eq 1 ]] || fail "ConstraintTemplate not created by Gatekeeper (check .status)"
cat <<YAML | "$K" apply -f -
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: D8DemoExecGuard
metadata:
  name: $CONSTRAINT
  labels:
    gatekeeper-exec-demo: owned
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: ["*"]
        kinds: ["*"]
    scope: Namespaced
  parameters:
    forbiddenNamespaces:
      - $NS
YAML

echo 'PASS: Pod and Gatekeeper deny policy installed.'
echo "Next: ./02-check.sh"
