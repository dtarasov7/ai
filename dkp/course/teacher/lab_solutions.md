# Решения и ориентиры для лабораторных работ

Формат ниже — не единственный допустимый ответ. Это набор признаков, по которым преподаватель может принять работу или отправить её на доработку.

## Лабораторная 1. Threat model

Ожидаемые сущности `shop-demo`:

- namespace: `frontend`, `orders`, `payments`, `platform-tools`;
- приложения: `frontend`, `orders-api`, `payments-api`;
- service accounts для приложений и CI/CD;
- сетевые связи: пользователь -> frontend -> orders -> payments;
- доверенные материалы: ingress TLS, service credentials, registry credentials, CI tokens.

Пример рисков и действий:

| Риск | Что делаем | Владелец |
| --- | --- | --- |
| Dev получает cluster-admin | RBAC/user-authz, группы, review | platform |
| Pod запускается от root | PSS/OperationPolicy/securityContext | platform + app owner |
| `frontend` ходит напрямую в `payments` | NetworkPolicy default deny + allow only `orders -> payments` | platform |
| Уязвимый образ попадает в prod | operator-trivy, registry policy, digest pinning | DevSecOps |
| Секрет хранится в Git | Stronghold/secret delivery, secret scanning | app owner |
| Нет audit trail | API audit + log shipping | platform/SOC |

Хороший roadmap:

1. Сейчас: IAM, admission warn, scanning, network inventory.
2. После стабилизации: deny для новых namespace, default deny network, managed secrets.
3. Уровень зрелости: runtime audit, compliance evidence, regular access review, incident drills.

## Лабораторная 2. Pod security

Ожидаемая позиция:

- новые namespace: начинать с `baseline` в warn и быстро переходить к `restricted`, если приложения готовы;
- legacy: сначала inventory, warn, исправление, потом deny;
- PSS не заменяет `OperationPolicy`.

Хороший фрагмент Deployment:

```yaml
securityContext:
  runAsNonRoot: true
  seccompProfile:
    type: RuntimeDefault
containers:
  - name: orders-api
    image: registry.example.com/shop/orders@sha256:1111111111111111111111111111111111111111111111111111111111111111
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 500m
        memory: 512Mi
    readinessProbe:
      httpGet:
        path: /ready
        port: 8080
    livenessProbe:
      httpGet:
        path: /healthz
        port: 8080
```

Слабый ответ: “включить restricted deny на всё” без списка нарушений, owner и rollback.

## Лабораторная 3. Network и mTLS

Ожидаемая матрица:

| Источник | Назначение | Разрешить |
| --- | --- | --- |
| internet / ingress | `frontend` | да, через Ingress |
| `frontend` | `orders` | да |
| `orders` | `payments` | да |
| `frontend` | `payments` | нет |
| любой namespace | `payments` | нет |

Допустимый вариант 1: стандартная `NetworkPolicy` для L3/L4.

Допустимый вариант 2: `CiliumNetworkPolicy`, если нужно FQDN, L7 или расширенный egress.

Для mTLS ожидается: strict mode для выбранного namespace или workload и `AuthorizationPolicy`, где разрешён конкретный ServiceAccount `orders-api`.

Проверка: позитивный тест `orders -> payments` проходит, негативный `frontend -> payments` и Pod из чужого namespace не проходят.

## Лабораторная 4. IAM

Ожидаемая матрица:

| Субъект | Scope | Права |
| --- | --- | --- |
| developers | namespace приложения | read, logs через Argo CD или ограниченный read-only |
| testers | namespace приложения | read, logs, events |
| platform/SRE | cluster | admin по процедуре, break-glass |
| auditors | cluster/namespace | read-only evidence |
| CI/CD | конкретный namespace | apply/update ограниченного набора ресурсов |

Допустимые варианты:

- текущая RBAC-модель DKP, если команда хочет предсказуемый production baseline;
- экспериментальная модель, если это учебный или пилотный контур и есть план миграции.

Слабый ответ: один общий ServiceAccount для CI/CD и людей или постоянный break-glass admin без срока и review.

## Лабораторная 5. Argo CD

Хорошее решение:

- dev/test работают через Argo CD UI;
- разрешено: `applications get`, `logs get`, просмотр history/events;
- запрещено по умолчанию: `exec`, `override`, чужие namespace, cluster-scoped resources;
- `policy.default: role:none`;
- `AppProject` ограничивает repo, namespace и resources.

Допустимые варианты:

1. Argo CD как основной интерфейс диагностики dev/test. Это лучший вариант для кейса пользователя.
2. Прямой `kubectl` остаётся только для platform/SRE и break-glass.
3. Прямой `kubectl` для dev/test допустим только при сильных компенсирующих мерах: short-lived kubeconfig, read-only RBAC, audit, запрет exec/secret, регулярный review.

Неприемлемо: “kubectl убрали”, но через Argo CD выдали `exec`, `override` и широкие sync-права.

## Лабораторная 6. Сертификаты и секреты

Ожидаемый inventory:

| Материал | Хранение | Доставка | Rotation |
| --- | --- | --- | --- |
| Ingress TLS | cert-manager/issuer | Kubernetes Secret для Ingress | auto-renew |
| DB password | Stronghold/Vault | CSI/file или direct access | 30-90 дней |
| API token | Stronghold/Vault | file mount; ENV только для legacy | short-lived |
| CI token | CI secret store/Stronghold | pipeline runtime | по событию и сроку |

Допустимые delivery patterns:

- file mount через CSI/SecretsStoreImport для modern app;
- direct access к secret store для приложений, готовых к short-lived credentials;
- ENV injection только как legacy-компромисс с планом миграции.

Слабый ответ: “секрет лежит в Kubernetes Secret, значит lifecycle закрыт”.

## Лабораторная 7. Scanning и audit

Ожидаемый triage:

| Сигнал | Priority | Первое действие |
| --- | --- | --- |
| Critical CVE в running image | high/critical | проверить exploitability, обновить image, redeploy |
| shell inside container | critical if unexpected | containment, audit user/process, проверить exec и workload |
| suspicious RBAC change | high | найти субъекта, откатить, проверить токены и audit trail |

Supply chain baseline:

- trusted registries;
- запрет `latest`;
- digest pinning для production;
- scanning reports;
- следующий уровень: signatures, SBOM, admission verify.

Слабый ответ: findings переписаны из отчёта, но нет owner, SLA и corrective action.

## Лабораторная 8. Multitenancy

Хороший результат:

- `Project` для `payments`;
- quota, network isolation, pod security profile;
- administrators как группа, а не ручные RoleBinding “потом”;
- описание, что создаёт шаблон;
- plan для изменения `ProjectTemplate`.

Допустимые варианты:

- встроенный `secure` template для быстрого старта;
- custom `ProjectTemplate`, если нужны стандартные labels, logging, scanning, NetworkPolicy и RoleBinding;
- `secure-with-dedicated-nodes`, если есть сильные требования изоляции.

Слабый ответ: вручную создать namespace и назвать это multitenancy.

## Лабораторная 9. Compliance и CSE

Ожидаемый audit pack:

- версия DKP/Kubernetes, release channel;
- `ClusterComplianceReport`;
- `VulnerabilityReport`, `ConfigAuditReport`, `ExposedSecretReport`;
- YAML политик допуска, NetworkPolicy, RBAC, Project/ProjectTemplate;
- список исключений с владельцами и сроками;
- action log по findings.

Правильный вывод: DKP CSE помогает с регуляторной и сертификационной частью, но не заменяет threat model, IAM review, incident response и локальные процессы.

Слабый ответ: “CSE включён, значит безопасно”.

## Лабораторная 10. NeuVector, Luntry и внешние платформы

Ожидаемая decision matrix:

| Задача | DKP built-in | NeuVector | Luntry/другой продукт | Решение |
| --- | --- | --- | --- | --- |
| Image scanning | operator-trivy | registry scanning, risk view | уточнить возможности | built-in достаточно или пилот |
| Runtime protection | runtime-audit-engine/Falco | learning + protect | уточнить eBPF/политики | пилот, если нужен enforcement |
| Network map | Hubble/Istio telemetry | map/policy generation | заявлена network map | пилот при SOC-потребности |
| SOC workflow | audit/log-shipper | rich console/events | уточнить SIEM | зависит от SOC |
| Compliance evidence | Trivy reports/Grafana | reports | уточнить форматы | built-in + внешний при требовании |

Хороший вывод: внешний продукт нужен не “потому что больше функций”, а если есть gap: SOC workflow, behavioral learning, cross-cluster reporting, policy generation, runtime enforcement.

Слабый ответ: включить Protect сразу в production без learning period и rollback.

## Лабораторная 11. Модули Deckhouse как часть модели угроз

Ожидаемая risk matrix:

| Модуль | Закрывает | Новый риск | Guardrails | Решение |
| --- | --- | --- | --- | --- |
| `istio` multicluster | mTLS, service authz | общий trust root, lateral movement | отдельные окружения, explicit AuthorizationPolicy | пилот или включить для конкретного вызова |
| `ingress-nginx` | управляемый вход и TLS | публичная точка атаки, wildcard | отдельные ingressClass, allow-list, запрет опасных annotations | включить с ограничениями |
| `registry`/proxy | контроль supply chain | компрометация внутреннего registry | digest, scanning, push RBAC | включить с процессом scanning |
| monitoring/Upmeter | видимость и SLO | утечка через dashboards/labels | Grafana RBAC, no secrets in labels | включить |

Хорошее решение по Istio: один межкластерный вызов, один ServiceAccount, один namespace, явный owner trust root.

Контрпример: federation dev/test/prod и `principals: ["*"]`.

## Как оценивать лабораторные в целом

Зачёт ставится, если:

- есть конкретные артефакты, а не только рассуждения;
- названы владельцы;
- есть проверка результата;
- есть путь отката или исправления;
- студент понимает новые риски своего решения.

Доработка нужна, если:

- решение строится вокруг “включить модуль” без модели угроз;
- права слишком широкие;
- нет разницы между prod и non-prod;
- нет evidence и lifecycle.
