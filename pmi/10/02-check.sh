#!/usr/bin/env bash
set -Eeuo pipefail
K="${KUBECTL:-kubectl}"
NS=gatekeeper-exec-demo
POD=exec-test
CONSTRAINT=deny-exec-demo
fail() { echo "FAIL: $*" >&2; exit 1; }
"$K" get crd d8demoexecguards.constraints.gatekeeper.sh >/dev/null || fail 'No demo Gatekeeper CRD'
"$K" get d8demoexecguard.constraints.gatekeeper.sh "$CONSTRAINT" >/dev/null || fail 'Demo constraint is missing'
[[ "$("$K" get d8demoexecguard.constraints.gatekeeper.sh "$CONSTRAINT" -o jsonpath='{.spec.enforcementAction}')" == 'deny' ]] || fail 'Policy is not in deny mode'
"$K" -n "$NS" wait --for=condition=Ready pod/"$POD" --timeout=30s >/dev/null || fail 'Pod not Ready'

echo '[1/3] Existing Pod is running...'
"$K" -n "$NS" get pod "$POD"
echo '[2/3] kubectl exec is expected to be denied by Gatekeeper...'
DENIED=0
for attempt in 1 2 3 4 5; do
  set +e
  OUTPUT="$("$K" -n "$NS" exec "$POD" -- /bin/sh -c 'echo SHOULD_NOT_EXECUTE' 2>&1)"
  STATUS=$?
  set -e
  if [[ $STATUS -ne 0 && "$OUTPUT" == *DEMO_GATEKEEPER_EXEC_DENIED* ]]; then
    DENIED=1
    break
  fi
  if [[ $STATUS -ne 0 ]]; then
    echo "Attempt $attempt: denied, but not with expected Gatekeeper marker: $OUTPUT" >&2
  else
    echo "Attempt $attempt: exec was allowed (policy propagation may be pending)" >&2
  fi
  sleep 2
done
[[ $DENIED -eq 1 ]] || fail "No demonstrable Gatekeeper denial. Last result: $OUTPUT"
echo "PASS: Gatekeeper rejected the API CONNECT request:"
echo "$OUTPUT"

echo '[3/3] Pod is still Running / application continues...'
PHASE="$("$K" -n "$NS" get pod "$POD" -o jsonpath='{.status.phase}')"
[[ "$PHASE" == 'Running' ]] || fail "Unexpected Pod phase: $PHASE"
echo 'PASS: Pod Running, but external kubectl exec blocked.'
echo 'OVERALL RESULT: PASS'
