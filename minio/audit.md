Ниже скрипт аудита, который **ничего не изменяет** в MinIO и использует только `minio-client` (`mc`). Он формирует каталог с отдельными отчётами по кластеру, пользователям, группам, политикам, бакетам, анонимному доступу и дополнительным настройкам.

```bash
#!/usr/bin/env bash
#
# minio-cluster-audit.sh
#
# Read-only аудит конфигурации MinIO через MinIO Client (mc).
#
# Использование:
#   ./minio-cluster-audit.sh <alias> [output-directory]
#
# Примеры:
#   ./minio-cluster-audit.sh production
#   ./minio-cluster-audit.sh production ./minio-audit
#
# Alias должен быть заранее настроен:
#   mc alias set production https://minio.example.com ACCESS_KEY SECRET_KEY
#
# Рекомендуется запускать с учётной записью, имеющей административные права.
#

set -uo pipefail

MC_BIN="${MC_BIN:-mc}"
ALIAS="${1:-}"
OUTPUT_ROOT="${2:-./minio-audit}"
TIMESTAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
REPORT_DIR="${OUTPUT_ROOT%/}/${ALIAS:-unknown}-${TIMESTAMP}"
ERROR_LOG="${REPORT_DIR}/errors.log"

if [[ -z "${ALIAS}" ]]; then
    echo "Использование: $0 <mc-alias> [output-directory]" >&2
    exit 1
fi

if ! command -v "${MC_BIN}" >/dev/null 2>&1; then
    echo "Ошибка: MinIO Client '${MC_BIN}' не найден в PATH." >&2
    exit 1
fi

mkdir -p \
    "${REPORT_DIR}/cluster" \
    "${REPORT_DIR}/identity/users" \
    "${REPORT_DIR}/identity/groups" \
    "${REPORT_DIR}/identity/policies" \
    "${REPORT_DIR}/buckets"

: > "${ERROR_LOG}"

log() {
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

sanitize_filename() {
    printf '%s' "$1" | sed 's#[^a-zA-Z0-9._-]#_#g'
}

command_available() {
    "${MC_BIN}" "$@" --help >/dev/null 2>&1
}

run_report() {
    local output_file="$1"
    local description="$2"
    shift 2

    log "${description}"

    {
        echo "# ${description}"
        echo "# UTC timestamp: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo "# Command: ${MC_BIN} $*"
        echo
    } > "${output_file}"

    if ! "${MC_BIN}" "$@" >> "${output_file}" 2>> "${ERROR_LOG}"; then
        {
            echo
            echo "[ERROR] Команда завершилась с ошибкой."
            echo "Подробности: ${ERROR_LOG}"
        } >> "${output_file}"

        printf '[ERROR] %s: %s %s\n' \
            "${description}" "${MC_BIN}" "$*" >> "${ERROR_LOG}"
        return 1
    fi
}

run_optional_report() {
    local output_file="$1"
    local description="$2"
    shift 2

    if command_available "${@:1:${#@}-1}" 2>/dev/null; then
        run_report "${output_file}" "${description}" "$@" || true
    else
        {
            echo "# ${description}"
            echo
            echo "Команда не поддерживается установленной версией mc."
            echo "Проверявшаяся команда: ${MC_BIN} $*"
        } > "${output_file}"
    fi
}

extract_json_strings() {
    local key="$1"

    if command -v jq >/dev/null 2>&1; then
        jq -r --arg key "${key}" '
            select(type == "object") |
            .[$key] //
            .result[$key] //
            .data[$key] //
            empty
        ' 2>/dev/null
    else
        sed -nE "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"([^\"]+)\".*/\1/p"
    fi
}

get_buckets() {
    local json_output

    if json_output="$("${MC_BIN}" ls --json "${ALIAS}" 2>> "${ERROR_LOG}")"; then
        printf '%s\n' "${json_output}" |
            extract_json_strings key |
            sed 's#/$##' |
            sed '/^$/d' |
            sort -u
        return
    fi

    "${MC_BIN}" ls "${ALIAS}" 2>> "${ERROR_LOG}" |
        awk '{print $NF}' |
        sed 's#/$##' |
        sed '/^$/d' |
        sort -u
}

get_users() {
    local json_output

    if json_output="$("${MC_BIN}" admin user list --json "${ALIAS}" 2>> "${ERROR_LOG}")"; then
        printf '%s\n' "${json_output}" |
            extract_json_strings accessKey |
            sed '/^$/d' |
            sort -u
        return
    fi

    "${MC_BIN}" admin user list "${ALIAS}" 2>> "${ERROR_LOG}" |
        awk '
            /^[[:space:]]*$/ { next }
            /^enabled|^disabled/ { print $2; next }
            /^Enabled|^Disabled/ { print $2; next }
        ' |
        sed '/^$/d' |
        sort -u
}

get_groups() {
    local json_output

    if json_output="$("${MC_BIN}" admin group list --json "${ALIAS}" 2>> "${ERROR_LOG}")"; then
        printf '%s\n' "${json_output}" |
            extract_json_strings groupName |
            sed '/^$/d' |
            sort -u
        return
    fi

    "${MC_BIN}" admin group list "${ALIAS}" 2>> "${ERROR_LOG}" |
        sed -E 's/^[^[:alnum:]_.@-]*//' |
        awk '{print $1}' |
        grep -Ev '^(Group|Status|Members|$)' |
        sort -u
}

get_policies() {
    local json_output

    if json_output="$("${MC_BIN}" admin policy list --json "${ALIAS}" 2>> "${ERROR_LOG}")"; then
        printf '%s\n' "${json_output}" |
            extract_json_strings policy |
            sed '/^$/d' |
            sort -u
        return
    fi

    "${MC_BIN}" admin policy list "${ALIAS}" 2>> "${ERROR_LOG}" |
        sed '/^[[:space:]]*$/d' |
        awk '{print $1}' |
        sort -u
}

audit_cluster() {
    run_report \
        "${REPORT_DIR}/cluster/mc-version.txt" \
        "Версия MinIO Client" \
        --version || true

    run_report \
        "${REPORT_DIR}/cluster/alias-list.txt" \
        "Настроенные alias MinIO Client" \
        alias list || true

    run_report \
        "${REPORT_DIR}/cluster/admin-info.txt" \
        "Информация о MinIO-кластере" \
        admin info "${ALIAS}" || true

    run_report \
        "${REPORT_DIR}/cluster/admin-info.jsonl" \
        "Информация о MinIO-кластере в JSON" \
        admin info --json "${ALIAS}" || true

    run_report \
        "${REPORT_DIR}/cluster/server-config.txt" \
        "Конфигурация MinIO Server" \
        admin config get "${ALIAS}" || true

    run_report \
        "${REPORT_DIR}/cluster/server-config.jsonl" \
        "Конфигурация MinIO Server в JSON" \
        admin config get --json "${ALIAS}" || true

    if command_available admin scanner; then
        run_report \
            "${REPORT_DIR}/cluster/scanner-status.txt" \
            "Состояние scanner" \
            admin scanner status "${ALIAS}" || true
    fi

    if command_available admin tier; then
        run_report \
            "${REPORT_DIR}/cluster/remote-tiers.txt" \
            "Настроенные remote tiers" \
            admin tier info "${ALIAS}" || true
    fi

    if command_available admin license; then
        run_report \
            "${REPORT_DIR}/cluster/license-info.txt" \
            "Информация о лицензии" \
            admin license info "${ALIAS}" || true
    fi
}

audit_identity() {
    local users_file="${REPORT_DIR}/identity/users-list.txt"
    local groups_file="${REPORT_DIR}/identity/groups-list.txt"
    local policies_file="${REPORT_DIR}/identity/policies-list.txt"

    run_report \
        "${users_file}" \
        "Список пользователей" \
        admin user list "${ALIAS}" || true

    run_report \
        "${REPORT_DIR}/identity/users-list.jsonl" \
        "Список пользователей в JSON" \
        admin user list --json "${ALIAS}" || true

    run_report \
        "${groups_file}" \
        "Список групп" \
        admin group list "${ALIAS}" || true

    run_report \
        "${REPORT_DIR}/identity/groups-list.jsonl" \
        "Список групп в JSON" \
        admin group list --json "${ALIAS}" || true

    run_report \
        "${policies_file}" \
        "Список IAM-политик" \
        admin policy list "${ALIAS}" || true

    run_report \
        "${REPORT_DIR}/identity/policies-list.jsonl" \
        "Список IAM-политик в JSON" \
        admin policy list --json "${ALIAS}" || true

    log "Получение детальной информации о пользователях"

    while IFS= read -r user; do
        [[ -z "${user}" ]] && continue

        local safe_user
        safe_user="$(sanitize_filename "${user}")"

        run_report \
            "${REPORT_DIR}/identity/users/${safe_user}.txt" \
            "Информация о пользователе ${user}" \
            admin user info "${ALIAS}" "${user}" || true
    done < <(get_users)

    log "Получение детальной информации о группах"

    while IFS= read -r group; do
        [[ -z "${group}" ]] && continue

        local safe_group
        safe_group="$(sanitize_filename "${group}")"

        run_report \
            "${REPORT_DIR}/identity/groups/${safe_group}.txt" \
            "Информация о группе ${group}" \
            admin group info "${ALIAS}" "${group}" || true
    done < <(get_groups)

    log "Экспорт содержимого IAM-политик"

    while IFS= read -r policy; do
        [[ -z "${policy}" ]] && continue

        local safe_policy
        safe_policy="$(sanitize_filename "${policy}")"

        run_report \
            "${REPORT_DIR}/identity/policies/${safe_policy}.json" \
            "Содержимое IAM-политики ${policy}" \
            admin policy info "${ALIAS}" "${policy}" || true
    done < <(get_policies)

    # Показывает привязки policy -> user/group, если команда поддерживается.
    if command_available admin policy entities; then
        run_report \
            "${REPORT_DIR}/identity/policy-entities.txt" \
            "Все привязки политик к пользователям и группам" \
            admin policy entities "${ALIAS}" || true

        run_report \
            "${REPORT_DIR}/identity/policy-entities.jsonl" \
            "Все привязки политик к пользователям и группам в JSON" \
            admin policy entities --json "${ALIAS}" || true
    else
        cat > "${REPORT_DIR}/identity/policy-entities.txt" <<EOF
Команда 'mc admin policy entities' не поддерживается установленной версией mc.

Привязки политик частично доступны в:
  identity/users/*.txt
  identity/groups/*.txt
EOF
    fi

    # Внешние IAM/IDP-настройки обычно отражаются в admin config get.
    # Дополнительно пытаемся получить LDAP-сущности, если они поддерживаются.
    if command_available idp ldap; then
        run_report \
            "${REPORT_DIR}/identity/ldap-accesskey-list.txt" \
            "LDAP service accounts/access keys" \
            idp ldap accesskey ls "${ALIAS}" || true
    fi
}

audit_bucket() {
    local bucket="$1"
    local safe_bucket
    local bucket_dir
    local target

    safe_bucket="$(sanitize_filename "${bucket}")"
    bucket_dir="${REPORT_DIR}/buckets/${safe_bucket}"
    target="${ALIAS}/${bucket}"

    mkdir -p "${bucket_dir}"

    run_report \
        "${bucket_dir}/summary.txt" \
        "Сводная информация о бакете ${bucket}" \
        stat "${target}" || true

    run_report \
        "${bucket_dir}/anonymous-access.txt" \
        "Настройки анонимного доступа бакета ${bucket}" \
        anonymous get "${target}" || true

    run_report \
        "${bucket_dir}/anonymous-access.jsonl" \
        "Настройки анонимного доступа бакета ${bucket} в JSON" \
        anonymous get --json "${target}" || true

    # Вывод правил анонимного доступа для путей/префиксов внутри бакета.
    if command_available anonymous list; then
        run_report \
            "${bucket_dir}/anonymous-rules.txt" \
            "Правила анонимного доступа бакета ${bucket}" \
            anonymous list "${target}" || true
    fi

    run_report \
        "${bucket_dir}/versioning.txt" \
        "Настройки versioning бакета ${bucket}" \
        version info "${target}" || true

    run_report \
        "${bucket_dir}/quota.txt" \
        "Настройки quota бакета ${bucket}" \
        quota info "${target}" || true

    run_report \
        "${bucket_dir}/lifecycle.txt" \
        "Lifecycle/ILM-конфигурация бакета ${bucket}" \
        ilm rule ls "${target}" || true

    run_report \
        "${bucket_dir}/encryption.txt" \
        "Настройки server-side encryption бакета ${bucket}" \
        encrypt info "${target}" || true

    run_report \
        "${bucket_dir}/replication.txt" \
        "Настройки bucket replication бакета ${bucket}" \
        replicate ls "${target}" || true

    if command_available retention; then
        run_report \
            "${bucket_dir}/retention.txt" \
            "Настройки object locking/retention бакета ${bucket}" \
            retention info "${target}" || true
    fi

    if command_available legalhold; then
        run_report \
            "${bucket_dir}/legalhold.txt" \
            "Настройки legal hold бакета ${bucket}" \
            legalhold info "${target}" || true
    fi

    if command_available event; then
        run_report \
            "${bucket_dir}/event-notifications.txt" \
            "Event notification rules бакета ${bucket}" \
            event ls "${target}" || true
    fi

    if command_available tag; then
        run_report \
            "${bucket_dir}/tags.txt" \
            "Теги бакета ${bucket}" \
            tag list "${target}" || true
    fi

    if command_available replicate status; then
        run_report \
            "${bucket_dir}/replication-status.txt" \
            "Статус репликации бакета ${bucket}" \
            replicate status "${target}" || true
    fi
}

audit_buckets() {
    local buckets_list="${REPORT_DIR}/buckets-list.txt"

    run_report \
        "${buckets_list}" \
        "Список бакетов" \
        ls "${ALIAS}" || true

    run_report \
        "${REPORT_DIR}/buckets-list.jsonl" \
        "Список бакетов в JSON" \
        ls --json "${ALIAS}" || true

    log "Получение настроек отдельных бакетов"

    while IFS= read -r bucket; do
        [[ -z "${bucket}" ]] && continue
        audit_bucket "${bucket}"
    done < <(get_buckets)
}

write_summary() {
    local bucket_count
    local user_count
    local group_count
    local policy_count

    bucket_count="$(get_buckets | wc -l | tr -d ' ')"
    user_count="$(get_users | wc -l | tr -d ' ')"
    group_count="$(get_groups | wc -l | tr -d ' ')"
    policy_count="$(get_policies | wc -l | tr -d ' ')"

    cat > "${REPORT_DIR}/README.txt" <<EOF
MinIO cluster configuration audit
==================================

Alias:             ${ALIAS}
Created at (UTC):  $(date -u '+%Y-%m-%dT%H:%M:%SZ')
mc binary:         ${MC_BIN}
mc version:        $("${MC_BIN}" --version 2>/dev/null | head -n 1)

Обнаружено:
  Бакетов:         ${bucket_count}
  Пользователей:   ${user_count}
  Групп:           ${group_count}
  IAM-политик:     ${policy_count}

Структура отчёта:
  cluster/
    admin-info.txt            Состояние и топология кластера
    server-config.txt         Конфигурация MinIO Server
    remote-tiers.txt          Настройки tiering, если поддерживаются

  identity/
    users-list.txt            Пользователи
    users/                    Детали пользователей и применённые политики
    groups-list.txt           Группы
    groups/                   Состав групп и применённые политики
    policies-list.txt         Список политик
    policies/                 JSON-содержимое каждой политики
    policy-entities.txt       Привязки политик к пользователям и группам

  buckets/
    <bucket>/
      anonymous-access.txt    Анонимный/public-доступ
      anonymous-rules.txt     Правила доступа по префиксам
      versioning.txt          Versioning
      quota.txt               Quota
      lifecycle.txt           Lifecycle/ILM
      encryption.txt          Server-side encryption
      replication.txt         Bucket replication
      retention.txt           Object locking/retention
      event-notifications.txt Bucket notifications
      tags.txt                Теги бакета

Ошибки и неподдерживаемые операции:
  errors.log

Важно:
  - Скрипт выполняет только операции чтения.
  - Полнота отчёта зависит от прав используемой учётной записи.
  - Не все команды доступны во всех версиях mc и MinIO Server.
  - Пароли, secret keys и другие секреты IAM API обычно не возвращаются.
EOF
}

main() {
    log "Проверка alias '${ALIAS}'"

    if ! "${MC_BIN}" admin info "${ALIAS}" >/dev/null 2>> "${ERROR_LOG}"; then
        echo "Ошибка: не удалось подключиться к MinIO alias '${ALIAS}'." >&2
        echo "Проверьте: mc alias list" >&2
        echo "Журнал: ${ERROR_LOG}" >&2
        exit 2
    fi

    audit_cluster
    audit_identity
    audit_buckets
    write_summary

    log "Аудит завершён"
    echo
    echo "Отчёт сохранён в:"
    echo "  ${REPORT_DIR}"
    echo
    echo "Основной файл:"
    echo "  ${REPORT_DIR}/README.txt"

    if [[ -s "${ERROR_LOG}" ]]; then
        echo
        echo "Некоторые команды вернули ошибки или не поддерживаются:"
        echo "  ${ERROR_LOG}"
    fi
}

main "$@"
```

### Запуск

```bash
chmod +x minio-cluster-audit.sh

mc alias set production \
  https://minio.example.com \
  "$MINIO_ACCESS_KEY" \
  "$MINIO_SECRET_KEY"

./minio-cluster-audit.sh production ./reports
```

Для административного аудита используемой учётной записи нужны права на `admin info`, просмотр IAM, конфигурации сервера и настроек бакетов. Скрипт проверяет доступность необязательных команд, поскольку набор операций может отличаться между версиями `mc` и MinIO Server. MinIO Client является официальным CLI для управления S3-совместимым хранилищем MinIO. ([MinIO AIStor Documentation][1])

Особенно чувствителен файл `cluster/server-config.txt`: хотя секретные значения обычно маскируются сервером, отчёт всё равно стоит хранить как конфиденциальный административный артефакт.

[1]: https://docs.min.io/aistor/?utm_source=chatgpt.com "MinIO AIStor Documentation"

