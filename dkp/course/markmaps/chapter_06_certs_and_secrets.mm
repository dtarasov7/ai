# Глава 6. Сертификаты и секреты

## Почему Kubernetes Secret недостаточен

### Ограничения
- слабая rotation model
- ограниченная auditability
- нет централизованной trust model
- доставка до приложения остаётся проблемой

## cert-manager

### Что закрывает
- issuing
- renewal
- issuer model
- internal and external PKI scenarios

### Типовые варианты
- corporate CA
- internal CA
- bootstrap with SelfSigned

## Stronghold

### Что даёт
- central secret store
- policy-based access
- short-lived credentials
- Vault-compatible model

## Delivery patterns

### Direct access
- приложение читает секрет само
- лучший вариант для зрелых приложений

### CSI-mounted files
- подходит для файловых секретов
- без хранения в Kubernetes Secret

### ENV injection
- компромисс для legacy-приложений
- удобнее, но слабее по security profile

## PKI and SSH

### Дальнейшее развитие
- internal PKI
- signed SSH certificates
- one-time passwords

## Практика

### Для shop-demo
- убрать static secret sprawl
- определить delivery pattern per service
- спроектировать rotation and ownership

### Артефакты
- certificate lifecycle scheme
- secret delivery matrix
- rotation policy
