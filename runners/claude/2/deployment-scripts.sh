#!/bin/bash
# ==========================================
# deploy-gitlab-runners.sh
# Скрипт для развертывания GitLab Runners
# ==========================================

set -euo pipefail

# Конфигурация
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE_PREFIX="gitlab-runner"
TENANTS=("tenant-1" "tenant-2")

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция логирования
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Проверка зависимостей
check_dependencies() {
    log "Проверка зависимостей..."
    
    if ! command -v kubectl &> /dev/null; then
        error "kubectl не найден. Установите kubectl."
    fi
    
    if ! command -v base64 &> /dev/null; then
        error "base64 не найден."
    fi
    
    # Проверка подключения к кластеру
    if ! kubectl cluster-info &> /dev/null; then
        error "Не удается подключиться к Kubernetes кластеру."
    fi
    
    log "Все зависимости установлены."
}

# Подготовка узлов кластера
prepare_nodes() {
    log "Подготовка узлов кластера..."
    
    # Проверяем наличие узлов для каждого tenant
    for tenant in "${TENANTS[@]}"; do
        log "Проверка узлов для $tenant..."
        
        # Добавляем метки к узлам
        local nodes=$(kubectl get nodes -l "kubernetes.io/hostname" --no-headers | awk '{print $1}' | head -2)
        local node_count=0
        
        for node in $nodes; do
            if [ $node_count -eq 0 ] && [ "$tenant" = "tenant-1" ]; then
                kubectl label nodes $node tenant=tenant-1 --overwrite
                kubectl taint nodes $node tenant=tenant-1:NoSchedule --overwrite
                log "Узел $node настроен для tenant-1"
            elif [ $node_count -eq 1 ] && [ "$tenant" = "tenant-2" ]; then
                kubectl label nodes $node tenant=tenant-2 --overwrite
                kubectl taint nodes $node tenant=tenant-2:NoSchedule --overwrite
                log "Узел $node настроен для tenant-2"
            fi
            ((node_count++))
        done
    done
}

# Создание S3 bucket и пользователей
create_s3_resources() {
    log "Создание S3 ресурсов..."
    
    for tenant in "${TENANTS[@]}"; do
        local bucket_name="${tenant}-gitlab-cache"
        local username="${tenant}-gitlab-user"
        
        log "Создание bucket $bucket_name и пользователя $username..."
        
        # Здесь должны быть команды для создания S3 bucket и пользователя
        # Пример для Ceph с radosgw-admin:
        # radosgw-admin user create --uid=$username --display-name="GitLab $tenant User"
        # radosgw-admin bucket create --bucket=$bucket_name --uid=$username
        
        warn "Необходимо вручную создать S3 bucket '$bucket_name' и пользователя '$username'"
        warn "Обновите секреты с правильными access-key и secret-key"
    done
}

# Создание секретов
create_secrets() {
    log "Создание секретов..."
    
    for tenant in "${TENANTS[@]}"; do
        local namespace="${NAMESPACE_PREFIX}-${tenant}"
        
        log "Создание секретов для $tenant..."
        
        # Запрос учетных данных S3
        read -p "Введите S3 Access Key для $tenant: " s3_access_key
        read -s -p "Введите S3 Secret Key для $tenant: " s3_secret_key
        echo
        
        # Кодирование в base64
        local access_key_b64=$(echo -n "$s3_access_key" | base64 -w 0)
        local secret_key_b64=$(echo -n "$s3_secret_key" | base64 -w 0)
        
        # Создание временного файла с секретом
        cat > "/tmp/s3-secret-${tenant}.yaml" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: s3-credentials
  namespace: $namespace
type: Opaque
data:
  access-key: $access_key_b64
  secret-key: $secret_key_b64
EOF
        
        log "Секрет для $tenant создан."
    done
}

# Обновление runner токенов
update_runner_tokens() {
    log "Обновление runner токенов..."
    
    for tenant in "${TENANTS[@]}"; do
        read -p "Введите GitLab Runner token для $tenant: " runner_token
        
        # Обновляем ConfigMap с токеном
        local namespace="${NAMESPACE_PREFIX}-${tenant}"
        local config_file="/tmp/runner-config-${tenant}.yaml"
        
        # Создаем обновленную конфигурацию
        kubectl get configmap gitlab-runner-config -n $namespace -o yaml > $config_file 2>/dev/null || true
        
        if [ -f "$config_file" ]; then
            # Обновляем токен в конфигурации
            sed -i "s/token = \".*\"/token = \"$runner_token\"/" $config_file
            log "Токен для $tenant обновлен."
        else
            warn "ConfigMap для $tenant не найден. Будет создан при деплое."
        fi
    done
}

# Применение манифестов
apply_manifests() {
    log "Применение манифестов Kubernetes..."
    
    # Применяем манифесты для каждого tenant
    if [ -f "$SCRIPT_DIR/gitlab-runners.yaml" ]; then
        kubectl apply -f "$SCRIPT_DIR/gitlab-runners.yaml"
        log "Основные манифесты применены."
    else
        error "Файл gitlab-runners.yaml не найден в $SCRIPT_DIR"
    fi
    
    # Применяем секреты
    for tenant in "${TENANTS[@]}"; do
        local secret_file="/tmp/s3-secret-${tenant}.yaml"
        if [ -f "$secret_file" ]; then
            kubectl apply -f "$secret_file"
            rm -f "$secret_file"
            log "Секрет для $tenant применен."
        fi
    done
}

# Проверка состояния развертывания
check_deployment_status() {
    log "Проверка состояния развертывания..."
    
    for tenant in "${TENANTS[@]}"; do
        local namespace="${NAMESPACE_PREFIX}-${tenant}"
        
        log "Проверка $tenant..."
        
        # Ожидание готовности deployment
        kubectl wait --for=condition=available --timeout=300s deployment/gitlab-runner -n $namespace
        
        # Проверка статуса подов
        kubectl get pods -n $namespace -l app=gitlab-runner
        
        # Проверка логов
        local pod_name=$(kubectl get pods -n $namespace -l app=gitlab-runner -o jsonpath='{.items[0].metadata.name}')
        if [ -n "$pod_name" ]; then
            log "Последние логи runner для $tenant:"
            kubectl logs $pod_name -n $namespace --tail=10
        fi
    done
}

# Настройка мониторинга
setup_monitoring() {
    log "Настройка мониторинга..."
    
    # Создание ServiceMonitor для Prometheus
    cat > "/tmp/servicemonitor.yaml" <<EOF
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: gitlab-runners
  namespace: monitoring
  labels:
    app: gitlab-runner
spec:
  selector:
    matchLabels:
      app: gitlab-runner
  namespaceSelector:
    matchNames:
$(for tenant in "${TENANTS[@]}"; do echo "    - gitlab-runner-${tenant}"; done)
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
EOF
    
    if kubectl get namespace monitoring &> /dev/null; then
        kubectl apply -f "/tmp/servicemonitor.yaml"
        rm -f "/tmp/servicemonitor.yaml"
        log "ServiceMonitor создан."
    else
        warn "Namespace 'monitoring' не найден. ServiceMonitor не создан."
        warn "Файл сохранен в /tmp/servicemonitor.yaml"
    fi
}

# Основная функция
main() {
    log "Начало развертывания GitLab Runners..."
    
    check_dependencies
    prepare_nodes
    create_s3_resources
    create_secrets
    update_runner_tokens
    apply_manifests
    check_deployment_status
    setup_monitoring
    
    log "Развертывание завершено успешно!"
    log "Runners доступны в следующих namespace:"
    for tenant in "${TENANTS[@]}"; do
        echo "  - ${NAMESPACE_PREFIX}-${tenant}"
    done
}

# Функция очистки
cleanup() {
    log "Удаление GitLab Runners..."
    
    for tenant in "${TENANTS[@]}"; do
        local namespace="${NAMESPACE_PREFIX}-${tenant}"
        
        if kubectl get namespace $namespace &> /dev/null; then
            kubectl delete namespace $namespace
            log "Namespace $namespace удален."
        fi
    done
    
    # Удаление ServiceMonitor
    kubectl delete servicemonitor gitlab-runners -n monitoring 2>/dev/null || true
    
    log "Очистка завершена."
}

# Функция обновления
update() {
    log "Обновление GitLab Runners..."
    
    for tenant in "${TENANTS[@]}"; do
        local namespace="${NAMESPACE_PREFIX}-${tenant}"
        
        if kubectl get namespace $namespace &> /dev/null; then
            kubectl rollout restart deployment/gitlab-runner -n $namespace
            kubectl rollout status deployment/gitlab-runner -n $namespace
            log "Runner для $tenant обновлен."
        fi
    done
}

# Функция показа логов
logs() {
    local tenant=${1:-"tenant-1"}
    local namespace="${NAMESPACE_PREFIX}-${tenant}"
    
    if kubectl get namespace $namespace &> /dev/null; then
        local pod_name=$(kubectl get pods -n $namespace -l app=gitlab-runner -o jsonpath='{.items[0].metadata.name}')
        if [ -n "$pod_name" ]; then
            kubectl logs -f $pod_name -n $namespace
        else
            error "Pod для $tenant не найден."
        fi
    else
        error "Namespace $namespace не найден."
    fi
}

# Обработка аргументов командной строки
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "cleanup")
        cleanup
        ;;
    "update")
        update
        ;;
    "logs")
        logs "${2:-tenant-1}"
        ;;
    "status")
        check_deployment_status
        ;;
    *)
        echo "Использование: $0 {deploy|cleanup|update|logs [tenant]|status}"
        echo "  deploy  - Развернуть GitLab Runners"
        echo "  cleanup - Удалить GitLab Runners"
        echo "  update  - Обновить GitLab Runners"
        echo "  logs    - Показать логи runner (по умолчанию tenant-1)"
        echo "  status  - Проверить статус развертывания"
        exit 1
        ;;
esac