#!/usr/bin/env bash
# Пункт 7.2.2: список всех Secrets без значений.
# Что запрашивается: имена, namespaces, типы и метаданные Secrets без раскрытия data/stringData.
# Как собирается: используется `kubectl get secrets` в table/custom-columns; полный YAML намеренно не выгружается, чтобы не сохранить значения.
# Как анализируется: оцениваются namespace, type, возраст и количество ключей; содержимое Secret не читается.

set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$AUDIT_SCRIPT_DIR/audit-common.sh"

audit_init "7.2.2" "Secrets без значений"
audit_run "Secrets таблица без значений" "secrets.txt" kubectl get secrets --all-namespaces
audit_run "Secrets metadata без data" "secrets-metadata.txt" kubectl get secrets --all-namespaces -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,TYPE:.type,CREATED:.metadata.creationTimestamp
audit_shell "Secrets metadata TSV через jq без data/stringData, если jq установлен" "secrets-metadata.tsv" <<'AUDIT_SH'
set -Eeuo pipefail
printf 'namespace\tname\ttype\tdata_keys\tcreated\n'
if command -v jq >/dev/null 2>&1; then
  kubectl get secrets --all-namespaces -o json | jq -r '.items[] | [.metadata.namespace, .metadata.name, .type, ((.data // {}) | keys | join(",")), (.metadata.creationTimestamp // "")] | @tsv'
else
  printf 'jq не установлен: используйте secrets.txt\n' >&2
fi
AUDIT_SH
audit_done
