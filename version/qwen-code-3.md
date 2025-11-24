Вот полный Bash-скрипт, реализующий описанное решение. Он включает:

- Блокировку (lock-file)
- Чтение/запись `state.json`
- Получение версий через `get_app_version`
- Генерацию метрик Prometheus
- Обработку случая "ПО удалено"
- Запись в `.prom` файл атомарно
- Метрики для мониторинга сборщика

---

```bash
#!/bin/bash

# Настройки
STATE_FILE="/var/lib/app_version_collector/state.json"
METRICS_FILE="/var/lib/node_exporter/textfile_collector/app_versions.prom.tmp"
FINAL_METRICS_FILE="/var/lib/node_exporter/textfile_collector/app_versions.prom"
LOCK_FILE="/var/run/app_version_collector.lock"
APP_LIST="nginx openssl postgresql redis mysql php"

# Функция блокировки
acquire_lock() {
    if ! mkdir "$LOCK_FILE" 2>/dev/null; then
        echo "Lock already held by another process. Exiting."
        exit 1
    fi
}

# Функция разблокировки
release_lock() {
    rmdir "$LOCK_FILE" 2>/dev/null
}

# Улучшенная функция кодирования версии
encode_version() {
    local version="$1"
    
    # Удаляем pre-release суффиксы (все после -, +, ~)
    version=$(echo "$version" | sed 's/[-+~].*//')
    
    # Поддержка до 4 компонентов, каждый до 9999
    local IFS='.'
    read -ra parts <<< "$version"
    
    # Дополняем нулями если компонентов меньше 4
    while [ ${#parts[@]} -lt 4 ]; do
        parts+=("0")
    done
    
    # Формула: v1*1000000000000 + v2*100000000 + v3*10000 + v4
    printf "%d%04d%04d%04d" "${parts[0]}" "${parts[1]}" "${parts[2]}" "${parts[3]}"
}

# Функция получения версии ПО (реализация не приведена — должна заполнять VERSION и возвращать 0 или 1)
# Пример вызова: if get_app_version "nginx"; then ... fi
# Предполагается, что функция определена где-то выше или импортируется.

# Инициализация переменных
declare -A apps_state
declare -A app_versions
declare -A app_changes
declare -A app_change_times

# Инициализация метрик
METRICS=""
SUCCESS=1
START_TIME=$(date +%s)

# Получаем имя хоста
NODE_NAME=$(hostname -s)

# Активируем блокировку
acquire_lock
trap release_lock EXIT

# Создаем директорию для метрик, если не существует
mkdir -p "$(dirname "$METRICS_FILE")"

# Читаем state.json, если существует
if [[ -f "$STATE_FILE" ]]; then
    # Используем jq для безопасного чтения JSON
    if command -v jq >/dev/null 2>&1; then
        # Читаем состояние приложений
        if jq -e '.apps' "$STATE_FILE" >/dev/null 2>&1; then
            # Загружаем текущее состояние
            while IFS= read -r line; do
                appname=$(echo "$line" | cut -d'|' -f1)
                current=$(echo "$line" | cut -d'|' -f2)
                previous=$(echo "$line" | cut -d'|' -f3)
                changes_total=$(echo "$line" | cut -d'|' -f4)
                change_time=$(echo "$line" | cut -d'|' -f5)
                apps_state["$appname"]="{\"current\":\"$current\",\"previous\":\"$previous\",\"changes_total\":$changes_total,\"change_time\":$change_time}"
            done < <(jq -r 'to_entries[] | "\(.key)|\(.value.current)|\(.value.previous)|\(.value.changes_total)|\(.value.change_time)"' "$STATE_FILE")
        else
            echo "Invalid state file format. Resetting state."
            > "$STATE_FILE"
        fi
    else
        echo "jq not found. Cannot parse state.json. Skipping state load."
        > "$STATE_FILE"
    fi
fi

# Собираем версии для каждого приложения
for app in $APP_LIST; do
    VERSION=""
    if get_app_version "$app"; then
        # ПО найдено, версия получена
        app_versions["$app"]="$VERSION"
        app_changes["$app"]=0
        app_change_times["$app"]=0
    else
        # ПО не найдено
        app_versions["$app"]="deleted"
        # Если в state.json было записано другое значение — обновляем
        if [[ -n "${apps_state[$app]}" ]]; then
            # Парсим текущее состояние
            current=$(echo "${apps_state[$app]}" | jq -r '.current')
            if [[ "$current" != "deleted" ]]; then
                # Обновляем state: предыдущая = текущая, текущая = deleted
                app_changes["$app"]=1  # флаг изменения
                app_change_times["$app"]=$(date +%s)
            fi
        fi
    fi
done

# Генерируем метрики
for app in $APP_LIST; do
    version_str="${app_versions[$app]}"
    
    # Определяем числовую версию
    if [[ "$version_str" == "deleted" ]]; then
        version_numeric=0
        version_label="deleted"
    else
        version_numeric=$(encode_version "$version_str")
        version_label="$version_str"
    fi

    # Генерируем info-метрику
    METRICS+="# HELP app_version_info Information about the version of an application.\n"
    METRICS+="# TYPE app_version_info gauge\n"
    METRICS+="app_version_info{nodename=\"$NODE_NAME\",appname=\"$app\",version=\"$version_label\"} 1\n"

    # Генерируем numeric-метрику
    METRICS+="# HELP app_version_numeric Numeric representation of application version for comparisons.\n"
    METRICS+="# TYPE app_version_numeric gauge\n"
    METRICS+="app_version_numeric{nodename=\"$NODE_NAME\",appname=\"$app\"} $version_numeric\n"

    # Генерируем метрику времени последнего изменения
    # Если есть изменение — обновляем время
    change_flag=0
    if [[ -n "${apps_state[$app]}" ]]; then
        current=$(echo "${apps_state[$app]}" | jq -r '.current')
        if [[ "$current" != "$version_str" ]]; then
            change_flag=1
        fi
    fi

    # Если произошло изменение (или это первое сканирование), обновляем время
    if [[ $change_flag -eq 1 ]] || [[ -z "${apps_state[$app]}" ]]; then
        change_time=$(date +%s)
    else
        # Берем из state
        change_time=$(echo "${apps_state[$app]}" | jq -r '.change_time')
    fi

    METRICS+="# HELP app_version_change_time_seconds Unix timestamp of the last version change.\n"
    METRICS+="# TYPE app_version_change_time_seconds gauge\n"
    METRICS+="app_version_change_time_seconds{nodename=\"$NODE_NAME\",appname=\"$app\"} $change_time\n"
done

# Добавляем метрики сборщика
METRICS+="# HELP app_version_scrape_timestamp_seconds Timestamp of the last successful scrape.\n"
METRICS+="# TYPE app_version_scrape_timestamp_seconds gauge\n"
METRICS+="app_version_scrape_timestamp_seconds{instance=\"$NODE_NAME\"} $(date +%s)\n"

METRICS+="# HELP app_version_collector_success Whether the collector succeeded (1 = success, 0 = failure).\n"
METRICS+="# TYPE app_version_collector_success gauge\n"
METRICS+="app_version_collector_success{instance=\"$NODE_NAME\"} $SUCCESS\n"

METRICS+="# HELP app_version_collector_duration_seconds Duration of the collector execution in seconds.\n"
METRICS+="# TYPE app_version_collector_duration_seconds gauge\n"
METRICS+="app_version_collector_duration_seconds{instance=\"$NODE_NAME\"} $(( $(date +%s) - START_TIME ))\n"

# Записываем метрики в временный файл
echo -n "$METRICS" > "$METRICS_FILE"

# Атомарно перемещаем файл
mv "$METRICS_FILE" "$FINAL_METRICS_FILE"

# Обновляем state.json
# Сначала создаем новое состояние
new_state='{"apps": {'
first=true

for app in $APP_LIST; do
    version_str="${app_versions[$app]}"
    change_flag=0

    # Проверяем, нужно ли обновить state
    if [[ -n "${apps_state[$app]}" ]]; then
        current=$(echo "${apps_state[$app]}" | jq -r '.current')
        if [[ "$current" != "$version_str" ]]; then
            change_flag=1
        fi
    fi

    # Если нет состояния — создаем новое
    if [[ -z "${apps_state[$app]}" ]]; then
        changes_total=0
        previous=""
        change_time=0
    else
        changes_total=$(echo "${apps_state[$app]}" | jq -r '.changes_total')
        previous=$(echo "${apps_state[$app]}" | jq -r '.previous')
        change_time=$(echo "${apps_state[$app]}" | jq -r '.change_time')
    fi

    # Если произошло изменение — обновляем счетчик и время
    if [[ $change_flag -eq 1 ]]; then
        changes_total=$((changes_total + 1))
        previous="$current"
        change_time=$(date +%s)
    fi

    # Формируем JSON для приложения
    app_json="{\"current\":\"$version_str\",\"previous\":\"$previous\",\"changes_total\":$changes_total,\"change_time\":$change_time}"

    if [[ $first == true ]]; then
        first=false
    else
        new_state+=", "
    fi
    new_state+="\"$app\": $app_json"
done

new_state+="}}"

# Записываем новое состояние
echo "$new_state" > "$STATE_FILE"

# Логируем успешное завершение
echo "App version collection completed successfully at $(date)."

exit 0
```

---

### 🔧 Важные замечания:

1. **Требуется `jq`** — для парсинга и генерации JSON. Установите его:
   ```bash
   apt install jq   # Debian/Ubuntu
   yum install jq   # CentOS/RHEL
   ```

2. **Функция `get_app_version`** — должна быть определена в скрипте или sourced. Пример:
   ```bash
   get_app_version() {
       local app="$1"
       case "$app" in
           nginx)
               if command -v nginx >/dev/null; then
                   VERSION=$(nginx -v 2>&1 | awk '{print $3}' | sed 's/;//')
                   return 1
               fi
               ;;
           openssl)
               if command -v openssl >/dev/null; then
                   VERSION=$(openssl version | awk '{print $2}')
                   return 1
               fi
               ;;
           *)
               echo "Unknown app: $app"
               return 0
               ;;
       esac
       return 0
   }
   ```

3. **Права доступа**: Убедитесь, что скрипт может писать в `/var/lib/node_exporter/textfile_collector/` и `/var/lib/app_version_collector/`.

4. **Cron**: Добавьте в crontab:
   ```bash
   0 * * * * /path/to/your/script.sh
   ```

5. **Алерты и дашборды Grafana** — как описано в задании — работают с этими метриками.

---

Этот скрипт полностью соответствует вашей спецификации: блокировка, state-менеджмент, кодирование версий, обработка удалений, мониторинг сборщика и атомарная запись метрик.