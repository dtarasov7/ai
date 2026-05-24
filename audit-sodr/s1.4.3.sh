#!/usr/bin/env bash
# Пункт 1.4.3: default requests/limits для новых pod.
# Что запрашивается: значения requests/limits по умолчанию, применяемые к новым pod.
# Как собирается: читаются LimitRange по всем namespaces, так как Kubernetes берет defaults именно из LimitRange.
# Как анализируется: default и defaultRequest в LimitRange определяют CPU/Memory defaults; отсутствие LimitRange означает отсутствие namespace defaults.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "1.4.3" "Default requests/limits"
audit_run "LimitRange YAML как источник default requests/limits" "limitranges.yaml" kubectl get limitrange --all-namespaces -o yaml
audit_run "LimitRange describe для человекочитаемого анализа" "limitranges-describe.txt" kubectl describe limitrange --all-namespaces
audit_shell "Сводка default/defaultRequest из LimitRange" "default-requests-limits-snippets.txt" <<'AUDIT_SH'
set -Eeuo pipefail
kubectl get limitrange --all-namespaces -o yaml | grep -n -E 'namespace:|name:|default:|defaultRequest:|cpu:|memory:' || true
AUDIT_SH
audit_done
