# Глава 1. Основы ИБ в Kubernetes и DKP

## Почему Kubernetes требует особого взгляда на ИБ

### Что меняется
- декларативная модель управления
- быстро пересоздаваемые приложения
- динамичные технические учётные записи
- API как центр управления

### Какие риски выходят на первый план
- избыточные привилегии Pod
- ошибки RBAC
- подмена образов и supply chain drift
- слабая сегментация east-west трафика
- отсутствие обнаруживающих мер

## Модель 4C

### Cloud
- базовая инфраструктура
- сеть и perimeter
- усиление настроек хостов

### Cluster
- kube-apiserver
- etcd
- доступ к управляющему слою Kubernetes
- audit

### Container
- image provenance
- runtime restrictions
- securityContext
- secrets handling

### Code
- уязвимости приложения
- безопасные зависимости
- корректная работа с секретами

## Zero Trust для DKP

### Принципы
- не доверять по факту нахождения в одной сети
- требовать понятный источник запроса
- разрешать только явно необходимое
- постоянно проверять состояние

### Слои реализации
- доступ и учётные записи
- проверка ресурсов перед запуском
- network
- PKI and secrets
- scanning and audit

## Встроенные механизмы DKP

### Доступ и учётные записи
- user-authn
- user-authz
- Dex

### Проверка ресурсов перед запуском
- admission-policy-engine
- PSS
- SecurityPolicy
- OperationPolicy

### Network
- cni-cilium
- istio

### Trust material
- cert-manager
- Stronghold
- secrets-store-integration

### Проверки и сигналы обнаружения
- operator-trivy
- runtime-audit-engine
- API audit
- контроль целостности

## Практический вывод

### Что нужно сделать сначала
- собрать threat model
- определить trust boundaries
- выбрать стартовый минимум требований

### Что внедряется поэтапно
- применение политик допуска
- default deny network
- IAM review
- rotation and secret delivery
- triage process for findings
