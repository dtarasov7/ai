# Инжектирование секретов в Deckhouse из Vault

## С использованием secrets-store-integration

### Описание модуля
- Доставляет секреты в поды приложений путём монтирования множественных секретов, ключей и сертификатов из внешних хранилищ
- Секрет извлекается из хранилища CSI драйвером на этапе создания контейнера. Поды запускаются только после чтения секретов из хранилища
- Требует предварительно настроенное хранилище секретов, совместимое с HashiCorp Vault с настроенным путем аутентификации

### Варианты без pod-reloader

#### CSI Volume Mount
##### Описание
- Секрет извлекается CSI драйвером при создании контейнера и записывается в volume контейнера
- Статус: безопасная опция
- Секреты доступны как файлы в файловой системе пода

##### Конфигурация
- Создание SecretsStoreImport CR
  - Указание типа: CSI
  - Определение роли и пути к секретам
  - Спецификация файлов для монтирования
- Использование в Deployment/StatefulSet
  - Монтирование CSI volume с драйвером secrets-store.csi.deckhouse.io
  - Ссылка на SecretsStoreImport через volumeAttributes

##### Пример использования
```yaml
apiVersion: deckhouse.io/v1alpha1
kind: SecretsStoreImport
metadata:
  name: python-backend
spec:
  type: CSI
  role: my-namespace1_backend
  files:
    - name: "db-password"
      source:
        path: "secret/data/database-for-python-app"
        key: "password"
```

#### Environment Variables (через injector)
##### Описание  
- При включенном модуле доступен mutating-webhook, который модифицирует pod manifest при наличии аннотации secrets-store.deckhouse.io/role, добавляя init контейнер для копирования injector и замены команд запуска
- Статус: небезопасно; не рекомендуется к использованию

##### Конфигурация
- Использование аннотаций на подах
  - `secrets-store.deckhouse.io/role`: указание роли
  - `secrets-store.deckhouse.io/env-from-path`: пути к секретам
- Определение переменных окружения с шаблонами
  - Формат: `secrets-store:path#key`

##### Пример
```yaml
annotations:
  secrets-store.deckhouse.io/role: "myapp-role"
env:
  - name: DB_PASS
    value: secrets-store:demo-kv/data/myapp-secret#DB_PASS
```

#### Синхронизация в K8s Secrets
##### Описание
- Использует Kubernetes secrets operator для синхронизации секретов из Vault в Kubernetes secrets. Небезопасно, так как данные хранятся в Kubernetes и etcd
- Традиционный способ передачи секретов через переменные окружения

##### Проблемы
- Секреты хранятся в etcd
- Потенциально могут быть прочитаны на любой ноде кластера
- Меньшая безопасность по сравнению с CSI

### Варианты с pod-reloader

#### CSI Mount + Auto Reload
##### Описание
- Комбинация CSI монтирования и автоматической перезагрузки
- Pod-reloader обеспечивает автоматический rollout при изменении ConfigMap или Secret

##### Конфигурация pod-reloader
- Включение модуля pod-reloader
```yaml
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: pod-reloader
spec:
  enabled: true
  version: 1
```

##### Аннотации для автоматического перезапуска
- `pod-reloader.deckhouse.io/auto: "true"` - отслеживание всех изменений в примонтированных ресурсах
- `pod-reloader.deckhouse.io/search: "true"` - отслеживание конкретных ресурсов
- `pod-reloader.deckhouse.io/secret-reload: "secret-name"` - указание конкретных секретов

##### Преимущества
- Автоматическое обновление при ротации секретов
- Не требует ручного вмешательства
- Поддержка rolling updates

#### Environment Variables + Auto Reload
##### Описание
- Injector инжектирует секреты как переменные окружения
- Pod-reloader перезапускает поды при изменениях

##### Особенности
- Аннотации configmap-reload и secret-reload не могут использоваться вместе с auto: "true"
- Требует правильной настройки аннотаций

##### Пример конфигурации
```yaml
metadata:
  annotations:
    secrets-store.deckhouse.io/role: "myapp-role"
    pod-reloader.deckhouse.io/auto: "true"
```

## Без использования secrets-store-integration

### Описание
- Прямые методы интеграции Vault с Kubernetes
- Не используют Deckhouse-специфичные модули
- Требуют сторонние операторы или native Vault инструменты

### Варианты без pod-reloader

#### Vault Agent Injector (Sidecar)
##### Описание
- Vault Agent работает как sidecar контейнер
- Инжектирует секреты через shared volume
- Поддерживает динамическую ротацию

##### Преимущества
- Аутентификация через Kubernetes ServiceAccount
- Автоматическое обновление секретов
- Поддержка шаблонов

##### Недостатки  
- Дополнительный overhead от sidecar контейнера
- Сложность конфигурации

##### Конфигурация
- Аннотации Vault Agent
  - `vault.hashicorp.com/agent-inject: "true"`
  - `vault.hashicorp.com/role: "app-role"`
  - `vault.hashicorp.com/agent-inject-secret-*`

#### External Secrets Operator
##### Описание
- Оператор для синхронизации секретов из различных провайдеров
- Создает и управляет Kubernetes Secrets на основе данных из Vault

##### Преимущества
- Поддержка множества провайдеров
- Декларативная конфигурация через CRD
- Автоматическая синхронизация

##### Недостатки
- Требует установки оператора
- Секреты хранятся в etcd

##### Конфигурация
```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "https://vault.example.com"
      path: "secret"
      version: "v2"
```

#### Vault CSI Provider
##### Описание
- CSI драйвер отправляет запрос к Vault CSI, который использует SecretProviderClass и ServiceAccount пода для получения секретов
- Монтирует секреты напрямую как volumes

##### Преимущества
- Низкий overhead
- Не требует sidecar контейнеров
- Подходит для stateless приложений

##### Конфигурация
```yaml
apiVersion: v1
kind: SecretProviderClass
metadata:
  name: vault-csi
spec:
  provider: vault
  parameters:
    vaultAddress: "https://vault.example.com"
    roleName: "app-role"
    objects: |
      - objectName: "database-password"
        secretPath: "secret/data/db"
        secretKey: "password"
```

### Варианты с pod-reloader

#### Vault Agent + Reloader
##### Описание
- Vault Agent инжектирует секреты
- Reloader проверяет новые версии секретов в Vault и автоматически перезагружает workloads путем инкрементирования аннотации

##### Конфигурация
- Аннотации для Vault Agent Injector
- Аннотации для pod-reloader
  - `reloader.stakater.com/auto: "true"` или аналоги Deckhouse

##### Преимущества
- Автоматическая ротация с перезапуском
- Полная интеграция с Vault

#### External Secrets + Reloader  
##### Описание
- External Secrets синхронизирует данные
- Reloader автоматически триггерит rollouts при обновлении Secrets или ConfigMaps

##### Стратегии перезагрузки
- env-vars: добавляет dummy переменную окружения для форсирования rolling update
- annotations: добавляет аннотацию last-reloaded-from, идеально для GitOps

##### Преимущества
- Поддержка rolling updates без downtime
- Гибкая настройка через аннотации

#### CSI Provider + Reloader
##### Описание
- CSI монтирует секреты как volumes
- Reloader отслеживает изменения

##### Особенности
- Может требовать кастомную настройку
- CSI обновления не всегда триггерят релоад автоматически

##### Конфигурация
- SecretProviderClass для Vault
- Аннотации pod-reloader на workloads

## Интеграция с Stronghold

### Описание
- Deckhouse Stronghold - HashiCorp Vault-совместимый API
- Модуль для безопасного хранения и управления жизненным циклом секретов, реализован как key-value хранилище

### Преимущества использования
- Нативная интеграция с Deckhouse
- Доступ через web интерфейс и API
- Поддержка Kubernetes ServiceAccounts

### Конфигурация с secrets-store-integration
- Параметр connectionConfiguration можно опустить, используется DiscoverLocalStronghold по умолчанию
- Автоматическое обнаружение локального Stronghold

## Рекомендации по выбору решения

### Для максимальной безопасности
- CSI монтирование - безопасная опция
- Прямой доступ приложения к Stronghold API - наиболее безопасная опция
- Избегать синхронизации в K8s Secrets

### Для простоты использования
- secrets-store-integration с CSI
- Автоматическая конфигурация с Stronghold
- Использование pod-reloader для автоматизации

### Для legacy приложений
- External Secrets Operator
- Vault Agent Injector
- Синхронизация в K8s Secrets (с пониманием рисков)

### Для GitOps окружений
- Использование annotations стратегии в reloader для предотвращения drift в ArgoCD или Flux
- External Secrets Operator
- Декларативная конфигурация через CRD

## Важные замечания

### Безопасность
- Синхронизация в K8s Secrets небезопасна - данные хранятся в etcd
- Секреты в приложении не хранятся нигде кроме самого приложения при прямом доступе к API

### Производительность
- Sidecar контейнеры создают дополнительный overhead
- CSI драйвер имеет минимальный overhead
- Reloader не имеет HighAvailability режима

### Совместимость аннотаций
- Нельзя использовать configmap-reload и secret-reload вместе с auto: "true"
- Аннотация search не может использоваться с auto: "true"

### Требования к конфигурации
- Настоятельно рекомендуется устанавливать caCert переменную
- Требуется предварительно настроенное хранилище с путем аутентификации
