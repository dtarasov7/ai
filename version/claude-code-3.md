Подготовлю полный bash-скрипт для мониторинга версий ПО с учётом всех требований:Я подготовил полный bash-скрипт для мониторинга версий ПО с учётом всех требований. Вот ключевые особенности реализации:

## Основные возможности

**1. Механизм блокировки**
- Использует `flock` для предотвращения параллельных запусков
- Настраиваемый timeout (по умолчанию 300 секунд)
- Автоматическое освобождение при завершении через trap

**2. Управление состоянием**
- Парсинг и генерация JSON без внешних зависимостей (jq)
- Ассоциативный массив для хранения данных в памяти
- Атомарная запись через временные файлы

**3. Обработка версий**
- Функция `encode_version` с поддержкой до 4 компонентов
- Обработка префиксов (например, "nginx/1.25")
- Удаление pre-release суффиксов (-rc1, +build, ~dev)

**4. Генерация метрик**
- Все требуемые метрики с правильными типами и HELP-текстами
- Обработка случая "deleted" (версия=0, метка version="deleted")
- Атомарная запись метрик

## Настройка через переменные окружения

```bash
export NODENAME="srv-1"
export APP_LIST="nginx openssl postgresql redis"
export STATE_FILE="/var/lib/app-version-collector/state.json"
export METRICS_FILE="/var/lib/node_exporter/textfile_collector/app_version.prom"
```

## Интеграция функции get_app_version

Добавьте в скрипт перед функцией `main()`:

```bash
get_app_version() {
    local app="$1"
    VERSION=""
    
    case "$app" in
        nginx)
            if command -v nginx &>/dev/null; then
                VERSION=$(nginx -v 2>&1 | grep -oP '\d+\.\d+\.\d+')
                [ -n "$VERSION" ] && return 1
            fi
            ;;
        openssl)
            if command -v openssl &>/dev/null; then
                VERSION=$(openssl version | awk '{print $2}')
                [ -n "$VERSION" ] && return 1
            fi
            ;;
        # ... другие приложения
    esac
    
    return 0
}
```

## Установка через Ansible

```yaml
- name: Deploy app version collector
  template:
    src: app_version_collector.sh.j2
    dest: /usr/local/bin/app_version_collector.sh
    mode: '0755'

- name: Create directories
  file:
    path: "{{ item }}"
    state: directory
  loop:
    - /var/lib/app-version-collector
    - /var/lib/node_exporter/textfile_collector

- name: Setup cron job
  cron:
    name: "App version collector"
    minute: "0"
    job: "/usr/local/bin/app_version_collector.sh >> /var/log/app-version-collector.log 2>&1"
```

Скрипт готов к использованию! 🚀



#!/bin/bash
#
# App Version Collector for Prometheus
# Collects software versions and generates Prometheus metrics
#

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

# Node name (hostname by default)
NODENAME="${NODENAME:-$(hostname -s)}"

# Paths
STATE_FILE="${STATE_FILE:-/var/lib/app-version-collector/state.json}"
METRICS_FILE="${METRICS_FILE:-/var/lib/node_exporter/textfile_collector/app_version.prom}"
LOCK_FILE="${LOCK_FILE:-/var/run/app-version-collector.lock}"

# List of applications to monitor (space-separated)
APP_LIST="${APP_LIST:-nginx openssl}"

# Lock timeout (seconds)
LOCK_TIMEOUT=300

# =============================================================================
# Global variables
# =============================================================================

VERSION=""
SCRIPT_START_TIME=$(date +%s)
COLLECTOR_SUCCESS=1
DECLARE -A APP_DATA

# =============================================================================
# Functions
# =============================================================================

# Logging
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" >&2
}

error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

# Acquire lock
acquire_lock() {
    local lock_fd=200
    local waited=0
    
    eval "exec 200>\"$LOCK_FILE\""
    
    while ! flock -n 200; do
        if [ $waited -ge $LOCK_TIMEOUT ]; then
            error "Failed to acquire lock after ${LOCK_TIMEOUT}s"
            return 1
        fi
        log "Waiting for lock..."
        sleep 5
        waited=$((waited + 5))
    done
    
    echo $$ >&200
    log "Lock acquired"
    return 0
}

# Release lock
release_lock() {
    if [ -f "$LOCK_FILE" ]; then
        rm -f "$LOCK_FILE"
        log "Lock released"
    fi
}

# Trap to ensure cleanup
cleanup() {
    release_lock
}

trap cleanup EXIT INT TERM

# Encode version to numeric format
encode_version() {
    local version="$1"
    
    # Remove pre-release suffixes (everything after -, +, ~)
    version=$(echo "$version" | sed 's/[-+~].*//')
    
    # Remove non-numeric prefixes (e.g., "nginx/1.25" -> "1.25")
    version=$(echo "$version" | sed 's/^[^0-9]*//')
    
    # Support up to 4 components, each up to 9999
    local IFS='.'
    read -ra parts <<< "$version"
    
    # Pad with zeros if less than 4 components
    while [ ${#parts[@]} -lt 4 ]; do
        parts+=("0")
    done
    
    # Ensure all parts are numeric and within range
    for i in "${!parts[@]}"; do
        if ! [[ "${parts[$i]}" =~ ^[0-9]+$ ]]; then
            parts[$i]=0
        fi
        if [ "${parts[$i]}" -gt 9999 ]; then
            parts[$i]=9999
        fi
    done
    
    # Formula: v1*1000000000000 + v2*100000000 + v3*10000 + v4
    printf "%d%04d%04d%04d" "${parts[0]}" "${parts[1]}" "${parts[2]}" "${parts[3]}"
}

# Load state from JSON
load_state() {
    if [ -f "$STATE_FILE" ]; then
        log "Loading state from $STATE_FILE"
        
        # Read JSON and populate APP_DATA associative array
        while IFS= read -r line; do
            if [[ $line =~ \"([^\"]+)\":\ *\{ ]]; then
                local app="${BASH_REMATCH[1]}"
                local current="" previous="" changes_total=0 change_time=0
                
                # Read app data
                while IFS= read -r data_line; do
                    [[ $data_line =~ \} ]] && break
                    
                    if [[ $data_line =~ \"current\":\ *\"([^\"]*)\" ]]; then
                        current="${BASH_REMATCH[1]}"
                    elif [[ $data_line =~ \"previous\":\ *\"([^\"]*)\" ]]; then
                        previous="${BASH_REMATCH[1]}"
                    elif [[ $data_line =~ \"changes_total\":\ *([0-9]+) ]]; then
                        changes_total="${BASH_REMATCH[1]}"
                    elif [[ $data_line =~ \"change_time\":\ *([0-9]+) ]]; then
                        change_time="${BASH_REMATCH[1]}"
                    fi
                done
                
                APP_DATA["${app}_current"]="$current"
                APP_DATA["${app}_previous"]="$previous"
                APP_DATA["${app}_changes_total"]="$changes_total"
                APP_DATA["${app}_change_time"]="$change_time"
            fi
        done < "$STATE_FILE"
    else
        log "State file not found, starting fresh"
    fi
}

# Save state to JSON
save_state() {
    local state_dir=$(dirname "$STATE_FILE")
    local temp_file="${STATE_FILE}.tmp"
    
    mkdir -p "$state_dir"
    
    cat > "$temp_file" << 'EOF'
{
  "apps": {
EOF
    
    local first=true
    for app in $APP_LIST; do
        local current="${APP_DATA[${app}_current]:-}"
        local previous="${APP_DATA[${app}_previous]:-}"
        local changes_total="${APP_DATA[${app}_changes_total]:-0}"
        local change_time="${APP_DATA[${app}_change_time]:-0}"
        
        # Skip if app has no data
        [ -z "$current" ] && continue
        
        if [ "$first" = true ]; then
            first=false
        else
            echo "," >> "$temp_file"
        fi
        
        cat >> "$temp_file" << EOF
    "$app": {
      "current": "$current",
      "previous": "$previous",
      "changes_total": $changes_total,
      "change_time": $change_time
    }
EOF
    done
    
    cat >> "$temp_file" << 'EOF'

  }
}
EOF
    
    # Atomic move
    mv "$temp_file" "$STATE_FILE"
    log "State saved to $STATE_FILE"
}

# Process application version
process_app() {
    local app="$1"
    local old_current="${APP_DATA[${app}_current]:-}"
    local old_previous="${APP_DATA[${app}_previous]:-}"
    local old_changes="${APP_DATA[${app}_changes_total]:-0}"
    local old_change_time="${APP_DATA[${app}_change_time]:-0}"
    
    VERSION=""
    
    # Get version (this function should be defined elsewhere)
    if get_app_version "$app"; then
        # App found, version in $VERSION
        log "App '$app': version $VERSION detected"
        
        if [ -z "$old_current" ] || [ "$old_current" = "deleted" ]; then
            # New installation or reinstallation
            log "App '$app': new installation detected"
            APP_DATA["${app}_current"]="$VERSION"
            APP_DATA["${app}_previous"]=""
            APP_DATA["${app}_changes_total"]="$((old_changes + 1))"
            APP_DATA["${app}_change_time"]="$SCRIPT_START_TIME"
        elif [ "$VERSION" != "$old_current" ]; then
            # Version changed
            log "App '$app': version changed from $old_current to $VERSION"
            APP_DATA["${app}_current"]="$VERSION"
            APP_DATA["${app}_previous"]="$old_current"
            APP_DATA["${app}_changes_total"]="$((old_changes + 1))"
            APP_DATA["${app}_change_time"]="$SCRIPT_START_TIME"
        else
            # Version unchanged
            APP_DATA["${app}_current"]="$VERSION"
            APP_DATA["${app}_previous"]="$old_previous"
            APP_DATA["${app}_changes_total"]="$old_changes"
            APP_DATA["${app}_change_time"]="$old_change_time"
        fi
    else
        # App not found
        if [ -n "$old_current" ]; then
            # App was present before but now deleted
            log "App '$app': not found (deleted)"
            
            if [ "$old_current" != "deleted" ]; then
                # Mark as deleted
                APP_DATA["${app}_current"]="deleted"
                APP_DATA["${app}_previous"]="$old_current"
                APP_DATA["${app}_changes_total"]="$((old_changes + 1))"
                APP_DATA["${app}_change_time"]="$SCRIPT_START_TIME"
            else
                # Already marked as deleted
                APP_DATA["${app}_current"]="deleted"
                APP_DATA["${app}_previous"]="$old_previous"
                APP_DATA["${app}_changes_total"]="$old_changes"
                APP_DATA["${app}_change_time"]="$old_change_time"
            fi
        else
            # App was never present, skip
            log "App '$app': not found (never installed)"
            return 0
        fi
    fi
}

# Generate Prometheus metrics
generate_metrics() {
    local metrics_dir=$(dirname "$METRICS_FILE")
    local temp_file="${METRICS_FILE}.tmp"
    
    mkdir -p "$metrics_dir"
    
    cat > "$temp_file" << EOF
# HELP app_version_info Application version information (version in label)
# TYPE app_version_info gauge
EOF
    
    for app in $APP_LIST; do
        local current="${APP_DATA[${app}_current]:-}"
        [ -z "$current" ] && continue
        
        echo "app_version_info{nodename=\"$NODENAME\",appname=\"$app\",version=\"$current\"} 1" >> "$temp_file"
    done
    
    cat >> "$temp_file" << EOF

# HELP app_version_numeric Application version as numeric value
# TYPE app_version_numeric gauge
EOF
    
    for app in $APP_LIST; do
        local current="${APP_DATA[${app}_current]:-}"
        [ -z "$current" ] && continue
        
        if [ "$current" = "deleted" ]; then
            echo "app_version_numeric{nodename=\"$NODENAME\",appname=\"$app\"} 0" >> "$temp_file"
        else
            local numeric=$(encode_version "$current")
            echo "app_version_numeric{nodename=\"$NODENAME\",appname=\"$app\"} $numeric" >> "$temp_file"
        fi
    done
    
    cat >> "$temp_file" << EOF

# HELP app_version_change_time_seconds Unix timestamp of last version change
# TYPE app_version_change_time_seconds gauge
EOF
    
    for app in $APP_LIST; do
        local current="${APP_DATA[${app}_current]:-}"
        local change_time="${APP_DATA[${app}_change_time]:-0}"
        [ -z "$current" ] && continue
        
        echo "app_version_change_time_seconds{nodename=\"$NODENAME\",appname=\"$app\"} $change_time" >> "$temp_file"
    done
    
    cat >> "$temp_file" << EOF

# HELP app_version_scrape_timestamp_seconds Unix timestamp of the scrape
# TYPE app_version_scrape_timestamp_seconds gauge
EOF
    
    for app in $APP_LIST; do
        local current="${APP_DATA[${app}_current]:-}"
        [ -z "$current" ] && continue
        
        echo "app_version_scrape_timestamp_seconds{nodename=\"$NODENAME\",appname=\"$app\"} $SCRIPT_START_TIME" >> "$temp_file"
    done
    
    local script_duration=$(($(date +%s) - SCRIPT_START_TIME))
    
    cat >> "$temp_file" << EOF

# HELP app_version_collector_success Whether the collector succeeded (1=success, 0=failure)
# TYPE app_version_collector_success gauge
app_version_collector_success{nodename="$NODENAME"} $COLLECTOR_SUCCESS

# HELP app_version_collector_duration_seconds Duration of the collection in seconds
# TYPE app_version_collector_duration_seconds gauge
app_version_collector_duration_seconds{nodename="$NODENAME"} $script_duration
EOF
    
    # Atomic move
    mv "$temp_file" "$METRICS_FILE"
    log "Metrics written to $METRICS_FILE"
}

# =============================================================================
# Main execution
# =============================================================================

main() {
    log "=== App Version Collector started ==="
    
    # Acquire lock
    if ! acquire_lock; then
        COLLECTOR_SUCCESS=0
        error "Failed to acquire lock, exiting"
        exit 1
    fi
    
    # Load previous state
    load_state
    
    # Process each application
    for app in $APP_LIST; do
        if ! process_app "$app"; then
            error "Failed to process app: $app"
            COLLECTOR_SUCCESS=0
        fi
    done
    
    # Save state
    save_state
    
    # Generate metrics
    generate_metrics
    
    log "=== App Version Collector finished successfully ==="
}

# Run main function
main "$@"
