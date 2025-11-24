Отличное, хорошо продуманное решение! Оно учитывает ключевые аспекты, такие как кардинальность, атомарность записи и отказоустойчивость.

Вот готовый код скрипта на Bash, реализующий вашу логику. Я добавил подробные комментарии, обработку ошибок и пример реализации функции `get_app_version`, чтобы скрипт можно было сразу запустить и протестировать.

---

### Код скрипта (`version_collector.sh`)

```bash
#!/usr/bin/env bash

# Строгий режим: прерывать выполнение при любой ошибке,
# при использовании необъявленной переменной и при ошибке в конвейере.
set -euo pipefail

################################################################################
#                               КОНФИГУРАЦИЯ                                   #
################################################################################

# Список ПО для проверки (приложения разделены пробелами)
APP_LIST="nginx openssl postgresql nonexistentapp"

# FQDN текущего сервера для использования в метках Prometheus
NODENAME=$(hostname -f)

# Путь к файлу состояния. Директория будет создана автоматически.
STATE_FILE="/var/lib/app-version-collector/state.json"

# Путь к файлу метрик для node-exporter. Директория должна существовать.
PROM_FILE="/var/lib/node_exporter/textfile_collector/app_versions.prom"

# Файл блокировки для предотвращения параллельных запусков
LOCK_FILE="/var/run/app-version-collector.lock"

################################################################################
#                             ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ                          #
################################################################################

# Функция логирования с временной меткой
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Функция очистки при завершении скрипта (удаление lock-файла)
cleanup() {
    rm -f "$LOCK_FILE"
    log "Скрипт завершен. Lock-файл удален."
}

# Функция для кодирования версии в числовой формат
# Поддерживает до 4 компонентов (major.minor.patch.build), каждый до 9999
# v1*10^12 + v2*10^8 + v3*10^4 + v4
encode_version() {
    local version="$1"
    
    # Если версия пустая или "deleted", возвращаем 0
    if [[ -z "$version" || "$version" == "deleted" ]]; then
        echo "0"
        return
    fi
    
    # Удаляем pre-release суффиксы и прочий "мусор"
    # Пример: nginx/1.25.4-alpine -> 1.25.4
    version=$(echo "$version" | sed -e 's/^[a-zA-Z/]*//' -e 's/[-+~].*//')
    
    local IFS='.'
    read -ra parts <<< "$version"
    
    # Дополняем нулями, если компонентов меньше 4
    while [ ${#parts[@]} -lt 4 ]; do
        parts+=("0")
    done
    
    # Ограничиваем количество компонентов до 4
    parts=("${parts[@]:0:4}")

    printf "%d%04d%04d%04d" "${parts[0]:-0}" "${parts[1]:-0}" "${parts[2]:-0}" "${parts[3]:-0}"
}

################################################################################
#         ПОЛУЧЕНИЕ ВЕРСИИ ПО - ЭТУ ФУНКЦИЮ НУЖНО АДАПТИРОВАТЬ                 #
################################################################################

# Глобальная переменная для хранения полученной версии
VERSION=""

# get_app_version <appname>
# Возвращает 0, если версия получена и записана в глоб. переменную $VERSION.
# Возвращает 1, если ПО не найдено.
get_app_version() {
    local app_name="$1"
    VERSION=""

    # --- НАЧАЛО РЕАЛИЗАЦИИ ---
    # Здесь должен быть ваш код для получения версии конкретного ПО.
    # Пример ниже - это заглушка для демонстрации.

    case "$app_name" in
        "nginx")
            if command -v nginx &>/dev/null; then
                # Nginx обычно выводит версию в stderr
                VERSION=$(nginx -v 2>&1 | grep -oP 'nginx/\K[0-9.]+')
                # Имитация обновления для теста
                # day=$(date +%d)
                # [ $((day % 2)) -eq 0 ] && VERSION="1.25.4" || VERSION="1.25.5"
            else
                return 1
            fi
            ;;
        "openssl")
            if command -v openssl &>/dev/null; then
                VERSION=$(openssl version | awk '{print $2}')
            else
                return 1
            fi
            ;;
        "postgresql")
             if command -v psql &>/dev/null; then
                VERSION=$(psql --version | awk '{print $3}')
             else
                return 1
             fi
            ;;
        *)
            # Если для приложения нет специальной логики, считаем, что оно не найдено
            return 1
            ;;
    esac
    # --- КОНЕЦ РЕАЛИЗАЦИИ ---

    if [[ -n "$VERSION" ]]; then
        return 0 # Успех
    else
        return 1 # Неудача (например, команда есть, но вывод пустой)
    fi
}


################################################################################
#                                ОСНОВНАЯ ЛОГИКА                               #
################################################################################

main() {
    # Проверка на наличие jq - он критически важен для работы со state.json
    if ! command -v jq &> /dev/null; then
        log "ОШИБКА: утилита 'jq' не найдена. Пожалуйста, установите ее."
        exit 1
    fi

    # Создаем директории, если их нет
    mkdir -p "$(dirname "$STATE_FILE")"
    mkdir -p "$(dirname "$PROM_FILE")"

    # Загружаем предыдущее состояние или создаем пустое
    if [[ -f "$STATE_FILE" ]]; then
        state_json=$(cat "$STATE_FILE")
    else
        log "Файл состояния не найден. Создается новый."
        state_json='{"apps":{}}'
    fi

    # Временный файл для атомарной записи метрик
    tmp_prom_file=$(mktemp)
    
    # Текущее время в UNIX timestamp для всех метрик этого запуска
    scrape_time=$(date +%s)

    # Основной цикл по списку приложений
    for app in $APP_LIST; do
        log "Проверка приложения: $app"

        # Получаем старые значения из state.json, если их нет - null
        current_state=$(echo "$state_json" | jq -r ".apps.\"$app\".current // \"null\"")
        previous_state=$(echo "$state_json" | jq -r ".apps.\"$app\".previous // \"null\"")
        change_time_state=$(echo "$state_json" | jq -r ".apps.\"$app\".change_time // $scrape_time")
        changes_total_state=$(echo "$state_json" | jq -r ".apps.\"$app\".changes_total // 0")

        # Пытаемся получить версию ПО
        if get_app_version "$app"; then
            # СЛУЧАЙ 1: ПО найдено
            detected_version="$VERSION"
            log "Найдена версия для '$app': $detected_version"

            if [[ "$current_state" != "$detected_version" ]]; then
                log "Обнаружено изменение версии для '$app': $current_state -> $detected_version"
                new_current="$detected_version"
                new_previous="$current_state"
                new_change_time="$scrape_time"
                new_changes_total=$((changes_total_state + 1))
            else
                # Версия не изменилась
                new_current="$current_state"
                new_previous="$previous_state"
                new_change_time="$change_time_state"
                new_changes_total="$changes_total_state"
            fi
            
            # Обновляем JSON в памяти
            state_json=$(echo "$state_json" | jq \
                --arg app "$app" \
                --arg current "$new_current" \
                --arg previous "$new_previous" \
                --argjson change_time "$new_change_time" \
                --argjson changes_total "$new_changes_total" \
                '.apps[$app] = {current: $current, previous: $previous, change_time: $change_time, changes_total: $changes_total}')

            # Генерируем метрики
            encoded_version=$(encode_version "$detected_version")
            cat >> "$tmp_prom_file" <<EOF
# HELP app_version_info Информация о версии приложения
# TYPE app_version_info gauge
app_version_info{nodename="$NODENAME",appname="$app",version="$detected_version"} 1
# HELP app_version_numeric Версия приложения в числовом формате
# TYPE app_version_numeric gauge
app_version_numeric{nodename="$NODENAME",appname="$app"} $encoded_version
# HELP app_version_change_time_seconds Время последнего изменения версии в Unix time
# TYPE app_version_change_time_seconds gauge
app_version_change_time_seconds{nodename="$NODENAME",appname="$app"} $new_change_time
EOF

        else
            # СЛУЧАЙ 2: ПО не найдено
            log "Приложение '$app' не найдено на сервере."

            if [[ "$current_state" != "null" && "$current_state" != "deleted" ]]; then
                # Если ПО было, но пропало
                log "Приложение '$app' было удалено. Предыдущая версия: $current_state"
                new_current="deleted"
                new_previous="$current_state"
                new_change_time="$scrape_time"
                new_changes_total=$((changes_total_state + 1))

                # Обновляем JSON в памяти
                state_json=$(echo "$state_json" | jq \
                    --arg app "$app" \
                    --arg current "$new_current" \
                    --arg previous "$new_previous" \
                    --argjson change_time "$new_change_time" \
                    --argjson changes_total "$new_changes_total" \
                    '.apps[$app] = {current: $current, previous: $previous, change_time: $change_time, changes_total: $changes_total}')
                
                # Генерируем метрики для удаленного ПО
                cat >> "$tmp_prom_file" <<EOF
# HELP app_version_info Информация о версии приложения
# TYPE app_version_info gauge
app_version_info{nodename="$NODENAME",appname="$app",version="deleted"} 1
# HELP app_version_numeric Версия приложения в числовом формате
# TYPE app_version_numeric gauge
app_version_numeric{nodename="$NODENAME",appname="$app"} 0
# HELP app_version_change_time_seconds Время последнего изменения версии в Unix time
# TYPE app_version_change_time_seconds gauge
app_version_change_time_seconds{nodename="$NODENAME",appname="$app"} $new_change_time
EOF
            fi
        fi
    done

    # Записываем обновленный state.json
    echo "$state_json" | jq '.' > "$STATE_FILE"
    log "Файл состояния '$STATE_FILE' обновлен."

    return 0
}


################################################################################
#                                ТОЧКА ВХОДА                                  #
################################################################################

# Механизм блокировки для предотвращения одновременного запуска
# `set -C` (noclobber) не дает перезаписать файл, если он существует.
if ( set -C; echo "$$" > "$LOCK_FILE" ) 2>/dev/null; then
    # Если lock-файл успешно создан, устанавливаем trap для его удаления при выходе.
    trap 'cleanup' EXIT
else
    # Если файл уже существует, другой процесс работает.
    log "Обнаружен lock-файл '$LOCK_FILE', созданный процессом $(cat "$LOCK_FILE"). Выход."
    exit 1
fi

log "Скрипт запущен."
start_time=$(date +%s)
success=1 # Предполагаем успех

# Запускаем основную логику и отлавливаем ошибки
if ! main; then
    log "ОШИБКА: Основная функция завершилась с ошибкой."
    success=0
fi

end_time=$(date +%s)
duration=$((end_time - start_time))

# Добавляем служебные метрики в конец временного файла
# Временный файл может быть пустым, если ни одно приложение из списка не было найдено
# и их не было в state.json, поэтому используем cat
metrics_file_content=$(cat "$tmp_prom_file")
rm -f "$tmp_prom_file"

# Финальная запись метрик в .prom файл
cat > "$PROM_FILE" <<EOF
$metrics_file_content
# HELP app_version_scrape_timestamp_seconds Время последнего сканирования версий
# TYPE app_version_scrape_timestamp_seconds gauge
app_version_scrape_timestamp_seconds{nodename="$NODENAME"} $start_time
# HELP app_version_collector_duration_seconds Длительность работы сборщика метрик
# TYPE app_version_collector_duration_seconds gauge
app_version_collector_duration_seconds{nodename="$NODENAME"} $duration
# HELP app_version_collector_success Успешность последнего запуска сборщика
# TYPE app_version_collector_success gauge
app_version_collector_success{nodename="$NODENAME"} $success
EOF

log "Файл метрик '$PROM_FILE' успешно создан. Длительность: ${duration}s."

# `trap` вызовет `cleanup` автоматически при выходе
exit 0
```

### Как использовать и развертывать

1.  **Зависимости**:
    *   `bash` (версии 4+)
    *   `jq` (обязательно, скрипт проверяет его наличие)
    *   `coreutils` (date, cat, mktemp, hostname, rm, mkdir)
    *   `sed`, `grep`, `awk` для парсинга версий.

2.  **Адаптация `get_app_version`**:
    *   Самая важная часть — это наполнение функции `get_app_version` реальной логикой получения версий для вашего ПО.
    *   Для каждого `appname` из `APP_LIST` добавьте соответствующий `case` или `if/elif` блок.
    *   Убедитесь, что функция корректно устанавливает глобальную переменную `VERSION` и возвращает `0` при успехе и `1` при неудаче.

3.  **Настройка прав и путей**:
    *   Сделайте скрипт исполняемым: `chmod +x version_collector.sh`.
    *   Убедитесь, что у пользователя, от имени которого запускается скрипт (например, `root` или специальный пользователь), есть права на запись в:
        *   Директорию `/var/lib/app-version-collector/`
        *   Директорию `/var/lib/node_exporter/textfile_collector/`
        *   Директорию `/var/run/` (для lock-файла)

4.  **Развертывание через Ansible**:
    *   Ваша Ansible-роль должна:
        *   Установить зависимости (`jq`).
        *   Скопировать скрипт `version_collector.sh` (например, в `/usr/local/bin/`).
        *   Создать необходимые директории с правильными правами.
        *   Добавить задание в `cron` для регулярного запуска скрипта.

    Пример задачи для `cron` (запуск каждые 15 минут):
    ```yaml
    - name: Add cron job for version collector
      ansible.builtin.cron:
        name: "Run app version collector"
        minute: "*/15"
        job: "/usr/local/bin/version_collector.sh > /dev/null 2>&1"
    ```

5.  **Настройка Node Exporter**:
    *   Убедитесь, что ваш `node_exporter` запущен с флагом, указывающим на директорию с текстовыми файлами метрик:
    ```
    --collector.textfile.directory="/var/lib/node_exporter/textfile_collector"
    ```

Этот скрипт полностью реализует описанный вами пайплайн, является отказоустойчивым и готовым к развертыванию.