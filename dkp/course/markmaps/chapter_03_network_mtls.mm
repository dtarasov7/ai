# Глава 3. Сетевые политики безопасности и mTLS

## Почему сеть в Kubernetes особенная

### Что меняется
- Pod IP не отвечает на вопрос, какой сервис делает запрос
- большой east-west трафик
- namespace не равен сетевой изоляции
- ServiceAccount важнее хоста

### Основные угрозы
- lateral movement
- свободный egress
- незашифрованный трафик
- доверие по принципу "внутри кластера можно"

## Минимальные сетевые требования

### Default deny
- ingress default deny
- egress default deny
- allow only explicit dependencies

### Policy language
- NetworkPolicy для простого минимального набора правил
- CiliumNetworkPolicy for richer cases

## DKP: cni-cilium

### Роль
- применение сетевых политик
- richer semantics
- единый сетевой минимум

## Istio and mTLS

### Что даёт mesh
- ServiceAccount сервиса
- mutual TLS
- traffic encryption
- авторизация по ServiceAccount

### Что не заменяет
- не заменяет NetworkPolicy
- не отменяет need for segmentation

## AuthorizationPolicy

### Что ограничивает
- кто может вызвать сервис
- какой service account доверен
- какие namespace допустимы

## Практика

### Для shop-demo
- frontend -> orders
- orders -> payments
- запрет всех остальных связей
- strict mTLS for critical path

### Артефакты
- connection matrix
- network policies
- mTLS and authorization policies
