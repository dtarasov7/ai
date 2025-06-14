#!/bin/bash

# ==========================================
# Скрипт развертывания GitLab Runners с Kaniko
# ==========================================

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для логирования
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка требований
check_requirements() {
    log_info "Checking requirements..."
    
    # Проверка kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed"
        exit 1
    fi
    
    # Проверка доступности кластера
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Проверка прав доступа
    if ! kubectl auth can-i create namespace; then
        log_error "Insufficient permissions to create namespaces"
        exit 1
    fi
    
    log_success "Requirements check passed"
}

# Создание секретов
create_secrets() {
    local tenant=$1
    local namespace="gitlab-runner-$tenant"
    local token=$2
    local registry_user=$3
    local registry_pass=$4
    
    log_info "Creating secrets for $tenant..."
    
    # GitLab Runner token
    kubectl create secret generic gitlab-runner-secret \
        --namespace="$namespace" \
        --from-literal=runner-registration-token="$token" \
        --from-literal=runner-token="" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Docker registry credentials
    kubectl create secret docker-registry kaniko-secret \
        --namespace="$namespace" \
        --docker-server="registry.company.com" \
        --docker-username="$registry_user" \
        --docker-password="$registry_pass" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    log_success "Secrets created for $tenant"
}

# Применение манифестов
apply_manifests() {
    log_info "Applying Kubernetes manifests..."
    
    # Создание namespaces
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: gitlab-runner-tenant-a
  labels:
    tenant: tenant-a
---
apiVersion: v1
kind: Namespace
metadata:
  name: gitlab-runner-tenant-b
  labels:
    tenant: tenant-b
EOF

    # Применение RBAC
    kubectl apply -f rbac-manifests.yaml
    
    # Применение основных манифестов
    kubectl apply -f gitlab-runner-manifests.yaml
    
    # Применение дополнительных конфигураций
    kubectl apply -f additional-configs.yaml
    
    log_success "Manifests applied successfully"
}

# Ожидание готовности подов
wait_for_pods() {
    local namespace=$1
    
    log_info "Waiting for pods in namespace $namespace to be ready..."
    
    kubectl wait --for=condition=ready pod \
        --selector=app=gitlab-runner \
        --namespace="$namespace" \
        --timeout=300s
    
    log_success "Pods in $namespace are ready"
}

# Регистрация runners
register_runners() {
    local tenant=$1
    local namespace="gitlab-runner-$tenant"
    local gitlab_url=$2
    local token=$3
    local tags=$4
    
    log_info "Registering GitLab Runner for $tenant..."
    
    # Получение имени пода
    local pod_name=$(kubectl get pods -n "$namespace" -l app=gitlab-runner -o jsonpath='{.items[0].metadata.name}')
    
    # Регистрация runner
    kubectl exec -n "$namespace" "$pod_name" -- \
        gitlab-runner register \
        --non-interactive \
        --url="$gitlab_url" \
        --registration-token="$token" \
        --executor=kubernetes \
        --tag-list="$tags" \
        --run-untagged=false \
        --locked=false \
        --access-level=not_protected \
        --kubernetes-namespace="$namespace"
    
    log_success "Runner registered for $tenant"
}

# Проверка состояния
check_status() {
    log_info "Checking deployment status..."
    
    echo -e "\n${BLUE}Namespaces:${NC}"
    kubectl get ns | grep gitlab-runner
    
    echo -e "\n${BLUE}Deployments:${NC}"
    kubectl get deployments -n gitlab-runner-tenant-a
    kubectl get deployments -n gitlab-runner-tenant-b
    
    echo -e "\n${BLUE}Pods:${NC}"
    kubectl get pods -n gitlab-runner-tenant-a
    kubectl get pods -n gitlab-runner-tenant-b
    
    echo -e "\n${BLUE}Services:${NC}"
    kubectl get services -n gitlab-runner-tenant-a
    kubectl get services -n gitlab-runner-tenant-b
    
    echo -e "\n${BLUE}Resource Quotas:${NC}"
    kubectl get resourcequota -n gitlab-runner-tenant-a
    kubectl get resourcequota -n gitlab-runner-tenant-b
}

# Тестирование функциональности
test_functionality() {
    log_info "Testing GitLab Runner functionality..."
    
    for tenant in tenant-a tenant-b; do
        local namespace="gitlab-runner-$tenant"
        local pod_name=$(kubectl get pods -n "$namespace" -l app=gitlab-runner -o jsonpath='{.items[0].metadata.name}')
        
        # Проверка статуса runner
        kubectl exec -n "$namespace" "$pod_name" -- gitlab-runner verify
        
        # Проверка логов
        log_info "Recent logs for $tenant:"
        kubectl logs -n "$namespace" "$pod_name" --tail=10
    done
    
    log_success "Functionality test completed"
}

# Создание примера pipeline
create_example_pipeline() {
    log_info "Creating example .gitlab-ci.yml..."
    
    cat > example-gitlab-ci.yml <<EOF
# Пример использования с Kaniko
variables:
  DOCKER_REGISTRY: "registry.company.com"
  DOCKER_REPOSITORY: "\$DOCKER_REGISTRY/example/app"

stages:
  - build
  - test
  - package

build:
  stage: build
  image: node:18-alpine
  tags:
    - tenant-a
    - nodejs
  script:
    - npm install
    - npm run build
  artifacts:
    paths:
      - dist/

test:
  stage: test
  image: node:18-alpine
  tags:
    - tenant-a
    - nodejs
  script:
    - npm test

package:
  stage: package
  image:
    name: gcr.io/kaniko-project/executor:v1.9.0-debug
    entrypoint: [""]
  tags:
    - tenant-a
    - kaniko
  script:
    - echo "{\\"auths\\":{\\"registry.company.com\\":{\\"auth\\":\\"\$(printf \\"%s:%s\\" \\"\$DOCKER_USERNAME\\" \\"\$DOCKER_PASSWORD\\" | base64 | tr -d '\\n')\\"}}}" > /kaniko/.docker/config.json
    - /kaniko/executor --context . --dockerfile Dockerfile --destination \$DOCKER_REPOSITORY:\$CI_COMMIT_SHA --cache=true --cache-repo=\$DOCKER_REGISTRY/cache
  only:
    - main
EOF
    
    log_success "Example .gitlab-ci.yml created"
}

# Функция очистки
cleanup() {
    log_warning "Cleaning up GitLab Runners deployment..."
    
    kubectl delete namespace gitlab-runner-tenant-a gitlab-runner-tenant-b || true
    kubectl delete clusterrole gitlab-runner || true
    
    log_success "Cleanup completed"
}

# Главная функция
main() {
    local command=${1:-deploy}
    
    case $command in
        "deploy")
            log_info "Starting GitLab Runners deployment..."
            
            # Чтение конфигурации
            source deploy.conf 2>/dev/null || {
                log_error "Configuration file deploy.conf not found"
                log_info "Creating example configuration file..."
                cat > deploy.conf <<EOF
# GitLab configuration
GITLAB_URL="https://gitlab.company.com/"

# Tenant A configuration
TENANT_A_TOKEN="your-tenant-a-token"
TENANT_A_REGISTRY_USER="tenant-a-user"
TENANT_A_REGISTRY_PASS="tenant-a-password"
TENANT_A_TAGS="tenant-a,kaniko,nodejs,java,dotnet"

# Tenant B configuration  
TENANT_B_TOKEN="your-tenant-b-token"
TENANT_B_REGISTRY_USER="tenant-b-user"
TENANT_B_REGISTRY_PASS="tenant-b-password"
TENANT_B_TAGS="tenant-b,kaniko,nodejs,java,dotnet"
EOF
                log_error "Please edit deploy.conf with your configuration and run again"
                exit 1
            }
            
            check_requirements
            apply_manifests
            
            create_secrets "tenant-a" "$TENANT_A_TOKEN" "$TENANT_A_REGISTRY_USER" "$TENANT_A_REGISTRY_PASS"
            create_secrets "tenant-b" "$TENANT_B_TOKEN" "$TENANT_B_REGISTRY_USER" "$TENANT_B_REGISTRY_PASS"
            
            wait_for_pods "gitlab-runner-tenant-a"
            wait_for_pods "gitlab-runner-tenant-b"
            
            register_runners "tenant-a" "$GITLAB_URL" "$TENANT_A_TOKEN" "$TENANT_A_TAGS"
            register_runners "tenant-b" "$GITLAB_URL" "$TENANT_B_TOKEN" "$TENANT_B_TAGS"
            
            check_status
            test_functionality
            create_example_pipeline
            
            log_success "GitLab Runners deployment completed successfully!"
            ;;
        "status")
            check_status
            ;;
        "test")
            test