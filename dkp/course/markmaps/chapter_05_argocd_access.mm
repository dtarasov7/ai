# Глава 5. Argo CD и operator-argo

## Зачем отдельная глава

### Это не только deployment
- новый пользовательский интерфейс
- новый слой доступа
- новый привилегированный контур

### Что меняется
- меньше прямого kubectl
- больше GitOps и auditability
- новый набор рисков

## operator-argo в DKP

### Что даёт
- platform-managed установка
- интеграция с Dex / SSO
- единый UI приложений

### Что не отменяет
- отдельный RBAC Argo CD
- review AppProject
- обновления и advisories

## Когда Argo CD полезен

### Для dev/test
- статус приложения
- дерево ресурсов
- события
- логи

### Для платформы
- меньше kubeconfig
- меньше ad hoc kubectl
- понятнее audit trail

## Граница доступа

### Argo RBAC
- policy.default role:none
- applications get
- logs get
- exec не давать по умолчанию
- override не давать по умолчанию

### AppProject
- разрешённый repo
- разрешённые namespace
- разрешённые типы ресурсов
- запрет cluster-scoped ресурсов

## Риски

### Что уменьшается
- массовый прямой kubectl
- ручной apply
- слабая наблюдаемость drift

### Что появляется
- UI/API как новая точка атаки
- Git и repo credentials как критичный слой
- второй RBAC поверх Kubernetes RBAC

## Auto-sync и self-heal

### Production
- обычно выключены
- sync через review и ручное подтверждение

### Non-production
- могут быть включены
- только после проверки границ проекта

## Когда Argo CD не окупается

### Признаки
- маленькая среда
- мало команд
- нет зрелого GitOps
- нет готовности сопровождать новый сервис

### Альтернатива
- узкий прямой kubectl
- компенсирующие меры
- явный break-glass

## Практика

### Артефакты
- access matrix
- argocd-rbac-cm
- AppProject
- решение по auto-sync
- break-glass
