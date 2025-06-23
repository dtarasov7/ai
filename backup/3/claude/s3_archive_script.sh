#!/bin/bash

# S3 Archive Script for Ceph 17.2.7 and rclone v1.65.2
# Запускается в начале каждой декады для архивации предыдущего бакета

set -euo pipefail

# Конфигурация
RCLONE_REMOTE="s3:"  # Имя remote в rclone config
ARCHIVE_BASE_DIR="/archive"  # Базовый каталог для архивов
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="${SCRIPT_DIR}/s3-archive.lock"
BACKUP_BASE_DIR="/backup"  # Базовый каталог для бэкапов (общий лог)

# Функция логирования
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ARCHIVE-$$] $*" | tee -a "$LOG_FILE"
}

# Функция для записи метрик Prometheus
write_metrics() {
    local metrics_file="$1"
    local timestamp_label="$2"
    local copied_count="$3"
    local copy_duration="$4"
    local script_duration="$5"
    local total_size="$6"
    local success_flag="$7"
    shift 7
    local errors=("$@")

    cat > "$metrics_file" << EOF
# HELP s3_archive_copied_objects_total Total number of archived objects
# TYPE s3_archive_copied_objects_total counter
s3_archive_copied_objects_total{run_time="$timestamp_label"} $copied_count

# HELP s3_archive_copy_duration_seconds Time spent copying data
# TYPE s3_archive_copy_duration_seconds gauge
s3_archive_copy_duration_seconds{run_time="$timestamp_label"} $copy_duration

# HELP s3_archive_script_duration_seconds Total script execution time
# TYPE s3_archive_script_duration_seconds gauge
s3_archive_script_duration_seconds{run_time="$timestamp_label"} $script_duration

# HELP s3_archive_copied_bytes_total Total bytes archived
# TYPE s3_archive_copied_bytes_total counter
s3_archive_copied_bytes_total{run_time="$timestamp_label"} $total_size

# HELP s3_archive_success Script execution success flag
# TYPE s3_archive_success gauge
s3_archive_success{run_time="$timestamp_label"} $success_flag

# HELP s3_archive_average_speed_bytes_per_second Average transfer speed
# TYPE s3_archive_average_speed_bytes_per_second gauge
s3_archive_average_speed_bytes_per_second{run_time="$timestamp_label"} $(( copy_duration > 0 ? total_size / copy_duration : 0 ))

EOF

    # Добавляем метрики ошибок
    local error_index=0
    for error in "${errors[@]}"; do
        if [[ -n "$error" ]]; then
            cat >> "$metrics_file" << EOF
# HELP s3_archive_error Error occurred during archiving
# TYPE s3_archive_error gauge
s3_archive_error{run_time="$timestamp_label",error="$error",error_id="$error_index"} 1

EOF
            ((error_index++))
        fi
    done
}

# Функция получения предыдущего бакета
get_previous_bucket() {
    local year=$(date +%Y)
    local month=$(date +%m)
    local day=$(date +%d)
    
    local decade
    local prev_decade
    local prev_year="$year"
    local prev_month="$month"
    
    if (( day >= 1 && day <= 10 )); then
        decade=0
        # Предыдущая декада - 2 декада предыдущего месяца
        prev_decade=2
        if (( month == 1 )); then
            prev_month=12
            prev_year=$((year - 1))
        else
            prev_month=$((month - 1))
        fi
    elif (( day >= 11 && day <= 20 )); then
        decade=1
        prev_decade=0
    else
        decade=2
        prev_decade=1
    fi
    
    printf "storage-%04d%02d%d" "$prev_year" "$prev_month" "$prev_decade"
}

# Функция получения размера бакета
get_bucket_size() {
    local bucket="$1"
    rclone size "${RCLONE_REMOTE}${bucket}" --json 2>/dev/null | \
        grep -o '"bytes":[0-9]*' | cut -d':' -f2 || echo 0
}

# Функция получения количества объектов
get_object_count() {
    local bucket="$1"
    rclone lsjson --recursive "${RCLONE_REMOTE}${bucket}" 2>/dev/null | \
        grep -c '"Path"' || echo 0
}

# Основная функция
main() {
    local script_start_time=$(date +%s)
    local current_time=$(date '+%d-%H-%M')
    local previous_bucket
    
    # Проверка lock файла
    if [[ -f "$LOCK_FILE" ]]; then
        local lock_pid
        lock_pid=$(<"$LOCK_FILE")
        if kill -0 "$lock_pid" 2>/dev/null; then
            echo "Archive script is already running (PID: $lock_pid)"
            exit 1
        else
            rm -f "$LOCK_FILE"
        fi
    fi
    
    # Создание lock файла
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"; exit' INT TERM EXIT
    
    # Определение предыдущего бакета
    previous_bucket=$(get_previous_bucket)
    
    # Создание структуры каталогов
    local archive_dir="${ARCHIVE_BASE_DIR}/${previous_bucket}"
    mkdir -p "$archive_dir"
    
    # Определение каталога для общего лога
    local current_bucket_backup="${BACKUP_BASE_DIR}/$(get_current_bucket)-backup"
    mkdir -p "$current_bucket_backup"
    
    # Настройка логирования (общий лог с backup скриптом)
    LOG_FILE="${current_bucket_backup}/backup.log"
    local rclone_log="${archive_dir}/rclone-archive-${current_time}.log"
    local metrics_file="${archive_dir}/archive-metrics-${current_time}.txt"
    
    log "=== S3 Archive Script Started ==="
    log "Previous bucket: $previous_bucket"
    log "Archive directory: $archive_dir"
    
    # Проверка существования бакета
    if ! rclone lsd "${RCLONE_REMOTE}" | grep -q "$previous_bucket"; then
        log "WARNING: Bucket $previous_bucket does not exist, skipping archive"
        # Создаем метрики с нулевыми значениями
        write_metrics "$metrics_file" "$current_time" 0 0 0 0 1
        exit 0
    fi
    
    # Инициализация переменных для метрик
    local copied_count=0
    local copy_duration=0
    local total_size=0
    local success_flag=0
    local errors=()
    
    # Получение информации о бакете до начала копирования
    log "Getting bucket information..."
    total_size=$(get_bucket_size "$previous_bucket")
    copied_count=$(get_object_count "$previous_bucket")
    
    log "Bucket size: $total_size bytes"
    log "Object count: $copied_count"
    
    # Проверка свободного места (опционально)
    local available_space
    available_space=$(df "$ARCHIVE_BASE_DIR" | awk 'NR==2 {print $4}')
    local available_bytes=$((available_space * 1024))
    
    if (( total_size > available_bytes )); then
        log "ERROR: Not enough free space. Required: $total_size, Available: $available_bytes"
        errors+=("insufficient_disk_space")
        write_metrics "$metrics_file" "$current_time" 0 0 0 0 0 "${errors[@]}"
        exit 1
    fi
    
    # Копирование бакета (щадящий режим)
    log "Starting archive sync..."
    local copy_start_time=$(date +%s)
    
    # Настройки rclone для щадящего режима
    local rclone_opts=(
        --config "$HOME/.config/rclone/rclone.conf"
        --log-file "$rclone_log"
        --log-level INFO
        --stats 5m
        --stats-one-line
        --transfers 8
        --checkers 4
        --buffer-size 64M
        --s3-chunk-size 32M
        --s3-upload-concurrency 4
        --use-json-log
        --bwlimit 100M
        --tpslimit 10
    )
    
    if rclone sync "${RCLONE_REMOTE}${previous_bucket}" "$archive_dir" "${rclone_opts[@]}" 2>&1; then
        local copy_end_time=$(date +%s)
        copy_duration=$((copy_end_time - copy_start_time))
        log "Archive completed successfully in ${copy_duration} seconds"
        
        # Верификация архива
        log "Verifying archive..."
        local archive_size
        archive_size=$(du -sb "$archive_dir" | cut -f1)
        local archive_count
        archive_count=$(find "$archive_dir" -type f | wc -l)
        
        log "Archive verification: size=$archive_size bytes, count=$archive_count files"
        
        # Обновляем метрики с реальными значениями
        total_size="$archive_size"
        copied_count="$archive_count"
        success_flag=1
    else
        local copy_end_time=$(date +%s)
        copy_duration=$((copy_end_time - copy_start_time))
        log "ERROR: Archive failed"
        errors+=("archive_sync_failed")
        copied_count=0
        total_size=0
    fi
    
    # Подсчет общего времени выполнения
    local script_end_time=$(date +%s)
    local script_duration=$((script_end_time - script_start_time))
    
    log "=== Archive completed in ${script_duration} seconds ==="
    
    # Запись метрик
    write_metrics "$metrics_file" "$current_time" "$copied_count" "$copy_duration" \
                  "$script_duration" "$total_size" "$success_flag" "${errors[@]}"
    
    log "Archive metrics written to: $metrics_file"
}

# Функция получения текущего бакета (для лога)
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

# Проверка зависимостей
check_dependencies() {
    local deps=("rclone" "date" "mkdir" "tee" "du" "df" "find")
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
    
    # Проверка доступности архивного каталога
    if [[ ! -d "$ARCHIVE_BASE_DIR" ]]; then
        echo "ERROR: Archive directory $ARCHIVE_BASE_DIR does not exist"
        exit 1
    fi
}

# Запуск скрипта
check_dependencies
main "$@"