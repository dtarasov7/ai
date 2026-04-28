# Шаблон итоговой проверки курса

## Общая информация

- Команда / слушатель:
- Дата:
- Версия DKP / Kubernetes:
- Среда:
- Используемый профиль курса:

## Описание учебного стенда

- Используемый набор артефактов:
  - `shop-demo/manifests/`
  - лабораторные листы
  - markmap-карты
- Что было взято как исходное состояние:
- Какие допущения были сделаны:

## 1. Threat model и границы доверия

### Основные активы
- 
- 
- 

### Основные доверительные границы
- 
- 
- 

### Топ-риски
| Риск | Вероятность | Влияние | Мера защиты / действие | Владелец |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
|  |  |  |  |  |
|  |  |  |  |  |

## 2. Политики допуска и Pod security

### Выбранный минимальный набор требований
- PSS target:
- namespace exceptions:
- rollout mode:

### Что внедрено
- 
- 
- 

### Какие долги остались
- 
- 

## 3. Network и mTLS

### Разрешённые связи
| Источник | Назначение | Протокол / порт | Почему разрешено |
| --- | --- | --- | --- |
|  |  |  |  |
|  |  |  |  |

### Что внедрено
- default deny ingress:
- default deny egress:
- mTLS:
- AuthorizationPolicy:

## 4. IAM

### Матрица доступа
| Субъект | Scope | Роль | Владелец | Review cadence |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
|  |  |  |  |  |

### Отдельно зафиксировать
- machine identities:
- аварийный доступ (break-glass process):
- revoke process:

### Обязательный capstone-кейс: убрать прямой `kubectl` у dev/test без потери диагностики

См. также отдельные референсные материалы:
- [почти готовый эталонный ответ проверяющего для варианта с Argo CD](reference_argocd_access_solution.md);
- [почти готовый эталонный ответ проверяющего для варианта с прямым `kubectl` и компенсирующими мерами](reference_direct_kubectl_solution.md).

#### Постановка задачи

Для `shop-demo` нужно спроектировать такой контур доступа, при котором разработчики и тестировщики:
- не получают прямой `kubectl` и kubeconfig по умолчанию;
- не получают по умолчанию `kubectl exec`, `port-forward`, `get secrets` и cluster-wide права;
- при этом не теряют удобство базовой диагностики: должны видеть состояние приложения, дерево ресурсов, историю синхронизации, события и логи.

Если для этого используется Argo CD, его нужно описывать не как “ещё один UI”, а как отдельный слой доступа со своими границами, правами и рисками.

#### Что нужно решить по этому кейсу

- Нужен ли в данной среде Argo CD как пользовательская точка доступа, или прямой `kubectl` всё же остаётся оправданным.
- Какие группы работают только через Argo CD, а какие сохраняют прямой доступ к Kubernetes API.
- Какие действия допустимы через Argo CD: просмотр приложений, просмотр логов, синхронизация, rollback.
- Какие действия запрещены по умолчанию: `exec`, `override`, доступ к cluster-scoped ресурсам, работа с чужими namespace.
- Как ограничивается `AppProject`: разрешённые Git-репозитории, namespace, типы ресурсов.
- Где проходит граница между повседневной диагностикой и break-glass-доступом platform/SRE.
- Какой риск создаёт сам Argo CD: UI, API, токены, repo credentials, auto-sync и self-heal.

#### Матрица интерфейсов доступа

| Группа | Через какой интерфейс работает | Что разрешено | Что запрещено по умолчанию | Владелец |
| --- | --- | --- | --- | --- |
| Разработчики |  |  |  |  |
| Тестировщики |  |  |  |  |
| Platform / SRE |  |  |  |  |
| Аудиторы |  |  |  |  |

#### Обязательные артефакты по кейсу

- Короткое архитектурное решение: почему выбран именно такой путь доступа.
- Матрица `subject -> interface -> action -> scope -> owner`.
- Фрагмент политики Argo CD RBAC или явное объяснение, почему Argo CD не используется.
- `AppProject` с ограничением репозитория, namespace и типов ресурсов.
- Описание того, какие действия остаются только у platform/SRE через прямой `kubectl`.
- Описание break-glass-пути, если Argo CD, SSO или GitOps-контур недоступны.
- План проверки: как убедиться, что dev/test видят логи и статус приложения, но не могут сделать `exec` или обойти Git-дисциплину.

#### Учебный baseline для варианта с Argo CD

Ниже не “единственно правильный” production-вариант, а ориентир для capstone. Его можно дорабатывать под свою версию Argo CD, структуру групп и принятую GitOps-модель.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-rbac-cm
  namespace: argocd
data:
  policy.default: role:none
  policy.csv: |
    p, role:shop-dev-readonly, applications, get, shop-demo/*, allow
    p, role:shop-dev-readonly, logs, get, shop-demo/*, allow
    g, shop-dev, role:shop-dev-readonly
    g, shop-test, role:shop-dev-readonly
```

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: shop-demo
  namespace: argocd
spec:
  sourceRepos:
    - https://git.example.org/platform/shop-demo.git
  destinations:
    - namespace: frontend
      server: https://kubernetes.default.svc
    - namespace: orders
      server: https://kubernetes.default.svc
    - namespace: payments
      server: https://kubernetes.default.svc
  clusterResourceWhitelist: []
  namespaceResourceWhitelist:
    - group: apps
      kind: Deployment
    - group: ""
      kind: Service
    - group: ""
      kind: ConfigMap
    - group: networking.k8s.io
      kind: Ingress
  namespaceResourceBlacklist:
    - group: ""
      kind: Secret
```

#### Что считается сильным решением

- Dev/test действительно обходятся без kubeconfig и без прямого `kubectl`.
- Для диагностики им хватает просмотра приложений, событий и логов.
- `exec` не выдан “просто потому что иногда удобно”.
- `policy.default` в Argo CD не даёт широких прав всем аутентифицированным пользователям.
- `AppProject` ограничивает не только namespace, но и источник манифестов, а также набор ресурсов.
- Прямой `kubectl` остаётся только у ограниченного круга platform/SRE и оформлен как отдельный путь.
- Есть явная позиция по `auto-sync` и `self-heal`: где они допустимы, а где нет.
- Показано, как команда будет проверять эту модель после внедрения, а не только как нарисовать её на бумаге.

#### Что считается слабым решением

- “Мы убрали kubectl”, но через Argo CD выдали почти те же права.
- Dev/test могут сделать `exec` или синхронизировать произвольную ревизию без отдельного контроля.
- `AppProject` разрешает cluster-scoped ресурсы или деплой в чужие namespace без явной причины.
- В Git хранятся чувствительные секреты “для простоты GitOps”.
- Break-glass не описан, хотя обычный путь доступа стал зависеть от Argo CD и SSO.
- Непонятно, кто владеет repo credentials, Argo CD RBAC и review этой модели.

## 5. Сертификаты и секреты

### Inventory доверенных материалов
| Материал | Где хранится | Как доставляется | TTL / rotation | Владелец |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
|  |  |  |  |  |

### Что внедрено
- cert-manager:
- Stronghold or equivalent:
- delivery pattern:

## 6. Проверки, сигналы обнаружения и action loop

### Покрытие
- scanning namespaces:
- runtime audit:
- API audit:
- контроль целостности:

### Triage model
| Тип сигнала | Severity | Владелец | Первое действие | Эскалация |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
|  |  |  |  |  |

## 7. Мультиарендность и проектные шаблоны

### Project model
- Какие проекты создаются через `Project`:
- Какие namespace остаются системными или исключениями:
- Как запрещается ручное создание namespace вне проекта:

### ProjectTemplate
| Шаблон | Для кого | Стартовый набор требований безопасности | Владелец | Как обновляется |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
|  |  |  |  |  |

## 8. Compliance, CIS и DKP CSE evidence

### Evidence pack
- CIS dashboard / `ClusterComplianceReport`:
- `VulnerabilityReport` / `ConfigAuditReport` / `ExposedSecretReport`:
- YAML-политики и исключения:
- Ручные проверки, которые не покрываются автоматикой:

### Findings
| Finding | Источник | Риск | Действие | Владелец | Проверка исправления |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |
|  |  |  |  |  |  |

## 9. Внешние security-платформы

### Decision matrix
| Задача | DKP built-in | NeuVector | Luntry / другой продукт | Решение |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
|  |  |  |  |  |

### Пилот и ограничения
- Нужен ли NeuVector:
- Нужен ли Luntry или другой продукт:
- Какие privileged permissions требуются:
- Какой rollback из enforcement-режима:
- Какие вопросы к вендору остаются открытыми:

## 10. Что DKP даёт из коробки, а что делает команда

| DKP built-in | Решение команды / процесс |
| --- | --- |
|  |  |
|  |  |
|  |  |

## 11. Итоговая самооценка зрелости

Оцените по шкале от 0 до 3:
- 0 — отсутствует;
- 1 — существует как идея или ручная практика;
- 2 — внедрено частично и работает не везде;
- 3 — внедрено системно и поддерживается процессом.

| Область | Оценка | Комментарий |
| --- | --- | --- |
| Threat model |  |  |
| Минимальные требования допуска |  |  |
| Network segmentation |  |  |
| IAM |  |  |
| Контролируемый доступ к приложениям (Argo CD / граница с kubectl) |  |  |
| Secrets and PKI |  |  |
| Проверки и сигналы обнаружения |  |  |
| Multitenancy и ProjectTemplate |  |  |
| Compliance evidence |  |  |
| External security platform decision |  |  |
| Incident action loop |  |  |

## 12. Критерии приёмки

Проверяющий отмечает:
- [ ] Есть явная threat model и границы доверия (trust boundaries).
- [ ] Минимальные требования допуска описаны и имеют план rollout.
- [ ] Сетевые связи ограничены по принципу explicit allow.
- [ ] Для критичных сервисов описаны правила доступа на основе ServiceAccount, а не IP-адреса.
- [ ] Люди и автоматизация разделены в модели доступа.
- [ ] Для dev/test отдельно решён вопрос: нужен ли прямой kubectl или достаточно контролируемого доступа через Argo CD.
- [ ] Если используется Argo CD, доступ через него не включает `exec` и `override` по умолчанию, а `AppProject` ограничивает repo, namespace и ресурсы.
- [ ] Для секретов и сертификатов есть lifecycle, а не только хранение.
- [ ] Новые project spaces создаются через `Project`/`ProjectTemplate`, а не вручную.
- [ ] Compliance findings разобраны с владельцами и действиями.
- [ ] По DKP CSE указано, что она даёт и чего не заменяет.
- [ ] Решение по NeuVector/Luntry принято через decision matrix, а не по списку функций.
- [ ] Findings приводят к действиям, а не просто копятся.
- [ ] Показана граница между built-in DKP и operational responsibility команды.

## 13. Решение проверяющего

- Статус:
  - [ ] зачтено
  - [ ] зачтено с замечаниями
  - [ ] требуется доработка

- Сильные стороны:
  - 
  - 

- Замечания:
  - 
  - 

- Следующие шаги:
  - 
  - 
