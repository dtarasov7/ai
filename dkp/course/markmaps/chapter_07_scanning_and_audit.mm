# Глава 7. Выявление уязвимостей и аудит

## Проверки и сигналы обнаружения

### Почему обязательны
- слой предотвращения не видит всё
- новые CVE появляются после запуска
- runtime behavior меняется
- административные действия тоже риск

## Типы сигналов

### Trivy
- CVE
- compliance checks
- known image issues

### Runtime audit
- shell inside container
- suspicious mounts
- privileged behavior
- exploit patterns

### API audit
- who changed what
- administrative evidence
- incident investigation

### Контроль целостности
- digest verification
- drift detection

## Минимальные требования к supply chain

### Минимум
- trusted registries
- no mutable tags
- digest pinning

### Следующий уровень зрелости
- image signatures
- provenance checks
- SBOM

## DKP components

### Built-in
- operator-trivy
- runtime-audit-engine
- API audit
- контроль целостности

## Action loop

### Не просто alert
- assign owner
- set priority
- patch image
- tighten policy
- validate fix

## Практика

### Для shop-demo
- CVE in payments image
- shell in compromised container
- suspicious kubernetes API change

### Артефакты
- triage flow
- severity rules
- corrective action matrix
