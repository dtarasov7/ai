# Глава 4. Управление доступом

## IAM в Kubernetes

### Почему тема сложнее, чем кажется
- много разных субъектов
- люди и автоматизация требуют разных моделей
- временные исключения становятся постоянными
- нужен не только доступ, но и отзыв plus auditability

## Аутентификация

### Какие субъекты бывают
- люди
- service accounts
- CI/CD
- внешние IdP groups

### DKP
- user-authn
- Dex
- OIDC providers
- generated kubeconfig

## Авторизация

### RBAC
- roles
- cluster roles
- bindings
- least privilege

### user-authz
- current role model
- experimental role model

## Current vs experimental model

### Current
- high-level access levels
- короче YAML
- меньше прозрачность intent

### Experimental
- use roles
- manage roles
- ближе к native RBAC
- проще читать intent

## Процессы

### Что нужно построить
- role ownership
- review of access
- revoke process
- break-glass access
- separate machine identities

## Практика

### Для shop-demo
- developers
- platform team
- auditors
- CI/CD

### Артефакты
- group matrix
- role mapping
- access review process
