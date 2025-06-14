# Архитектура GitLab Runners с Kaniko в Kubernetes

## Варианты архитектуры

### 1. Архитектура с отдельными namespace и nodeSelector

**Описание**: Каждый tenant получает отдельный namespace с собственным GitLab Runner, который запускается на выделенных узлах через nodeSelector.

**Компоненты:**
- Отдельный namespace для каждого tenant
- GitLab Runner Deployment в каждом namespace
- NodeSelector для привязки к конкретным worker узлам
- Отдельные S3 bucket и учетные записи для кеширования
- ServiceAccount с ограниченными правами на namespace
- NetworkPolicy для изоляции трафика

**Преимущества:**
- Полная изоляция на уровне namespace
- Простота управления RBAC
- Четкое разделение ресурсов
- Легкость мониторинга per-tenant

**Недостатки:**
- Больше overhead на управление
- Дублирование конфигураций
- Сложность централизованного обновления

### 2. Архитектура с единым namespace и taints/tolerations

**Описание**: Все runners в одном namespace, но с использованием taints/tolerations для привязки к конкретным узлам.

**Компоненты:**
- Один namespace для всех runners
- Taints на worker узлах для каждого tenant
- Tolerations в Pod спецификации runners
- Отдельные ConfigMap и Secret для каждого runner
- Различные имена deployment для изоляции

**Преимущества:**
- Централизованное управление
- Меньше overhead на namespace
- Единая точка мониторинга

**Недостатки:**
- Меньшая изоляция
- Сложность RBAC настройки
- Риск случайного доступа к чужим ресурсам

### 3. Гибридная архитектура с DaemonSet

**Описание**: Использование DaemonSet с nodeSelector для запуска runners только на определенных узлах.

**Компоненты:**
- DaemonSet для каждой группы узлов
- Метки на узлах для группировки
- Статические конфигурации через ConfigMap
- Автоматическое масштабирование по узлам

**Преимущества:**
- Автоматическое развертывание на новых узлах
- Простота добавления новых узлов
- Гарантированное присутствие runner на каждом узле

**Недостатки:**
- Ограниченная гибкость в конфигурации
- Сложность параллельного выполнения заданий
- Привязка к топологии кластера

## Рекомендуемая архитектура

Рекомендую **первый вариант** с отдельными namespace, так как он обеспечивает:
- Максимальную изоляцию (требование ИБ)
- Простоту управления правами доступа
- Четкое разделение ресурсов и кешей
- Возможность независимого масштабирования

## Структура кеширования Kaniko

### S3 Cache
```
s3://tenant-1-cache/
├── cache/
│   ├── java-builds/
│   └── dotnet-builds/
└── layers/

s3://tenant-2-cache/
├── cache/
│   ├── java-builds/
│   └── dotnet-builds/
└── layers/
```

### Registry Cache (альтернатива)
```
registry.local/cache/tenant-1/
├── java-base:latest
├── dotnet-base:latest
└── build-cache:sha256-xxx

registry.local/cache/tenant-2/
├── java-base:latest
├── dotnet-base:latest
└── build-cache:sha256-xxx
```

## Схема взаимодействия

```
GitLab (External) 
    ↓ (webhook/API)
K8s Cluster
├── tenant-1-namespace
│   ├── GitLab Runner (20 concurrent jobs)
│   │   ↓ (создает Pod)
│   └── Kaniko Pod → S3 tenant-1-cache
├── tenant-2-namespace
│   ├── GitLab Runner (20 concurrent jobs)
│   │   ↓ (создает Pod)
│   └── Kaniko Pod → S3 tenant-2-cache
└── monitoring-namespace
    └── Prometheus → (scrape runners)
```

## Мониторинг

GitLab Runners экспонируют метрики на порту 9252:
- `gitlab_runner_jobs_total`
- `gitlab_runner_job_duration_seconds`
- `gitlab_runner_concurrent_jobs`
- `gitlab_runner_limit_concurrent_jobs`

## Требования к узлам

```yaml
# Метки для worker узлов
tenant-1-node:
  labels:
    tenant: tenant-1
    workload: gitlab-runner
  taints:
    - key: tenant
      value: tenant-1
      effect: NoSchedule

tenant-2-node:
  labels:
    tenant: tenant-2
    workload: gitlab-runner
  taints:
    - key: tenant
      value: tenant-2
      effect: NoSchedule
```