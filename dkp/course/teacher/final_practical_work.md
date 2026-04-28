# Итоговая практическая работа: версия для преподавателя

## Что должен собрать слушатель

Итоговая работа должна показать, что слушатель умеет собрать минимальный уровень безопасности для `shop-demo`, а не просто повторить названия модулей.

Обязательные блоки:

1. Threat model и границы доверия.
2. Pod security и admission rollout.
3. NetworkPolicy, egress, mTLS и AuthorizationPolicy.
4. IAM для людей и automation.
5. Решение по Argo CD или прямому `kubectl`.
6. Certificate/secret lifecycle.
7. Scanning, runtime audit, API audit и triage-flow.
8. Multitenancy через `Project`/`ProjectTemplate`.
9. Compliance evidence и DKP CSE.
10. Decision matrix по NeuVector/Luntry.
11. Risk matrix по модулям Deckhouse.

## Эталонная структура ответа

### 1. Threat model

Сильный ответ содержит:

- активы: Kubernetes API, workloads, registry, secrets, Git repo, Argo CD, ingress, audit logs;
- границы доверия: user/SSO, CI/CD, cluster API, namespace boundary, service-to-service traffic, secret store, external ingress;
- минимум 10 рисков с владельцами.

Пример:

| Риск | Действие | Владелец |
| --- | --- | --- |
| Dev/test получают лишний kubectl | Argo CD read/logs, no exec, break-glass только SRE | platform |
| `orders` обходит `frontend`/`payments` boundary | NetworkPolicy + AuthorizationPolicy | platform |
| Секреты в Git | Stronghold + secret delivery + secret scanning | app owner |
| Vulnerable image | Trivy + digest pinning + SLA patch | DevSecOps |

### 2. Pod security

Хорошее решение:

- `baseline` в warn для существующих namespace;
- `restricted` для новых namespace или после исправлений;
- `OperationPolicy` для registry, resources, probes, tags;
- исключения только с owner, сроком и причиной.

Допустимые варианты:

- эволюционный rollout warn -> deny;
- сразу deny только для новых проектов, где template уже соответствует требованиям.

Отклонить ответ, если слушатель предлагает “deny + restricted на всё завтра” без inventory и rollback.

### 3. Network и mTLS

Минимальная модель:

- default deny ingress для namespace;
- egress рассматривается отдельно;
- разрешены только `frontend -> orders` и `orders -> payments`;
- mTLS не заменяет NetworkPolicy;
- AuthorizationPolicy разрешает конкретный ServiceAccount.

Допустимые варианты:

- только NetworkPolicy для базовой L3/L4-сегментации;
- CiliumNetworkPolicy, если есть причина использовать L7/FQDN/расширенный egress;
- Istio только для критичных сервисов, если команда готова сопровождать mesh.

### 4. IAM

Сильная матрица:

| Группа | Интерфейс | Scope | Права |
| --- | --- | --- | --- |
| dev | Argo CD | свои приложения | status/logs |
| test | Argo CD | свои приложения | status/logs |
| auditors | Grafana/API read-only | cluster evidence | read-only |
| CI/CD | ServiceAccount | один namespace | apply ограниченных ресурсов |
| platform/SRE | kubectl | cluster | admin по процедуре |

Обязательно: owner групп, review cadence, revoke process, break-glass.

### 5. Argo CD или прямой `kubectl`

Допустимый вариант A: Argo CD как контролируемый доступ.

- dev/test не получают kubeconfig по умолчанию;
- разрешены applications get/logs get;
- запрещены exec, override, secrets, чужие namespace;
- AppProject ограничивает repo, destinations и resource kinds;
- direct kubectl остаётся у platform/SRE.

Допустимый вариант B: прямой `kubectl` с компенсирующими мерами.

- short-lived kubeconfig;
- read-only RBAC;
- запрет `exec`, `port-forward`, `get secrets`;
- audit;
- регулярный access review;
- отдельный break-glass.

Вариант B хуже для кейса, где Argo CD уже закрывает диагностику, но может быть принят, если слушатель явно доказал, что Argo CD создаёт лишний риск в данной среде.

### 6. Secrets and PKI

Сильный ответ разделяет:

- хранение;
- доставку;
- ротацию;
- владельца;
- recovery.

Допустимые варианты:

- cert-manager для ingress/internal TLS;
- Stronghold/Vault-compatible store для секретов;
- CSI/file delivery для modern apps;
- ENV injection только для legacy и с планом миграции;
- direct access к secret store для приложений, готовых к short-lived credentials.

### 7. Scanning, audit и action loop

Слушатель должен показать, что findings приводят к действиям.

Пример:

| Finding | Action |
| --- | --- |
| critical CVE | rebuild image, redeploy, verify report |
| shell inside container | incident-like triage, проверить exec/RBAC, containment |
| suspicious RoleBinding | rollback, identify subject, rotate token if needed |

Слабый ответ: “включили dashboard” без owner и SLA.

### 8. Multitenancy

Хорошее решение:

- новые project spaces через `Project`;
- `ProjectTemplate` задаёт quota, network isolation, labels, admins, monitoring/scanning;
- ручное создание namespace ограничено;
- изменение template проходит review и staging.

Допустимые варианты:

- встроенный secure template;
- custom template;
- dedicated nodes только для реально чувствительных tenant.

### 9. Compliance и DKP CSE

Нужно принять только ответ, где compliance не подменяет security.

Evidence pack:

- DKP/Kubernetes version;
- release channel;
- enabled modules;
- compliance reports;
- vulnerability/config/secret reports;
- YAML policies;
- exceptions with owners;
- manual checks.

DKP CSE: помогает regulated organization, но не заменяет local access review, threat model, incident response и secure delivery.

### 10. NeuVector/Luntry

Ожидаемое решение:

- встроенные DKP-механизмы достаточны для базового уровня;
- NeuVector/Luntry рассматриваются только при явном gap;
- перед enforcement нужен pilot;
- для Luntry отделены публичные факты от вопросов к вендору.

Допустимые варианты:

- не включать внешний продукт, если built-ins достаточно;
- пилот NeuVector на одном namespace;
- пилот Luntry только после ответа по permissions, eBPF, RBAC, data flow, SIEM, updates.

### 11. Risk matrix по модулям Deckhouse

Минимально принять работу можно, если есть три модуля и по каждому:

- закрываемый риск;
- новый риск;
- данные/права;
- blast radius;
- guardrails;
- решение.

Пример:

| Модуль | Решение |
| --- | --- |
| `istio` multicluster | пилот только для `orders -> payments`; не объединять dev/test/prod |
| `ingress-nginx` | включить с отдельным internal/public ingressClass и allow-list |
| `registry` | включить, но scanning/digest/push RBAC обязательны |

## Итоговая шкала проверки

### Зачтено

- Есть все обязательные блоки.
- Есть YAML или чёткие архитектурные фрагменты.
- Есть владельцы и lifecycle.
- Есть варианты решений там, где они действительно возможны.
- Слушатель объясняет новые риски своих решений.

### Зачтено с замечаниями

- Основная логика верная, но не хватает 1-2 практических артефактов.
- Есть YAML, но слабее описаны owners/review/rollback.
- Есть matrix, но недостаточно негативных тестов.

### Требуется доработка

- Ответ построен как список модулей без модели угроз.
- Используются широкие права без обоснования.
- Нет процесса review/rotation/revoke.
- Compliance выдаётся за безопасность.
- Argo CD или внешний security product описан как магическое решение без новых рисков.

## Как проверять фразу “есть жизненный цикл”

Для доступа, проектов, секретов, compliance findings и runtime findings должны быть пять признаков:

1. Владелец: кто отвечает.
2. Периодичность review: когда пересматривается.
3. Событие изменения: что запускает пересмотр вне расписания.
4. Evidence: чем доказывается текущее состояние.
5. Закрытие: как отозвать доступ, удалить проект, ротировать секрет или закрыть finding.

Примеры критериев:

| Область | Что проверить |
| --- | --- |
| Доступ | owner группы, review раз в квартал, revoke при увольнении/смене роли, audit |
| Проекты | ProjectTemplate owner, change review, diff перед rollout, rollback |
| Секреты | TTL, rotation owner, способ доставки, тест ротации, emergency revoke |
| Compliance findings | severity, owner, due date, exception expiry, evidence fix |
| Runtime/API findings | triage SLA, incident owner, corrective action, post-review |

Если хотя бы двух признаков нет, это не lifecycle, а разовая настройка.
