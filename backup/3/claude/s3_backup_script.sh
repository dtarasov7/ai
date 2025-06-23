#!/bin/bash

# S3 Backup Script for Ceph 17.2.7 and rclone v1.65.2
# Запускается каждые 30 минут по cron

set -euo pipefail

# Конфигурация
RCLONE_REMOTE="s3:"  # Имя remote в rclone config
BACKUP_BASE_DIR="/backup"  # Базовый каталог для бэкапов
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="${SCRIPT_DIR}/s3-backup.lock"
TIMESTAMP_FILE="${SCRIPT_DIR}/last_backup_time"

# Функция логирования
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$$] $*" | tee -a "$LOG_FILE"
}

# Функция для записи метрик Prometheus
write_metrics() {
    local metrics_file="$1"
    local timestamp_label="$2"
    local copied_count="$3"
    local deleted_count="$4"
    local copy_duration="$5"
    local script_duration="$6"
    local total_size="$7"
    local success_flag="$8"
    shift 8
    local errors=("$@")

    cat > "$metrics_file" << EOF
# HELP s3_backup_copied_objects_total Total number of copied objects
# TYPE s3_backup_copied_objects_total counter
s3_backup_copied_objects_total{run_time="$timestamp_label"} $copied_count

# HELP s3_backup_deleted_objects_total Total number of deleted objects detected
# TYPE s3_backup_deleted_objects_total counter
s3_backup_deleted_objects_total{run_time="$timestamp_label"} $deleted_count

# HELP s3_backup_copy_duration_seconds Time spent copying data
# TYPE s3_backup_copy_duration_seconds gauge
s3_backup_copy_duration_seconds{run_time="$timestamp_label"} $copy_duration

# HELP s3_backup_script_duration_seconds Total script execution time
# TYPE s3_backup_script_duration_seconds gauge
s3_backup_script_duration_seconds{run_time="$timestamp_label"} $script_duration

# HELP s3_backup_copied_bytes_total Total bytes copied
# TYPE s3_backup_copied_bytes_total counter
s3_backup_copied_bytes_total{run_time="$timestamp_label"} $total_size

# HELP s3_backup_success Script execution success flag
# TYPE s3_backup_success gauge
s3_backup_success{run_time="$timestamp_label"} $success_flag

EOF

    # Добавляем метрики ошибок
    local error_index=0
    for error in "${errors[@]}"; do
        if [[ -n "$error" ]]; then
            cat >> "$metrics_file" << EOF
# HELP s3_backup_error Error occurred during backup
# TYPE s3_backup_error gauge
s3_backup_error{run_time="$timestamp_label",error="$error",error_id="$error_index"} 1

EOF
            ((error_index++))
        fi
    done
}

# Функция получения текущего бакета
get_current_bucket() {
    local year=$(date +%Y)
    local month=$(date +%m)
    local day=$(date +%d)
    
    local decade
    if (( day >= 1 && day <= 10 )); then
        decade=0
    elif (( day >= 11 && day <= 20 )); then
        decade=1
    else
        decade=2
    fi
    
    echo "storage-${year}${month}${decade}"
}

# Функция получения списка объектов
get_object_list() {
    local bucket="$1"
    local output_file="$2"
    
    rclone lsjson --recursive "${RCLONE_REMOTE}${bucket}" > "$output_file" 2>/dev/null || {
        echo "[]" > "$output_file"
        return 1
    }
}

# Функция сравнения списков для поиска удаленных объектов
find_deleted_objects() {
    local old_list="$1"
    local new_list="$2"
    local deleted_list="$3"
    
    # Используем jq для сравнения списков объектов
    if command -v jq &> /dev/null; then
        jq -r --slurpfile new "$new_list" '
            map(.Path) - ($new[0] | map(.Path)) | .[]
        ' "$old_list" > "$deleted_list" 2>/dev/null || touch "$deleted_list"
    else
        # Fallback без jq
        grep -o '"Path":"[^"]*"' "$old_list" 2>/dev/null | cut -d'"' -f4 | sort > "${deleted_list}.old" || touch "${deleted_list}.old"
        grep -o '"Path":"[^"]*"' "$new_list" 2>/dev/null | cut -d'"' -f4 | sort > "${deleted_list}.new" || touch "${deleted_list}.new"
        comm -23 "${deleted_list}.old" "${deleted_list}.new" > "$deleted_list" || touch "$deleted_list"
        rm -f "${deleted_list}.old" "${deleted_list}.new"
    fi
}

# Основная функция
main() {
    local script_start_time=$(date +%s)
    local current_time=$(date '+%d-%H-%M')
    local current_bucket
    
    # Проверка lock файла
    if [[ -f "$LOCK_FILE" ]]; then
        local lock_pid
        lock_pid=$(<"$LOCK_FILE")
        if kill -0 "$lock_pid" 2>/dev/null; then
            echo "Script is already running (PID: $lock_pid)"
            exit 1
        else
            rm -f "$LOCK_FILE"
        fi
    fi
    
    # Создание lock файла
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"; exit' INT TERM EXIT
    
    # Определение текущего бакета
    current_bucket=$(get_current_bucket)
    
    # Создание структуры каталогов
    local backup_dir="${BACKUP_BASE_DIR}/${current_bucket}-backup"
    local current_backup_dir="${backup_dir}/${current_time}"
    local deleted_dir="${backup_dir}/${current_time}-deleted"
    
    mkdir -p "$backup_dir" "$current_backup_dir" "$deleted_dir"
    
    # Настройка логирования
    LOG_FILE="${backup_dir}/backup.log"
    local rclone_log="${backup_dir}/rclone-${current_time}.log"
    local metrics_file="${backup_dir}/metrics-${current_time}.txt"
    local object_list_current="${backup_dir}/objects-${current_time}.json"
    local object_list_previous="${backup_dir}/objects-previous.json"
    local deleted_objects_file="${deleted_dir}/deleted-objects.txt"
    
    log "=== S3 Backup Script Started ==="
    log "Current bucket: $current_bucket"
    log "Backup directory: $current_backup_dir"
    
    # Инициализация переменных для метрик
    local copied_count=0
    local deleted_count=0
    local copy_duration=0
    local total_size=0
    local success_flag=0
    local errors=()
    
    # Получение времени последнего запуска
    local last_backup_time=""
    if [[ -f "$TIMESTAMP_FILE" ]]; then
        last_backup_time=$(<"$TIMESTAMP_FILE")
        log "Last backup time: $last_backup_time"
    else
        log "First run - no previous timestamp"
    fi
    
    # Сохранение времени текущего запуска
    date '+%Y-%m-%d %H:%M:%S' > "$TIMESTAMP_FILE"
    
    # Получение списка объектов
    log "Getting current object list..."
    if ! get_object_list "$current_bucket" "$object_list_current"; then
        log "ERROR: Failed to get object list"
        errors+=("failed_to_get_object_list")
    fi
    
    # Поиск удаленных объектов
    if [[ -f "$object_list_previous" ]]; then
        log "Finding deleted objects..."
        find_deleted_objects "$object_list_previous" "$object_list_current" "$deleted_objects_file"
        deleted_count=$(wc -l < "$deleted_objects_file" 2>/dev/null || echo 0)
        log "Found $deleted_count deleted objects"
    fi
    
    # Копирование измененных объектов
    log "Starting incremental backup..."
    local copy_start_time=$(date +%s)
    
    # Настройки rclone для максимальной производительности
    local rclone_opts=(
        --config "$HOME/.config/rclone/rclone.conf"
        --log-file "$rclone_log"
        --log-level INFO
        --stats 1m
        --stats-one-line
        --transfers 32
        --checkers 16
        --buffer-size 256M
        --s3-chunk-size 64M
        --s3-upload-concurrency 16
        --use-json-log
    )
    
    # Определение фильтра по времени
    if [[ -n "$last_backup_time" ]]; then
        # Копируем файлы, измененные с последнего запуска
        rclone_opts+=(--max-age "${last_backup_time}")
    fi
    
    if rclone copy "${RCLONE_REMOTE}${current_bucket}" "$current_backup_dir" "${rclone_opts[@]}" 2>&1; then
        local copy_end_time=$(date +%s)
        copy_duration=$((copy_end_time - copy_start_time))
        log "Backup completed successfully in ${copy_duration} seconds"
        
        # Подсчет скопированных файлов и размера
        if [[ -f "$rclone_log" ]]; then
            copied_count=$(grep -c "INFO.*Copied" "$rclone_log" 2>/dev/null || echo 0)
            # Извлечение размера из лога (приблизительно)
            total_size=$(grep "Transferred:" "$rclone_log" | tail -1 | grep -o '[0-9,]\+ *Bytes' | tr -d ', ' | cut -d' ' -f1 || echo 0)
        fi
        
        success_flag=1
    else
        local copy_end_time=$(date +%s)
        copy_duration=$((copy_end_time - copy_start_time))
        log "ERROR: Backup failed"
        errors+=("backup_copy_failed")
    fi
    
    log "Copied objects: $copied_count"
    log "Total size: $total_size bytes"
    
    # Сохранение текущего списка объектов как предыдущего для следующего запуска
    cp "$object_list_current" "$object_list_previous" 2>/dev/null || true
    
    # Подсчет общего времени выполнения
    local script_end_time=$(date +%s)
    local script_duration=$((script_end_time - script_start_time))
    
    log "=== Backup completed in ${script_duration} seconds ==="
    
    # Запись метрик
    write_metrics "$metrics_file" "$current_time" "$copied_count" "$deleted_count" \
                  "$copy_duration" "$script_duration" "$total_size" "$success_flag" "${errors[@]}"
    
    log "Metrics written to: $metrics_file"
}

# Проверка зависимостей
check_dependencies() {
    local deps=("rclone" "date" "mkdir" "tee")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            echo "ERROR: Required command '$dep' not found"
            exit 1
        fi
    done
    
    # Проверка конфигурации rclone
    if ! rclone listremotes | grep -q "^s3:$"; then
        echo "ERROR: rclone remote 's3:' not configured"
        exit 1
    fi
}

# Запуск скрипта
check_dependencies
main "$@"