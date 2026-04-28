# Глава 2. Безопасность пода

## Pod security как основа

### Почему это важно
- именно Pod доходит до runtime
- ошибка в Pod spec быстро превращается в эксплуатационный риск
- без проверки ресурсов перед запуском остальные проверки догоняют проблему постфактум

## Базовые механизмы

### Pod Security Standards
- privileged
- минимальный набор требований
- restricted

### Security Context
- runAsNonRoot
- allowPrivilegeEscalation
- readOnlyRootFilesystem
- capabilities
- seccomp

### Admission как проверка на входе
- проверка до записи ресурса в API
- platform guardrail
- единая точка применения правил

## DKP: admission-policy-engine

### Что даёт
- PSS: уровень baseline
- SecurityPolicy
- OperationPolicy
- режимы warn, dryrun, deny

### Типовые требования
- allowed registries
- запрет `latest`
- requests and limits
- обязательные probes
- контроль exec and attach

## Rollout

### Правильная последовательность
- inventory запускаемых приложений
- warn mode
- исправление нарушений
- deny for critical namespaces
- selective move to restricted

### Что ломает внедрение
- включение deny без подготовки
- отсутствие owners for violations
- вечные исключения для legacy

## Практика

### Для shop-demo
- определить минимальные требования для frontend, orders, payments
- подготовить OperationPolicy
- описать legacy exceptions

### Артефакты
- namespace policy matrix
- rollout plan
- backlog исправлений приложений
