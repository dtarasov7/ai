#!/bin/bash

# S3 Backup Monitoring Script
# Проверяет состояние системы резервного копирования и генерирует отчеты

set -euo pipefail

# Конфигурация
BACKUP_BASE_DIR="/backup"
ARCHIVE_BASE_DIR="/archive"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="${SCRIPT_DIR}/reports"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция вывода с цветом
print_status() {
    local status="$1"
    local message="$2"
    local color
    
    case "$status" in
        "OK") color="$GREEN" ;;
        "WARNING") color="$YELLOW" ;;
        "ERROR") color="$RED" ;;
        "INFO") color="$BLUE" ;;
        *) color="$NC" ;;
    esac
    
    echo -e "[${color}${status}${NC}] $message"
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

# Проверка состояния lock файлов
check_lock_files() {
    print_status "INFO" "Checking lock files..."
    
    local backup_lock="${SCRIPT_DIR}/s3-backup.lock"
    local archive_lock="${SCRIPT_DIR}/s3-archive.lock"
    
    if [[ -f "$backup_lock" ]]; then
        local backup_pid=$(<"$backup_lock")
        if kill -0 "$backup_pid" 2>/dev/null; then
            print_status "INFO" "Backup script is running (PID: $backup_pid)"
        else
            print_status "WARNING" "Stale backup lock file found (PID: $backup_pid)"
        fi
    else
        print_status "OK" "No backup lock file"
    fi
    
    if [[ -f "$archive_lock" ]]; then
        local archive_pid=$(<"$archive_lock")
        if kill -0 "$archive_pid" 2>/dev/null; then
            print_status "INFO" "Archive script is running (PID: $archive_pid)"
        else
            print_status "WARNING" "Stale archive lock file found (PID: $archive_pid)"
        fi
    else
        print_status "OK" "No archive lock file"
    fi
}

# Проверка последних бэкапов
check_recent_backups() {
    print_status "INFO" "Checking recent backups..."
    
    local current_bucket=$(get_current_bucket)
    local backup_dir="${BACKUP_BASE_DIR}/${current_bucket}-backup"
    
    if [[ ! -d "$backup_dir" ]]; then
        print_status "ERROR" "Backup directory not found: $backup_dir"
        return 1
    fi
    
    # Проверка последних метрик
    local latest_metrics
    latest_metrics=$(find "$backup_dir" -name "metrics-*.txt" -type f -exec ls -t {} + | head -1 2>/dev/null || echo "")
    
    if [[ -n "$latest_metrics" ]]; then
        local metrics_time
        metrics_time=$(stat -c %Y "$latest_metrics" 2>/dev/null || echo 0)
        local current_time=$(date +%s)
        local age=$((current_time - metrics_time))
        
        if (( age < 3600 )); then
            print_status "OK" "Recent backup found ($(($age / 60)) minutes ago)"
            
            # Проверка успешности последнего бэкапа
            local success_flag
            success_flag=$(grep "s3_backup_success" "$latest_metrics" | tail -1 | awk '{print $2}' || echo "0")
            
            if [[ "$success_flag" == "1" ]]; then
                print_status "OK" "Last backup was successful"
            else
                print_status "ERROR" "Last backup failed"
            fi
        else
            print_status "WARNING" "Last backup is old ($(($age / 3600)) hours ago)"
        fi
    else
        print_status "ERROR" "No backup metrics found"
    fi
}

# Проверка дискового пространства
check_disk_space() {
    print_status "INFO" "Checking disk space..."
    
    for dir in "$BACKUP_BASE_DIR" "$ARCHIVE_BASE_DIR"; do
        if [[ -d "$dir" ]]; then
            local usage
            usage=$(df "$dir" | awk 'NR==2 {print $5}' | tr -d '%')
            
            if (( usage >= 90 )); then
                print_status "ERROR" "$dir is ${usage}% full"
            elif (( usage >= 75 )); then
                print_status "WARNING" "$dir is ${usage}% full"
            else
                print_status "OK" "$dir is ${usage}% full"
            fi
        else
            print_status "ERROR" "Directory not found: $dir"
        fi
    done
}

# Проверка подключения к S3
check_s3_connectivity() {
    print_status "INFO" "Checking S3 connectivity..."
    
    if rclone lsd s3: &>/dev/null; then
        print_status "OK" "S3 connection successful"
        
        # Проверка текущего бакета
        local current_bucket=$(get_current_bucket)
        if rclone lsd s3: | grep -q "$current_bucket"; then
            print_status "OK" "Current bucket exists: $current_bucket"
        else
            print_status "WARNING" "Current bucket not found: $current_bucket"
        fi
    else
        print_status "ERROR" "S3 connection failed"
    fi
}

# Анализ метрик за последние 24 часа
analyze_metrics() {
    print_status "INFO" "Analyzing metrics for last 24 hours..."
    
    local current_bucket=$(get_current_bucket)
    local backup_dir="${BACKUP_BASE_DIR}/${current_bucket}-backup"
    
    if [[ ! -d "$backup_dir" ]]; then
        print_status "ERROR" "Backup directory not found"
        return 1
    fi
    
    local total_copied=0
    local total_deleted=0
    local total_size=0
    local success_count=0
    local failure_count=0
    local metrics_count=0
    
    # Анализ метрик за последние 24 часа
    while IFS= read -r -d '' metrics_file; do
        local file_time
        file_time=$(stat -c %Y "$metrics_file" 2>/dev/null || echo 0)
        local current_time=$(date +%s)
        local age=$((current_time - file_time))
        
        # Пропускаем файлы старше 24 часов
        if (( age > 86400 )); then
            continue
        fi
        
        ((metrics_count++))
        
        # Извлечение метрик
        local copied
        copied=$(grep "s3_backup_copied_objects_total" "$metrics_file" | awk '{print $2}' || echo "0")
        total_copied=$((total_copied + copied))
        
        local deleted
        deleted=$(grep "s3_backup_deleted_objects_total" "$metrics_file" | awk '{print $2}' || echo "0")
        total_deleted=$((total_deleted + deleted))
        
        local size
        size=$(grep "s3_backup_copied_bytes_total" "$metrics_file" | awk '{print $2}' || echo "0")
        total_size=$((total_size + size))
        
        local success
        success=$(grep "s3_backup_success" "$metrics_file" | awk '{print $2}' || echo "0")
        if [[ "$success" == "1" ]]; then
            ((success_count++))
        else
            ((failure_count++))
        fi
        
    done < <(find "$backup_dir" -name "metrics-*.txt" -type f -print0 2>/dev/null)
    
    print_status "INFO" "24h Summary:"
    echo "  - Backup runs: $metrics_count"
    echo "  - Successful: $success_count"
    echo "  - Failed: $failure_count"
    echo "  - Objects copied: $total_copied"
    echo "  - Objects deleted: $total_deleted"
    echo "  - Data copied: $(numfmt --to=iec $total_size 2>/dev/null || echo $total_size) bytes"
    
    if (( failure_count > 0 )); then
        print_status "WARNING" "$failure_count failed backup runs in last 24h"
    else
        print_status "OK" "All backup runs successful in last 24h"
    fi
}

# Проверка логов на ошибки
check_log_errors() {
    print_status "INFO" "Checking logs for errors..."
    
    local current_bucket=$(get_current_bucket)
    local backup_dir="${BACKUP_BASE_DIR}/${current_bucket}-backup"
    local log_file="${backup_dir}/backup.log"
    
    if [[ -f "$log_file" ]]; then
        local error_count
        error_count=$(grep -c "ERROR" "$log_file" 2>/dev/null || echo 0)
        local warning_count
        warning_count=$(grep -c "WARNING" "$log_file" 2>/dev/null || echo 0)
        
        if (( error_count > 0 )); then
            print_status "ERROR" "Found $error_count errors in log"
            echo "Recent errors:"
            grep "ERROR" "$log_file" | tail -3 | sed 's/^/  /'
        fi
        
        if (( warning_count > 0 )); then
            print_status "WARNING" "Found $warning_count warnings in log"
        fi
        
        if (( error_count == 0 && warning_count == 0 )); then
            print_status "OK" "No errors or warnings in log"
        fi
    else
        print_status "ERROR" "Log file not found: $log_file"
    fi
}

# Генерация отчета
generate_report() {
    local report_file="${REPORT_DIR}/status-$(date +%Y%m%d-%H%M%S).txt"
    mkdir -p "$REPORT_DIR"
    
    print_status "INFO" "Generating report: $report_file"
    
    {
        echo "S3 Backup System Status Report"
        echo "Generated: $(date)"
        echo "========================================"
        echo
        
        echo "SYSTEM STATUS:"
        check_lock_files 2>&1 | sed 's/\x1b\[[0-9;]*m//g'
        echo
        
        echo "S3 CONNECTIVITY:"
        check_s3_connectivity 2>&1 | sed 's/\x1b\[[0-9;]*m//g'
        echo
        
        echo "DISK SPACE:"
        check_disk_space 2>&1 | sed 's/\x1b\[[0-9;]*m//g'
        echo
        
        echo "RECENT BACKUPS:"
        check_recent_backups 2>&1 | sed 's/\x1b\[[0-9;]*m//g'
        echo
        
        echo "24H METRICS:"
        analyze_metrics 2>&1 | sed 's/\x1b\[[0-9;]*m//g'
        echo
        
        echo "LOG ANALYSIS:"
        check_log_errors 2>&1 | sed 's/\x1b\[[0-9;]*m//g'
        
    } > "$report_file"
    
    print_status "OK" "Report saved to $report_file"
}

# Очистка старых отчетов
cleanup_reports() {
    if [[ -d "$REPORT_DIR" ]]; then
        find "$REPORT_DIR" -name "status-*.txt" -mtime +7 -delete 2>/dev/null || true
        print_status "INFO" "Old reports cleaned up"
    fi
}

# Основная функция
main() {
    echo "S3 Backup System Monitor"
    echo "========================"
    echo
    
    case "${1:-status}" in
        "status")
            check_lock_files
            echo
            check_s3_connectivity
            echo
            check_disk_space
            echo
            check_recent_backups
            echo
            analyze_metrics
            echo
            check_log_errors
            ;;
        "report")
            generate_report
            cleanup_reports
            ;;
        "quick")
            check_s3_connectivity
            check_recent_backups
            ;;
        "help")
            echo "Usage: $0 [status|report|quick|help]"
            echo "  status  - Full status check (default)"
            echo "  report  - Generate detailed report file"
            echo "  quick   - Quick connectivity and backup check"
            echo "  help    - Show this help"
            ;;
        *)
            print_status "ERROR" "Unknown command: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Проверка зависимостей
check_dependencies() {
    local deps=("rclone" "date" "df" "find" "stat" "awk")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            print_status "ERROR" "Required command '$dep' not found"
            exit 1
        fi
    done
}

# Запуск
check_dependencies
main "$@"