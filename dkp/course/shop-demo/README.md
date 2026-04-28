# Учебный кластер `shop-demo`

## Что это физически

`shop-demo` не является “встроенным живым кластером” внутри репозитория. Физически это:
- учебный сценарий интернет-магазина;
- набор Kubernetes-манифестов в `shop-demo/manifests/`;
- опорный стенд для лабораторных, markmap-карт и итоговой проверки.

То есть в рамках курса `shop-demo` — это конкретное приложение и конкретные YAML-артефакты, которые можно применить к любому учебному DKP/Kubernetes-кластеру.

## Структура

- `manifests/kustomization.yaml` — точка входа для развёртывания;
- `manifests/00-namespaces.yaml` — namespace-ы курса;
- `manifests/10-frontend.yaml` — внешний интерфейс;
- `manifests/20-orders.yaml` — сервис заказов;
- `manifests/30-payments.yaml` — сервис платежей;
- `manifests/40-platform-tools.yaml` — технические учётные записи сервисов и служебные объекты.

## Как использовать

### Вариант 1. Как сценарий для чтения

Используйте `shop-demo` как общий предмет обсуждения:
- политики допуска строятся вокруг `frontend`, `orders`, `payments`;
- network policy описывает связи между сервисами;
- IAM-модель проектируется для разработчиков, платформенной команды, аудиторов и CI/CD;
- secret delivery и scanning рассматриваются на тех же объектах.

### Вариант 2. Как реальный учебный стенд

Примените манифесты к учебному кластеру:

```bash
kubectl apply -k shop-demo/manifests/
```

## Важно

Базовые манифесты намеренно упрощены:
- они созданы как стартовая точка для курса;
- они не являются production-ready эталоном;
- часть тем курса как раз и состоит в том, чтобы усилить этот набор приложений с помощью политик допуска, network policy, IAM, secret management и обнаруживающих мер защиты.

## Логика приложения

```text
Пользователь -> frontend -> orders -> payments
                     ^
                     |
               CI/CD и platform tools
```

## Что отрабатывается по главам

### Глава 1
- карта угроз;
- trust boundaries;
- минимальные правила, настройки и проверки безопасности.

### Глава 2
- Pod security;
- минимальные требования допуска;
- rollout policy.

### Глава 3
- east-west segmentation;
- mTLS for critical calls;
- AuthorizationPolicy.

### Глава 4
- роли для людей и автоматизации;
- machine identities;
- review and revoke process.

### Глава 5
- Argo CD как контролируемый доступ к приложениям;
- GitOps-границы, AppProject и RBAC;
- диагностика через UI и логи без прямого kubectl;
- различие между удобным доступом и скрытым административным доступом.

### Глава 6
- secret inventory;
- certificate lifecycle;
- delivery patterns.

### Глава 7
- scanning coverage;
- runtime signals;
- API audit;
- triage process.

### Глава 8
- tenant boundaries;
- Project и ProjectTemplate;
- безопасный стартовый шаблон проекта.

### Глава 9
- compliance reports;
- CIS и DKP CSE;
- что отчёты доказывают, а что нет.

### Глава 10
- NeuVector и внешние security-платформы;
- decision matrix по внешним продуктам;
- критерии пилота и эксплуатационной цены решения.

### Глава 11
- оценка модулей Deckhouse как изменения модели угроз;
- хорошие решения и контрпримеры по `istio`, `ingress-nginx`, registry/cache и monitoring;
- risk matrix: включить, пилотировать или не включать.
