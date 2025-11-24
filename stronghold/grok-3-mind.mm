# Инъекция секретов из Stronghold в Deckhouse App

## Расположение Stronghold
### В том же кластере (Локальный)
#### С использованием secrets-store-integration
##### Автоматическая настройка (DiscoverLocalStronghold)
##### Инъекция через env vars (аннотации: secrets-store.deckhouse.io/env-from-path)
##### Инъекция через CSI volumes (SecretsStoreImport CR)
##### Ротация секретов (поллинг каждые 2 мин)
##### Аутентификация: Kubernetes auth (local path: kubernetes_local)
##### Плюсы: Низкая задержка, простота
##### Минусы: Зависимость от кластера
#### Без secrets-store-integration
##### Ручная инъекция via Vault CLI в init-container
##### Создание K8s Secrets из Stronghold (kubectl create secret)
##### Прямой доступ из app (HTTP to Stronghold API, не рекомендуется)
##### Использование Vault Agent Injector (если Helm установлен)
##### Аутентификация: SA token или AppRole
##### Плюсы: Гибкость для custom logic
##### Минусы: Нет авто-ротации, больше ручной работы, уязвимости
### Вне кластера (External)
#### С использованием secrets-store-integration
##### Manual connection config (ModuleConfig: url, authPath, CA)
##### Override аннотации (secrets-store.deckhouse.io/addr, auth-path)
##### Инъекция через env vars (аналогично локальному)
##### Инъекция через CSI volumes (аналогично локальному)
##### Ротация секретов (с сетевыми вызовами)
##### Аутентификация: Remote Kubernetes auth (custom path: remote-kube-1)
##### Сетевые требования: HTTPS, VPN/Firewall
##### Плюсы: Central management, multi-cluster
##### Минусы: Задержки, TLS overhead
#### Без secrets-store-integration
##### Ручная инъекция via Vault CLI в init-container (с URL)
##### Создание K8s Secrets externally (pull via API)
##### Прямой доступ из app (HTTPS to external Stronghold)
##### Sidecar container (Vault agent для caching)
##### Аутентификация: JWT/SA token to external auth backend
##### Плюсы: Независимость от Deckhouse модулей
##### Минусы: Сложная настройка сети, нет интеграции, ручная ротация
## Общие требования
### К приложению
#### Чтение из env vars или mounted files
#### Idempotent к изменениям секретов
#### Namespace alignment
### К кластеру
#### Deckhouse с Kubernetes 1.25+
#### ServiceAccount с bound ролями в Stronghold
### Требования к Stronghold
#### KV v2 secrets (paths like demo-kv/data/myapp-secret)
#### Policies и Roles для read access
## Диаграмма рендеринга
### Используйте markmap для визуализации
#### markmap --markdown this-file.md > mindmap.html
#### Откройте в браузере для интерактивной mind map
