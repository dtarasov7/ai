#!/usr/bin/env bash

set -Eeuo pipefail

audit_init() {
  AUDIT_POINT="$1"
  AUDIT_TITLE="$2"
  AUDIT_SCRIPT_DIR="${AUDIT_SCRIPT_DIR:-$(pwd)}"
  AUDIT_OUTPUT_ROOT="${AUDIT_OUTPUT_ROOT:-$AUDIT_SCRIPT_DIR/audit-output}"
  AUDIT_OUT_DIR="$AUDIT_OUTPUT_ROOT/s$AUDIT_POINT"
  AUDIT_SUMMARY="$AUDIT_OUT_DIR/README.txt"

  mkdir -p "$AUDIT_OUT_DIR"
  {
    printf 'Пункт: %s\n' "$AUDIT_POINT"
    printf 'Тема: %s\n' "$AUDIT_TITLE"
    printf 'Дата сбора UTC: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'Каталог результата: %s\n\n' "$AUDIT_OUT_DIR"
  } >"$AUDIT_SUMMARY"

  printf 'Пишу результаты в %s\n' "$AUDIT_OUT_DIR"
}

audit_log() {
  printf '%s\n' "$*" | tee -a "$AUDIT_SUMMARY" >&2
}

audit_command_line() {
  local arg
  for arg in "$@"; do
    printf '%q ' "$arg"
  done
}

audit_note_command() {
  local desc="$1"
  local outfile="$2"
  shift 2

  {
    printf '## %s\n' "$desc"
    printf 'Файл: %s\n' "$outfile"
    printf 'Команда: '
    audit_command_line "$@"
    printf '\n\n'
  } >>"$AUDIT_SUMMARY"
}

audit_run() {
  local desc="$1"
  local outfile="$2"
  shift 2

  audit_note_command "$desc" "$outfile" "$@"

  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Команда не найдена: %s\n' "$1" >"$AUDIT_OUT_DIR/$outfile"
    audit_log "WARN: $desc: команда '$1' не найдена, файл $outfile содержит описание проблемы."
    return 0
  fi

  set +e
  "$@" >"$AUDIT_OUT_DIR/$outfile" 2>"$AUDIT_OUT_DIR/$outfile.stderr"
  local rc=$?
  set -e

  if [[ ! -s "$AUDIT_OUT_DIR/$outfile.stderr" ]]; then
    rm -f "$AUDIT_OUT_DIR/$outfile.stderr"
  fi

  if [[ $rc -eq 0 ]]; then
    audit_log "OK: $desc -> $outfile"
  else
    audit_log "WARN: $desc: команда завершилась с кодом $rc, см. $outfile и $outfile.stderr."
  fi

  return 0
}

audit_shell() {
  local desc="$1"
  local outfile="$2"
  local tmp
  tmp="$(mktemp)"
  cat >"$tmp"

  {
    printf '## %s\n' "$desc"
    printf 'Файл: %s\n' "$outfile"
    printf 'Команда: bash <встроенный сценарий>\n\n'
  } >>"$AUDIT_SUMMARY"

  set +e
  AUDIT_OUT_DIR="$AUDIT_OUT_DIR" bash -o pipefail "$tmp" >"$AUDIT_OUT_DIR/$outfile" 2>"$AUDIT_OUT_DIR/$outfile.stderr"
  local rc=$?
  set -e
  rm -f "$tmp"

  if [[ ! -s "$AUDIT_OUT_DIR/$outfile.stderr" ]]; then
    rm -f "$AUDIT_OUT_DIR/$outfile.stderr"
  fi

  if [[ $rc -eq 0 ]]; then
    audit_log "OK: $desc -> $outfile"
  else
    audit_log "WARN: $desc: встроенный сценарий завершился с кодом $rc, см. $outfile и $outfile.stderr."
  fi

  return 0
}

audit_done() {
  audit_log "Готово. Основной индекс результата: $AUDIT_SUMMARY"
}
