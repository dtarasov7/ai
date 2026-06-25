# Техническое задание и архитектурное решение

## Локальный AI-помощник ИТ-сопровождения, SRE и DevOps для раннего обнаружения ошибок и сбоев

Версия: 0.1
Целевой язык реализации: Python
Целевой режим эксплуатации: изолированный контур, локальные open-source LLM, уведомления только по электронной почте
Рабочее название: **SRE-AI Assistant**

---

## 1. Назначение системы

### 1.1. Цель

Создать программный комплекс на Python, выполняющий роль AI-помощника для ИТ-сопровождения, SRE и DevOps-команд. Система должна автоматически анализировать алерты, метрики, логи, события инфраструктуры и состояние сервисов, выявлять ранние признаки ошибок и деградаций, формировать гипотезы о причинах инцидентов и отправлять структурированные email-уведомления ответственным группам.

Решение должно работать в изолированном окружении, без обращения к внешним LLM/API, с использованием локальных open-source моделей и read-only интеграций с инфраструктурными системами.

### 1.2. Ключевой принцип

Система не должна самостоятельно выполнять изменяющие действия в инфраструктуре. На первом этапе допускаются только:

* чтение метрик, логов, событий и конфигураций;
* корреляция данных;
* формирование выводов;
* генерация рекомендаций;
* отправка email-уведомлений.

Любые remediation-действия, такие как перезапуск pod, изменение ingress, изменение конфигурации HAProxy/Nginx, изменение правил Consul/Vault/PostgreSQL/Ceph/Kafka, должны оставаться ручными и выполняться человеком.

---

## 2. Область применения

Система предназначена для эксплуатации в инфраструктуре, включающей:

* Kubernetes;
* Deckhouse Kubernetes Platform / DKP;
* Prometheus;
* Alertmanager;
* Grafana;
* OpenSearch;
* Kafka;
* Keycloak;
* Nginx;
* Angie;
* HAProxy;
* Ceph;
* Vault;
* RED OS;
* ALT Linux;
* Astra Linux;
* Consul;
* Redis;
* PostgreSQL.

---

## 3. Основные сценарии использования

### 3.1. Alert-driven расследование

1. Alertmanager получает алерт от Prometheus.
2. Alertmanager отправляет webhook в SRE-AI Assistant.
3. Система нормализует алерт.
4. Классификатор определяет домен проблемы: Kubernetes, БД, сеть, хранилище, безопасность, брокер сообщений, ОС, ingress/proxy.
5. Agent Orchestrator выбирает набор read-only инструментов.
6. Система собирает релевантные данные:

   * метрики из Prometheus;
   * логи из OpenSearch;
   * события Kubernetes;
   * состояние pod/deployment/node;
   * состояние Kafka/Ceph/PostgreSQL/Redis/Vault/Consul;
   * связанные дашборды Grafana;
   * исторические похожие инциденты.
7. Локальная LLM строит RCA-гипотезу.
8. Верификатор проверяет, достаточно ли данных.
9. Если данных недостаточно, выполняется дополнительный сбор.
10. Итог отправляется email-уведомлением.

### 3.2. Scheduled health checks

Система по расписанию выполняет проверки:

* доступность критичных сервисов;
* рост ошибок 5xx;
* рост latency;
* рост restart count;
* disk pressure / memory pressure / pid pressure;
* деградация Ceph;
* лаги Kafka consumer group;
* рост slow queries PostgreSQL;
* рост ошибок Keycloak;
* проблемы с Vault seal/unseal/token;
* недоступность Consul leader;
* рост eviction в Kubernetes;
* рост rejected connections в HAProxy/Nginx/Angie.

### 3.3. Раннее обнаружение деградаций

Система должна не только реагировать на уже сработавшие алерты, но и выявлять предвестники:

* устойчивый рост latency;
* увеличение error budget burn rate;
* рост количества warning-событий Kubernetes;
* частые OOMKilled;
* рост PostgreSQL locks/deadlocks;
* увеличение Kafka consumer lag;
* рост Ceph slow ops;
* снижение available storage;
* частые 401/403 в Keycloak;
* рост upstream timeout в Nginx/Angie/HAProxy;
* рост CPU throttling в контейнерах.

### 3.4. Интерактивный режим

На последующих этапах допускается CLI/API-режим:

```bash
sre-ai ask "Почему растёт latency у сервиса billing-api?"
sre-ai investigate --alert-id <id>
sre-ai healthcheck --service keycloak
```

Для MVP интерактивный режим можно реализовать только как CLI для администраторов.

---

## 4. Функциональные требования

### FR-001. Приём алертов

Система должна принимать алерты через HTTP webhook от Alertmanager.

Минимальные поля:

* alertname;
* status;
* severity;
* labels;
* annotations;
* startsAt;
* endsAt;
* generatorURL;
* fingerprint;
* receiver;
* groupLabels;
* commonLabels;
* commonAnnotations.

### FR-002. Нормализация событий

Система должна приводить события разных источников к единой внутренней модели:

```yaml
IncidentEvent:
  id: string
  source: prometheus|manual|schedule|opensearch|k8s
  status: firing|resolved|suspected|warning
  severity: critical|high|medium|low|info
  service: string
  namespace: string
  cluster: string
  component: string
  labels: object
  annotations: object
  started_at: datetime
  received_at: datetime
  correlation_key: string
```

### FR-003. Дедупликация

Система должна исключать повторную обработку одинаковых алертов в пределах настраиваемого окна времени.

Параметры:

```yaml
deduplication:
  enabled: true
  window_minutes: 30
  key_fields:
    - cluster
    - namespace
    - alertname
    - service
    - instance
```

### FR-004. Корреляция событий

Система должна объединять связанные события:

* один namespace;
* один service;
* один node;
* один deployment;
* один storage pool;
* одна Kafka consumer group;
* один PostgreSQL instance;
* один ingress/upstream;
* близость по времени.

### FR-005. Интеграция с Prometheus

Система должна выполнять read-only PromQL-запросы:

* instant query;
* range query;
* query metadata;
* получение активных алертов;
* получение правил алертинга при наличии доступа.

Примеры запросов:

```promql
up
rate(http_requests_total{status=~"5.."}[5m])
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))
sum(rate(container_cpu_cfs_throttled_seconds_total[5m])) by (pod, namespace)
kube_pod_container_status_restarts_total
kube_node_status_condition
```

### FR-006. Интеграция с Grafana

Система должна уметь:

* искать дашборды по service/namespace/component;
* читать структуру dashboard JSON;
* извлекать panel queries;
* использовать panel queries как дополнительный источник PromQL/OpenSearch-запросов;
* включать ссылки на Grafana dashboards в email-отчёт.

### FR-007. Интеграция с OpenSearch

Система должна выполнять read-only поиск логов:

* по namespace;
* по pod;
* по container;
* по service;
* по trace_id/request_id, если доступны;
* по временным окнам вокруг алерта;
* по severity/error keywords;
* по конкретным индексам.

Примеры шаблонов:

```json
{
  "query": {
    "bool": {
      "must": [
        {"match": {"kubernetes.namespace": "{{ namespace }}"}},
        {"range": {"@timestamp": {"gte": "now-30m", "lte": "now"}}}
      ],
      "should": [
        {"match_phrase": {"message": "error"}},
        {"match_phrase": {"message": "exception"}},
        {"match_phrase": {"message": "timeout"}},
        {"match_phrase": {"message": "connection refused"}}
      ]
    }
  },
  "size": 100
}
```

### FR-008. Интеграция с Kubernetes

Система должна выполнять только read-only операции:

* get pods;
* describe pods;
* get events;
* get deployments/statefulsets/daemonsets;
* get nodes;
* get services/endpoints/ingress;
* get jobs/cronjobs;
* get configmaps/secrets metadata без чтения секретных значений;
* get resource usage, если доступен metrics-server;
* получение container restart reason;
* получение last state;
* получение image/version.

Запрещено:

* delete pod;
* scale deployment;
* patch/edit/apply;
* exec в pod без отдельного разрешения;
* чтение значений Secret;
* port-forward в production namespace.

### FR-009. Интеграция с Deckhouse / DKP

Система должна учитывать специфику DKP:

* namespaces Deckhouse;
* состояние deckhouse modules;
* события control-plane;
* состояние CNI/CSI/ingress-nginx, если используется;
* мониторинг DKP-компонентов через Prometheus/Grafana;
* health-check системных компонентов платформы.

### FR-010. Интеграция с Kafka

Система должна собирать:

* broker availability;
* controller status;
* ISR shrink/expand;
* under-replicated partitions;
* offline partitions;
* consumer lag;
* rebalance events;
* disk usage;
* broker logs;
* ошибки авторизации и TLS/SASL.

### FR-011. Интеграция с Keycloak

Система должна анализировать:

* доступность realm endpoints;
* ошибки login/token/refresh;
* рост 401/403;
* проблемы с LDAP/IdP;
* состояние PostgreSQL, используемого Keycloak;
* JVM metrics;
* HTTP latency;
* ошибки ingress/proxy перед Keycloak.

### FR-012. Интеграция с Nginx / Angie / HAProxy

Система должна анализировать:

* 4xx/5xx;
* upstream timeout;
* connection refused;
* TLS handshake errors;
* reload failures;
* active connections;
* queue;
* backend health;
* latency by upstream;
* saturation worker connections;
* ошибки конфигурации.

### FR-013. Интеграция с Ceph

Система должна анализировать:

* cluster health;
* OSD up/in;
* PG states;
* slow ops;
* nearfull/full;
* degraded/misplaced objects;
* MON quorum;
* MGR status;
* RBD/CephFS issues;
* latency storage pool.

### FR-014. Интеграция с Vault

Система должна анализировать:

* sealed/unsealed;
* active/standby;
* token renewal errors;
* audit log errors;
* auth backend failures;
* storage backend issues;
* latency;
* expiration leases.

### FR-015. Интеграция с Consul

Система должна анализировать:

* leader availability;
* raft peers;
* service health checks;
* DNS/query errors;
* catalog inconsistencies;
* latency;
* ACL errors.

### FR-016. Интеграция с Redis

Система должна анализировать:

* availability;
* memory fragmentation;
* evictions;
* rejected connections;
* replication lag;
* Sentinel/Cluster state;
* slowlog;
* blocked clients.

### FR-017. Интеграция с PostgreSQL

Система должна анализировать:

* availability;
* replication lag;
* locks/deadlocks;
* slow queries;
* connection saturation;
* bloat;
* checkpoint pressure;
* vacuum/autovacuum issues;
* WAL growth;
* disk usage;
* errors in logs.

### FR-018. Интеграция с Linux OS

Для RED OS, ALT Linux, Astra Linux система должна поддерживать сбор:

* системных метрик через node_exporter;
* journald logs, если они централизованы в OpenSearch;
* состояние systemd services через заранее разрешённые read-only команды;
* disk usage;
* inode usage;
* network errors;
* oom-killer events;
* kernel warnings;
* SELinux/AppArmor/мандатные ограничения при наличии.

### FR-019. Локальная LLM

Система должна работать с локальным LLM endpoint через OpenAI-compatible API или собственный адаптер.

Рекомендуемые режимы:

* vLLM для GPU-инференса;
* Ollama для простого стенда/MVP;
* llama.cpp/llama-cpp-python для CPU/GGUF-моделей;
* отдельный embedding model для RAG;
* отдельный reranker model при необходимости.

### FR-020. Agentic-loop

Система должна реализовать итеративный цикл расследования:

1. понять алерт;
2. выбрать план диагностики;
3. вызвать read-only tools;
4. сжать и нормализовать результаты;
5. сформировать гипотезы;
6. проверить гипотезы дополнительными запросами;
7. оценить уверенность;
8. сформировать итог.

### FR-021. Runbook RAG

Система должна поддерживать базу знаний:

* runbooks;
* инструкции эксплуатации;
* known errors;
* postmortems;
* архитектурные схемы;
* регламенты эскалации;
* SLO/SLA;
* карты сервисов;
* ownership matrix.

Форматы источников:

* Markdown;
* YAML;
* JSON;
* HTML;
* PDF на последующих этапах;
* Git repository mirror;
* локальная директория.

### FR-022. Email-only уведомления

Система должна отправлять уведомления только по email.

Запрещённые каналы для целевого контура:

* Slack;
* Telegram;
* Mattermost;
* Microsoft Teams;
* PagerDuty;
* OpsGenie;
* внешние SaaS.

Email должен содержать:

* тему;
* severity;
* service;
* cluster;
* namespace;
* краткое резюме;
* вероятную причину;
* доказательства;
* затронутые компоненты;
* ссылки на Grafana/OpenSearch/Kubernetes dashboard;
* рекомендации;
* команды для ручной диагностики;
* уровень уверенности;
* список данных, которые не удалось получить;
* ID расследования.

### FR-023. Хранилище расследований

Система должна сохранять:

* входной алерт;
* собранные данные;
* использованные tools;
* LLM prompts/responses;
* финальный отчёт;
* статусы;
* время выполнения;
* ошибки;
* confidence score;
* feedback оператора.

Рекомендуемое хранилище:

* PostgreSQL для структурированных данных;
* S3-compatible/minio или файловое хранилище для больших артефактов;
* OpenSearch для полнотекстового поиска расследований, если допустимо.

### FR-024. Web UI

Для MVP Web UI необязателен. Для промышленной версии рекомендуется внутренний UI:

* список расследований;
* карточка инцидента;
* timeline;
* найденные доказательства;
* история LLM-выводов;
* feedback;
* настройки интеграций;
* просмотр health checks.

UI не должен иметь возможности выполнять изменяющие действия в инфраструктуре.

---

## 5. Нефункциональные требования

### NFR-001. Изоляция

Система должна работать без доступа в Интернет.

Требования:

* все Python packages должны поставляться через внутренний репозиторий;
* container images должны храниться во внутреннем registry;
* LLM models должны храниться локально;
* embedding models должны храниться локально;
* внешние telemetry endpoints должны быть отключены;
* DNS egress наружу должен быть запрещён;
* egress network policy должна разрешать только внутренние endpoints и SMTP relay.

### NFR-002. Безопасность

Обязательные меры:

* read-only RBAC;
* отдельный Kubernetes ServiceAccount;
* отдельные service credentials на каждую интеграцию;
* хранение секретов в Vault или Kubernetes Secret с шифрованием;
* запрет логирования секретов;
* маскирование токенов, паролей, cookies, Authorization headers;
* audit log всех tool-вызовов;
* allowlist команд;
* запрет произвольного shell;
* ограничение размера данных, передаваемых в LLM;
* prompt-injection protection.

### NFR-003. Производительность

Целевые показатели:

* приём webhook: до 1 секунды;
* постановка задачи в очередь: до 3 секунд;
* первичный отчёт по critical alert: до 2 минут;
* полное расследование: до 10 минут;
* scheduled health check: по расписанию без влияния на production;
* одновременные расследования: настраиваемо, минимум 5 для MVP.

### NFR-004. Надёжность

Система должна:

* сохранять входящие алерты до обработки;
* поддерживать retry;
* не терять задачи при рестарте;
* иметь dead-letter queue;
* иметь собственные метрики;
* иметь health/readiness probes;
* уметь деградировать без LLM, отправляя хотя бы технический отчёт;
* не блокировать Alertmanager.

### NFR-005. Наблюдаемость самой системы

Система должна экспортировать Prometheus-метрики:

```text
sre_ai_incidents_total
sre_ai_investigation_duration_seconds
sre_ai_tool_calls_total
sre_ai_tool_errors_total
sre_ai_llm_tokens_total
sre_ai_llm_latency_seconds
sre_ai_email_sent_total
sre_ai_email_failed_total
sre_ai_confidence_score
sre_ai_queue_depth
```

### NFR-006. Совместимость с российскими Linux-дистрибутивами

Система должна поддерживать запуск на:

* RED OS;
* ALT Linux;
* Astra Linux.

Минимальные требования:

* Python 3.11+;
* systemd unit для VM/bare metal deployment;
* containerized deployment для Kubernetes;
* отсутствие обязательной зависимости от внешних SaaS;
* возможность работы через внутренние CA;
* поддержка корпоративного SMTP.

---

## 6. Архитектура решения

### 6.1. Общая схема компонентов

Основные компоненты:

1. **Webhook API**
   Принимает алерты от Alertmanager и ручные запросы.

2. **Event Normalizer**
   Приводит события к единой модели.

3. **Correlation Engine**
   Дедуплицирует и группирует связанные события.

4. **Investigation Orchestrator**
   Управляет расследованием.

5. **Tool Registry**
   Хранит список доступных read-only инструментов.

6. **Tool Executor**
   Выполняет безопасные запросы к Prometheus, OpenSearch, Kubernetes, Grafana и другим системам.

7. **Context Builder**
   Сжимает, фильтрует и структурирует результаты.

8. **RAG Service**
   Ищет релевантные runbooks и postmortems.

9. **Local LLM Gateway**
   Абстрагирует vLLM/Ollama/llama.cpp.

10. **Verifier / Critic**
    Проверяет выводы LLM на полноту, противоречия и наличие доказательств.

11. **Report Generator**
    Формирует email-отчёт.

12. **Email Notifier**
    Отправляет уведомления через SMTP.

13. **Storage**
    Хранит события, расследования, отчёты, feedback.

14. **Scheduler**
    Запускает регулярные health checks.

15. **Admin CLI / API**
    Позволяет администраторам запускать расследования вручную.

---

## 7. PlantUML: контекстная диаграмма

```plantuml
@startuml
title SRE-AI Assistant - Контекстная диаграмма

actor "SRE / DevOps\nоператор" as SRE
actor "Дежурная группа\nEmail recipients" as MailUsers

rectangle "Изолированный контур" {
  rectangle "SRE-AI Assistant\nPython service" as AI

  database "PostgreSQL\nInvestigation DB" as PG
  database "Vector DB\nRunbooks / Postmortems" as VDB
  rectangle "Local LLM Runtime\nvLLM / Ollama / llama.cpp" as LLM
  rectangle "SMTP Relay\nкорпоративная почта" as SMTP

  rectangle "Prometheus / Alertmanager" as Prom
  rectangle "Grafana" as Grafana
  rectangle "OpenSearch" as OS
  rectangle "Kubernetes / DKP" as K8S
  rectangle "Kafka" as Kafka
  rectangle "Keycloak" as Keycloak
  rectangle "Nginx / Angie / HAProxy" as Proxy
  rectangle "Ceph" as Ceph
  rectangle "Vault" as Vault
  rectangle "Consul" as Consul
  rectangle "Redis" as Redis
  rectangle "PostgreSQL services" as AppPG
  rectangle "Linux hosts\nRED OS / ALT / Astra" as Linux
}

Prom --> AI : webhook alerts
AI --> Prom : read-only PromQL
AI --> Grafana : read-only dashboards API
AI --> OS : read-only logs search
AI --> K8S : read-only Kubernetes API
AI --> Kafka : read-only metrics/API/logs
AI --> Keycloak : read-only metrics/logs
AI --> Proxy : metrics/logs
AI --> Ceph : read-only status/metrics
AI --> Vault : read-only health/metrics
AI --> Consul : read-only health/API
AI --> Redis : read-only metrics/info
AI --> AppPG : read-only metrics/logs
AI --> Linux : read-only metrics/logs

AI --> PG : investigations
AI --> VDB : semantic search
AI --> LLM : local inference only
AI --> SMTP : send email reports
SMTP --> MailUsers : email

SRE --> AI : CLI/API ask/investigate
AI --> SRE : report/status

@enduml
```

---

## 8. PlantUML: компонентная архитектура

```plantuml
@startuml
title SRE-AI Assistant - Компонентная архитектура

package "API Layer" {
  [Webhook API\nFastAPI] as Webhook
  [Admin API / CLI] as Admin
}

package "Event Processing" {
  [Event Normalizer] as Normalizer
  [Deduplication] as Dedup
  [Correlation Engine] as Corr
  queue "Task Queue\nRedis/RQ/Celery/Kafka optional" as Queue
}

package "Investigation Core" {
  [Investigation Orchestrator] as Orch
  [Planner] as Planner
  [Tool Registry] as Registry
  [Tool Executor] as Executor
  [Context Builder] as Context
  [Evidence Store] as Evidence
  [Verifier / Critic] as Critic
  [Report Generator] as Report
}

package "AI Layer" {
  [LLM Gateway] as Gateway
  [Embedding Service] as Emb
  [Reranker optional] as Reranker
  [Prompt Templates] as Prompt
}

package "Knowledge" {
  database "Vector DB\nQdrant/pgvector" as Vector
  database "Runbook Repository\nGit mirror / FS" as Runbooks
}

package "Integrations" {
  [Prometheus Adapter] as Prom
  [Grafana Adapter] as Grafana
  [OpenSearch Adapter] as OS
  [Kubernetes Adapter] as K8S
  [Kafka Adapter] as Kafka
  [Keycloak Adapter] as Keycloak
  [Proxy Adapter] as Proxy
  [Ceph Adapter] as Ceph
  [Vault Adapter] as Vault
  [Consul Adapter] as Consul
  [Redis Adapter] as Redis
  [PostgreSQL Adapter] as PGAdapter
  [Linux Adapter] as Linux
}

package "Storage / Notifications" {
  database "PostgreSQL\nmetadata" as DB
  database "Object/File Storage\nlarge artifacts" as Obj
  [Email Notifier\nSMTP only] as Email
}

Webhook --> Normalizer
Admin --> Normalizer
Normalizer --> Dedup
Dedup --> Corr
Corr --> Queue
Queue --> Orch

Orch --> Planner
Planner --> Registry
Registry --> Executor
Executor --> Prom
Executor --> Grafana
Executor --> OS
Executor --> K8S
Executor --> Kafka
Executor --> Keycloak
Executor --> Proxy
Executor --> Ceph
Executor --> Vault
Executor --> Consul
Executor --> Redis
Executor --> PGAdapter
Executor --> Linux

Executor --> Evidence
Evidence --> Context
Context --> Gateway
Gateway --> Prompt
Gateway --> Critic
Context --> Emb
Emb --> Vector
Runbooks --> Vector
Vector --> Reranker
Reranker --> Context

Critic --> Orch
Orch --> Report
Report --> Email

Orch --> DB
Evidence --> DB
Evidence --> Obj
Report --> DB

@enduml
```

---

## 9. PlantUML: последовательность расследования алерта

```plantuml
@startuml
title Последовательность alert-driven расследования

participant Alertmanager
participant "Webhook API" as API
participant "Event Normalizer" as Norm
participant "Correlation Engine" as Corr
queue "Task Queue" as Q
participant "Investigation Orchestrator" as Orch
participant "Tool Executor" as Tool
participant "Prometheus" as Prom
participant "OpenSearch" as OS
participant "Kubernetes API" as K8S
participant "RAG Service" as RAG
participant "Local LLM" as LLM
participant "Verifier" as Verifier
participant "Email Notifier" as Email
database "Investigation DB" as DB

Alertmanager -> API : POST /webhooks/alertmanager
API -> Norm : normalize(payload)
Norm -> Corr : correlate(event)
Corr -> Q : enqueue(investigation_task)
Q -> Orch : consume task
Orch -> DB : create investigation

Orch -> Tool : collect baseline evidence
Tool -> Prom : PromQL range/instant queries
Prom --> Tool : metrics
Tool -> OS : log search by labels/time window
OS --> Tool : log excerpts
Tool -> K8S : get pods/events/deployments/nodes
K8S --> Tool : k8s state/events

Tool --> Orch : evidence bundle
Orch -> RAG : search runbooks/postmortems
RAG --> Orch : relevant docs

Orch -> LLM : analyze alert + evidence + runbooks
LLM --> Orch : hypotheses + next checks

loop until confidence threshold or max iterations
  Orch -> Tool : additional targeted checks
  Tool --> Orch : evidence
  Orch -> LLM : refine RCA
  LLM --> Orch : updated RCA
end

Orch -> Verifier : verify claims against evidence
Verifier --> Orch : confidence + issues

Orch -> DB : save final result
Orch -> Email : send structured report
Email --> Orch : delivery status

@enduml
```

---

## 10. PlantUML: state machine расследования

```plantuml
@startuml
title Состояния расследования инцидента

[*] --> Received

Received --> Normalized : payload valid
Received --> Rejected : invalid payload

Normalized --> Deduplicated
Deduplicated --> Suppressed : duplicate within window
Deduplicated --> Correlated : new or updated incident

Correlated --> Queued
Queued --> Running

Running --> CollectingEvidence
CollectingEvidence --> Analyzing
Analyzing --> NeedMoreData : confidence < threshold
NeedMoreData --> CollectingEvidence : additional tools

Analyzing --> Verifying : confidence >= threshold
Verifying --> Reporting : claims verified
Verifying --> PartialReport : insufficient evidence

PartialReport --> EmailSent
Reporting --> EmailSent

EmailSent --> Completed
Suppressed --> Completed
Rejected --> [*]
Completed --> [*]

Running --> Failed : unrecoverable error
Failed --> EmailSent : send degraded report
Failed --> [*]

@enduml
```

---

## 11. PlantUML: изоляция и безопасность

```plantuml
@startuml
title Изоляция, read-only доступ и запрет внешних соединений

rectangle "Kubernetes Namespace: sre-ai" {
  rectangle "sre-ai-api" as API
  rectangle "sre-ai-worker" as Worker
  rectangle "sre-ai-scheduler" as Scheduler
  rectangle "llm-runtime" as LLM
  rectangle "vector-db" as VDB
  rectangle "postgres-investigation-db" as DB
}

rectangle "Allowed internal services" {
  rectangle "Prometheus" as Prom
  rectangle "Grafana" as Grafana
  rectangle "OpenSearch" as OS
  rectangle "Kubernetes API" as K8S
  rectangle "SMTP Relay" as SMTP
  rectangle "Vault" as Vault
}

cloud "Internet" as Internet

API --> Worker : internal queue
Worker --> LLM : local inference
Worker --> VDB : semantic search
Worker --> DB : investigation data
Worker --> Prom : read-only
Worker --> Grafana : read-only
Worker --> OS : read-only
Worker --> K8S : read-only RBAC
Worker --> Vault : read-only secrets access
Worker --> SMTP : send email only

API -[#red,dashed]-> Internet : denied by NetworkPolicy
Worker -[#red,dashed]-> Internet : denied by NetworkPolicy
LLM -[#red,dashed]-> Internet : denied by NetworkPolicy

note right of K8S
RBAC:
get/list/watch only
no patch/update/delete
no secrets values
no exec by default
end note

note bottom of Worker
Tool execution:
allowlist only
timeouts
memory limits
output limits
secret masking
audit log
end note

@enduml
```

---

## 12. Логическая модель данных

### 12.1. Таблица incidents

```sql
create table incidents (
    id uuid primary key,
    correlation_key text not null,
    status text not null,
    severity text not null,
    source text not null,
    cluster text,
    namespace text,
    service text,
    component text,
    alertname text,
    fingerprint text,
    started_at timestamptz,
    received_at timestamptz not null,
    completed_at timestamptz,
    confidence numeric(5,2),
    summary text,
    root_cause text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
```

### 12.2. Таблица incident_events

```sql
create table incident_events (
    id uuid primary key,
    incident_id uuid references incidents(id),
    raw_payload jsonb not null,
    normalized_payload jsonb not null,
    source text not null,
    received_at timestamptz not null default now()
);
```

### 12.3. Таблица tool_calls

```sql
create table tool_calls (
    id uuid primary key,
    incident_id uuid references incidents(id),
    tool_name text not null,
    input_hash text not null,
    input_sanitized jsonb,
    output_summary text,
    output_ref text,
    status text not null,
    duration_ms integer,
    error text,
    created_at timestamptz not null default now()
);
```

### 12.4. Таблица llm_calls

```sql
create table llm_calls (
    id uuid primary key,
    incident_id uuid references incidents(id),
    model_name text not null,
    prompt_template text not null,
    prompt_hash text not null,
    input_tokens integer,
    output_tokens integer,
    latency_ms integer,
    response_text text,
    created_at timestamptz not null default now()
);
```

### 12.5. Таблица reports

```sql
create table reports (
    id uuid primary key,
    incident_id uuid references incidents(id),
    subject text not null,
    body_text text not null,
    body_html text,
    recipients text[] not null,
    delivery_status text not null,
    created_at timestamptz not null default now()
);
```

---

## 13. Модульная структура Python-проекта

```text
sre_ai_assistant/
  pyproject.toml
  README.md
  alembic.ini

  src/sre_ai/
    main.py

    api/
      app.py
      routes_webhook.py
      routes_admin.py
      schemas.py
      auth.py

    core/
      config.py
      logging.py
      security.py
      masking.py
      exceptions.py

    events/
      models.py
      normalizer.py
      dedup.py
      correlator.py

    queue/
      broker.py
      tasks.py
      retry.py

    investigation/
      orchestrator.py
      planner.py
      state_machine.py
      evidence.py
      context_builder.py
      verifier.py
      scoring.py

    llm/
      gateway.py
      openai_compatible.py
      prompt_templates/
        incident_analysis.md
        hypothesis_check.md
        final_report.md

    rag/
      indexer.py
      chunker.py
      embeddings.py
      retriever.py
      reranker.py

    tools/
      base.py
      registry.py
      executor.py
      policies.py

      prometheus.py
      grafana.py
      opensearch.py
      kubernetes.py
      kafka.py
      keycloak.py
      proxy.py
      ceph.py
      vault.py
      consul.py
      redis.py
      postgres.py
      linux.py

    notifications/
      email.py
      templates/
        incident_text.j2
        incident_html.j2

    storage/
      db.py
      models.py
      repositories.py
      migrations/

    scheduler/
      healthchecks.py
      jobs.py

    observability/
      metrics.py
      tracing.py

    cli/
      main.py

  tests/
    unit/
    integration/
    e2e/

  deploy/
    helm/
    manifests/
    systemd/
    docker/
```

---

## 14. Технологический стек

### 14.1. Backend

* Python 3.11 или 3.12;
* FastAPI для webhook/admin API;
* Pydantic для схем;
* SQLAlchemy 2.x;
* Alembic;
* PostgreSQL;
* Redis/RQ или Celery для очередей;
* APScheduler или Celery Beat для расписаний;
* Jinja2 для email-шаблонов;
* prometheus-client для метрик;
* structlog или стандартный logging с JSON formatter.

### 14.2. LLM runtime

Рекомендуемые варианты:

#### Вариант A. vLLM

Подходит для production GPU-инференса.

Плюсы:

* высокая производительность;
* OpenAI-compatible endpoint;
* batch serving;
* удобная замена backend без изменения бизнес-логики.

#### Вариант B. Ollama

Подходит для MVP и стендов.

Плюсы:

* простота установки;
* удобное управление моделями;
* подходит для небольших команд и пилотного запуска.

#### Вариант C. llama.cpp / llama-cpp-python

Подходит для CPU-only или ограниченных ресурсов.

Плюсы:

* GGUF-модели;
* меньше требований к GPU;
* удобно для полностью автономных стендов.

### 14.3. Embeddings / RAG

Варианты:

* Qdrant;
* pgvector;
* OpenSearch vector search, если уже разрешено использовать OpenSearch;
* Chroma для MVP.

Рекомендуется для production:

* pgvector, если хочется минимизировать количество компонентов;
* Qdrant, если нужна отдельная производительная vector DB.

---

## 15. Рекомендуемые локальные модели

Окончательный выбор должен быть сделан после benchmark на ваших runbooks и реальных инцидентах.

### 15.1. Основная instruct-модель

Критерии:

* хорошее понимание русского и английского;
* способность работать с JSON/YAML/logs;
* устойчивость к длинному контексту;
* tool-use/function calling;
* возможность локального запуска.

Кандидаты:

* Qwen2.5/Qwen3 Instruct;
* Llama 3.1/3.3 Instruct;
* Mistral/Mixtral;
* DeepSeek-Coder / Devstral-подобные модели для технического анализа;
* специализированные code/instruct модели для анализа логов и конфигураций.

### 15.2. Embedding model

Критерии:

* русский + английский;
* технические тексты;
* runbooks;
* YAML/Markdown.

Кандидаты:

* bge-m3;
* multilingual-e5;
* jina embeddings multilingual;
* Qwen embeddings.

### 15.3. Reranker

Кандидаты:

* bge-reranker;
* jina reranker;
* lightweight cross-encoder.

### 15.4. Минимальный профиль железа

#### MVP

* 1 GPU 24 GB VRAM или CPU-only с quantized model;
* 16–32 GB RAM;
* PostgreSQL;
* Redis;
* 100–500 GB disk для артефактов и логов расследований.

#### Production

* 1–2 GPU 48–80 GB VRAM для LLM;
* отдельные CPU workers для tool execution;
* PostgreSQL HA;
* резервное копирование DB;
* лимиты на каждый namespace/pod;
* отдельный node pool для AI workloads.

---

## 16. Безопасное выполнение инструментов

### 16.1. Tool contract

Каждый tool должен иметь декларативное описание:

```yaml
name: kubernetes_get_pods
description: Get pods in namespace
category: kubernetes
risk_level: read_only
timeout_seconds: 10
max_output_bytes: 200000
allowed_parameters:
  namespace:
    type: string
    required: true
  label_selector:
    type: string
    required: false
forbidden:
  - exec
  - delete
  - patch
  - update
```

### 16.2. Allowlist

Tool Executor должен вызывать только зарегистрированные инструменты. Произвольная генерация shell-команд LLM запрещена.

### 16.3. Sanitization

Перед передачей данных в LLM необходимо маскировать:

* passwords;
* tokens;
* API keys;
* Authorization headers;
* cookies;
* private keys;
* client secrets;
* JWT;
* database connection strings;
* персональные данные, если они попадают в логи.

### 16.4. Output budgeting

Для каждого tool:

* ограничение времени;
* ограничение памяти;
* ограничение размера ответа;
* агрегация больших логов;
* server-side filtering;
* top-N errors;
* sampling;
* summary вместо raw dump.

---

## 17. Процесс расследования

### 17.1. Planner

Planner должен выбирать диагностический маршрут.

Пример:

```yaml
alertname: KubePodCrashLooping
route:
  - kubernetes.get_pod
  - kubernetes.get_events
  - opensearch.search_logs
  - prometheus.query_restarts
  - prometheus.query_cpu_memory
  - rag.search_runbooks
  - llm.analyze
```

### 17.2. Evidence-first подход

LLM не должна делать выводы без доказательств. Каждый вывод в отчёте должен иметь источник:

```yaml
claim: "Pod падает из-за OOMKilled"
evidence:
  - kubernetes.last_state.reason: OOMKilled
  - prometheus.memory_usage: 98% of limit
  - opensearch.logs: "Killed process ..."
confidence: 0.91
```

### 17.3. Confidence score

Рекомендуемая шкала:

* 0.90–1.00 — высокая уверенность;
* 0.70–0.89 — вероятная причина;
* 0.50–0.69 — гипотеза требует проверки;
* ниже 0.50 — данных недостаточно.

### 17.4. Стоп-условия

Расследование завершается, если:

* достигнут confidence threshold;
* достигнут max iterations;
* достигнут timeout;
* источник данных недоступен;
* алерт resolved и политика разрешает завершение;
* оператор остановил расследование.

---

## 18. Email-отчёт

### 18.1. Тема письма

Формат:

```text
[CRITICAL][cluster-prod][payments] Возможный OOMKilled: billing-api / confidence 91%
```

### 18.2. Структура письма

```text
Инцидент: KubePodCrashLooping
Severity: critical
Cluster: cluster-prod
Namespace: payments
Service: billing-api
Начало: 2026-06-25 10:31:22 MSK
ID расследования: 7a1e...

Краткое резюме:
Pod billing-api-xxx перезапускается. Наиболее вероятная причина — превышение memory limit.

Вероятная причина:
Контейнер завершён с reason=OOMKilled. Метрики показывают рост memory usage до 98% от limit за 6 минут до рестарта.

Доказательства:
1. Kubernetes last state: OOMKilled.
2. Prometheus: container_memory_working_set_bytes приблизился к limit.
3. OpenSearch: перед рестартом есть ошибки "Java heap space".
4. Kubernetes events: BackOff restarting failed container.

Затронутые компоненты:
- deployment/billing-api
- pod/billing-api-xxx
- node/worker-12

Рекомендации:
1. Проверить изменение нагрузки после релиза.
2. Проверить JVM heap settings.
3. Проверить memory limit и requests.
4. Сравнить с предыдущей версией deployment.
5. При подтверждении — увеличить limit или откатить релиз.

Команды для ручной проверки:
kubectl -n payments describe pod billing-api-xxx
kubectl -n payments logs billing-api-xxx --previous
kubectl -n payments rollout history deployment billing-api

Ссылки:
Grafana: ...
OpenSearch: ...
Kubernetes dashboard: ...

Ограничения анализа:
- Не удалось получить логи previous container.
- Нет данных по trace_id.

Confidence: 91%
```

---

## 19. Конфигурация

### 19.1. Пример config.yaml

```yaml
app:
  name: sre-ai-assistant
  environment: prod
  log_level: INFO

security:
  isolated_mode: true
  allow_external_network: false
  mask_secrets: true
  max_tool_output_bytes: 200000
  max_investigation_minutes: 10
  max_iterations: 5

api:
  host: 0.0.0.0
  port: 8080
  auth:
    enabled: true
    type: token

queue:
  backend: redis
  redis_url: redis://redis.sre-ai.svc:6379/0

database:
  url: postgresql+psycopg://sre_ai:${DB_PASSWORD}@postgres:5432/sre_ai

llm:
  provider: openai_compatible
  base_url: http://vllm.sre-ai.svc:8000/v1
  model: local-sre-instruct
  temperature: 0.1
  max_tokens: 4096
  timeout_seconds: 120

embeddings:
  provider: local
  model: bge-m3
  vector_store: pgvector

notifications:
  email:
    enabled: true
    smtp_host: smtp.internal.local
    smtp_port: 587
    smtp_tls: true
    from: sre-ai@company.local
    default_recipients:
      - sre-oncall@company.local

integrations:
  prometheus:
    url: http://prometheus.monitoring.svc:9090
    timeout_seconds: 10

  alertmanager:
    url: http://alertmanager.monitoring.svc:9093

  grafana:
    url: http://grafana.monitoring.svc:3000

  opensearch:
    hosts:
      - https://opensearch.logging.svc:9200
    index_patterns:
      - logs-*
      - k8s-*

  kubernetes:
    in_cluster: true
    allowed_namespaces:
      - "*"
    deny_secret_values: true
    allow_exec: false

deduplication:
  enabled: true
  window_minutes: 30

correlation:
  time_window_minutes: 20
  same_namespace_weight: 0.3
  same_service_weight: 0.4
  same_node_weight: 0.2
  same_component_weight: 0.3

healthchecks:
  enabled: true
  schedules:
    critical_services: "*/5 * * * *"
    platform: "*/10 * * * *"
    storage: "*/15 * * * *"
```

---

## 20. API

### 20.1. Webhook Alertmanager

```http
POST /api/v1/webhooks/alertmanager
Authorization: Bearer <token>
Content-Type: application/json
```

Ответ:

```json
{
  "status": "accepted",
  "incident_id": "uuid",
  "deduplicated": false
}
```

### 20.2. Ручное расследование

```http
POST /api/v1/investigations
Authorization: Bearer <token>
Content-Type: application/json
```

Тело:

```json
{
  "cluster": "prod",
  "namespace": "payments",
  "service": "billing-api",
  "question": "Почему выросли ошибки 5xx за последние 30 минут?"
}
```

### 20.3. Получение статуса

```http
GET /api/v1/investigations/{id}
```

### 20.4. Health endpoints

```http
GET /healthz
GET /readyz
GET /metrics
```

---

## 21. RBAC Kubernetes

### 21.1. Пример ClusterRole

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: sre-ai-readonly
rules:
  - apiGroups: [""]
    resources:
      - pods
      - pods/log
      - events
      - services
      - endpoints
      - nodes
      - namespaces
      - configmaps
    verbs: ["get", "list", "watch"]

  - apiGroups: ["apps"]
    resources:
      - deployments
      - statefulsets
      - daemonsets
      - replicasets
    verbs: ["get", "list", "watch"]

  - apiGroups: ["batch"]
    resources:
      - jobs
      - cronjobs
    verbs: ["get", "list", "watch"]

  - apiGroups: ["networking.k8s.io"]
    resources:
      - ingresses
      - networkpolicies
    verbs: ["get", "list", "watch"]

  - apiGroups: ["metrics.k8s.io"]
    resources:
      - pods
      - nodes
    verbs: ["get", "list"]
```

Важно: Secret resources не должны быть включены в read permissions без отдельного решения службы ИБ.

---

## 22. NetworkPolicy

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sre-ai-egress
  namespace: sre-ai
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              name: monitoring
      ports:
        - protocol: TCP
          port: 9090
        - protocol: TCP
          port: 9093
        - protocol: TCP
          port: 3000

    - to:
        - namespaceSelector:
            matchLabels:
              name: logging
      ports:
        - protocol: TCP
          port: 9200

    - to:
        - namespaceSelector:
            matchLabels:
              name: sre-ai
      ports:
        - protocol: TCP
          port: 5432
        - protocol: TCP
          port: 6379
        - protocol: TCP
          port: 8000

    - to:
        - ipBlock:
            cidr: 10.0.10.25/32
      ports:
        - protocol: TCP
          port: 587
```

---

## 23. Prompt-инжиниринг

### 23.1. System prompt

```text
Ты локальный SRE assistant. Ты работаешь в изолированном контуре.
Ты не имеешь права предлагать неподтверждённые выводы как факт.
Ты не имеешь права придумывать данные, которых нет в evidence.
Ты не имеешь права рекомендовать опасные действия без явной пометки "требует ручного подтверждения".
Ты должен ссылаться на evidence id.
Ты должен указывать confidence.
Ты должен явно перечислять недоступные данные.
```

### 23.2. Формат ответа LLM

```json
{
  "summary": "...",
  "probable_root_cause": "...",
  "confidence": 0.0,
  "evidence": [
    {
      "id": "evidence-1",
      "source": "kubernetes",
      "claim": "..."
    }
  ],
  "affected_components": [],
  "recommended_manual_actions": [],
  "additional_checks_needed": [],
  "missing_data": [],
  "risk": "low|medium|high"
}
```

---

## 24. Контроль hallucination

Система должна:

* требовать ссылки на evidence для каждого вывода;
* запрещать финальный отчёт без evidence;
* проверять, что LLM не ссылается на несуществующие данные;
* запускать verifier prompt;
* снижать confidence при отсутствии подтверждения из независимых источников;
* явно писать “данных недостаточно”, если доказательств нет.

---

## 25. Интеграционная матрица

| Компонент    | Источник данных             |             Метод доступа | Тип доступа |    MVP |
| ------------ | --------------------------- | ------------------------: | ----------: | -----: |
| Prometheus   | Metrics, alerts             |                  HTTP API |   Read-only |     Да |
| Alertmanager | Alert webhook               |              HTTP webhook |     Inbound |     Да |
| Grafana      | Dashboards, panels          |                  HTTP API |   Read-only |     Да |
| OpenSearch   | Logs                        |        REST/Python client |   Read-only |     Да |
| Kubernetes   | State/events/logs           |            Kubernetes API |   Read-only |     Да |
| DKP          | Platform health             |    K8s/Prometheus/Grafana |   Read-only |     Да |
| Kafka        | Metrics/logs/admin describe |              Exporter/API |   Read-only | Этап 2 |
| Keycloak     | Metrics/logs/health         |                 HTTP/logs |   Read-only | Этап 2 |
| Nginx/Angie  | Metrics/logs                |       Exporter/OpenSearch |   Read-only | Этап 2 |
| HAProxy      | Metrics/logs                | Exporter/stats/OpenSearch |   Read-only | Этап 2 |
| Ceph         | Metrics/status/logs         |  Exporter/API/CLI wrapper |   Read-only | Этап 2 |
| Vault        | Health/metrics/logs         |       HTTP/API/OpenSearch |   Read-only | Этап 2 |
| Consul       | Health/API/metrics          |                  HTTP/API |   Read-only | Этап 2 |
| Redis        | Metrics/info/logs           |  Exporter/INFO/OpenSearch |   Read-only | Этап 2 |
| PostgreSQL   | Metrics/logs/views          |    Exporter/read-only SQL |   Read-only | Этап 2 |
| Linux OS     | Metrics/logs                |  node_exporter/OpenSearch |   Read-only | Этап 2 |

---

## 26. MVP

### 26.1. Состав MVP

MVP должен включать:

* FastAPI webhook для Alertmanager;
* PostgreSQL;
* Redis queue;
* Prometheus adapter;
* OpenSearch adapter;
* Kubernetes adapter;
* Grafana dashboard search;
* local LLM gateway;
* базовый RAG по Markdown runbooks;
* email notifier;
* deduplication;
* базовый correlation engine;
* audit log tool calls;
* Prometheus metrics самой системы;
* Helm chart.

### 26.2. MVP use cases

1. KubePodCrashLooping.
2. KubePodNotReady.
3. Node pressure.
4. High 5xx rate.
5. High latency.
6. PostgreSQL down через blackbox/exporter metrics.
7. Kafka consumer lag через exporter metrics.
8. Ceph health warning через exporter metrics.
9. Keycloak 5xx/latency через ingress metrics/logs.

### 26.3. Что не входит в MVP

* автоматическое исправление;
* полноценный Web UI;
* write actions;
* обучение модели;
* fine-tuning;
* автоматическое создание тикетов;
* уведомления в мессенджеры;
* внешние LLM.

---

## 27. Этапы реализации

### Этап 0. Аналитика и подготовка

Результаты:

* инвентаризация источников данных;
* список критичных сервисов;
* список SMTP-групп;
* список namespaces;
* ownership matrix;
* список существующих runbooks;
* перечень Prometheus rules;
* список Grafana dashboards;
* политика доступа.

### Этап 1. MVP

Срок условно: 6–10 недель.

Результаты:

* webhook ingestion;
* базовые адаптеры;
* локальный LLM;
* email-отчёты;
* хранение расследований;
* Helm deployment;
* тестовый контур.

### Этап 2. Расширение интеграций

Результаты:

* Kafka;
* Ceph;
* Vault;
* Consul;
* Redis;
* PostgreSQL;
* Keycloak;
* Nginx/Angie/HAProxy;
* Linux host checks.

### Этап 3. RAG и база знаний

Результаты:

* индексирование runbooks;
* postmortem search;
* service ownership;
* known incident matching;
* feedback loop.

### Этап 4. Повышение качества анализа

Результаты:

* verifier;
* critic model;
* confidence calibration;
* benchmark suite;
* golden incidents;
* regression tests prompts.

### Этап 5. Production hardening

Результаты:

* HA deployment;
* backup/restore;
* disaster recovery;
* нагрузочное тестирование;
* security review;
* ИБ-акцепт;
* эксплуатационная документация.

---

## 28. Критерии приёмки

### 28.1. Функциональные

Система считается принятой для MVP, если:

* принимает алерты от Alertmanager;
* создаёт расследование;
* собирает данные минимум из Prometheus, OpenSearch, Kubernetes;
* формирует email-отчёт;
* сохраняет историю расследования;
* не выполняет write actions;
* работает без доступа в Интернет;
* использует локальную LLM;
* экспортирует собственные метрики.

### 28.2. Качество RCA

Для набора тестовых инцидентов:

* не менее 70% отчётов должны содержать корректную основную гипотезу;
* не менее 90% отчётов должны содержать релевантные evidence;
* 100% отчётов должны явно указывать missing data;
* 0 случаев выполнения запрещённых действий.

### 28.3. Безопасность

* все tool calls записываются в audit log;
* секреты маскируются;
* egress в Интернет заблокирован;
* Kubernetes RBAC read-only;
* SMTP — единственный исходящий внешний по отношению к namespace канал уведомлений.

---

## 29. Тестирование

### 29.1. Unit tests

* normalizer;
* deduplication;
* correlation;
* tool policies;
* masking;
* prompt rendering;
* email rendering;
* confidence scoring.

### 29.2. Integration tests

* Alertmanager webhook;
* Prometheus API;
* OpenSearch API;
* Kubernetes fake cluster/kind;
* SMTP mock;
* LLM mock;
* PostgreSQL migrations.

### 29.3. E2E tests

Сценарии:

* CrashLoopBackOff;
* OOMKilled;
* image pull error;
* node disk pressure;
* high 5xx;
* high latency;
* missing service endpoints;
* PostgreSQL connection saturation;
* Kafka lag;
* Ceph degraded PG.

### 29.4. LLM evaluation

Создать набор “golden incidents”:

```yaml
- id: oom-java-billing-api
  alert: KubePodCrashLooping
  evidence:
    - pod last state OOMKilled
    - memory near limit
    - Java heap error in logs
  expected_root_cause: memory limit / heap pressure
  expected_recommendations:
    - check heap settings
    - check recent release
    - check memory limits
```

Метрики:

* RCA accuracy;
* evidence precision;
* false positive rate;
* missing data recognition;
* unsafe recommendation rate;
* average investigation time.

---

## 30. Эксплуатация

### 30.1. Deployment options

#### Kubernetes deployment

Рекомендуется для DKP/Kubernetes-контура.

Компоненты:

* sre-ai-api deployment;
* sre-ai-worker deployment;
* sre-ai-scheduler deployment;
* llm-runtime deployment/statefulset;
* postgres statefulset или внешний PostgreSQL;
* redis deployment;
* vector-db deployment;
* secret/configmap;
* serviceaccount/rolebinding;
* networkpolicy;
* servicemonitor.

#### VM/bare metal deployment

Для RED OS / ALT Linux / Astra Linux:

* systemd unit;
* локальный config.yaml;
* Python venv/wheelhouse;
* локальный model directory;
* journald logs;
* node_exporter metrics;
* SMTP relay.

### 30.2. Backup

Резервировать:

* PostgreSQL;
* vector DB;
* runbook index;
* config;
* prompt templates;
* investigation artifacts;
* model manifest.

Не обязательно резервировать:

* временные очереди;
* raw tool outputs, если они восстановимы и политика хранения это допускает.

### 30.3. Retention

Рекомендуемые значения:

```yaml
retention:
  incidents_days: 365
  raw_evidence_days: 90
  llm_prompts_days: 90
  email_reports_days: 365
  audit_log_days: 365
```

---

## 31. Риски и ограничения

### 31.1. Риск hallucination

Митигируется:

* evidence-first;
* verifier;
* confidence score;
* запрет выводов без источников;
* golden tests.

### 31.2. Риск утечки секретов в LLM

Митигируется:

* локальная LLM;
* masking;
* запрет чтения Secret values;
* audit;
* prompt/output scanning.

### 31.3. Риск нагрузки на observability-системы

Митигируется:

* rate limits;
* caching;
* query timeout;
* max concurrent investigations;
* server-side filters;
* преднастроенные безопасные запросы.

### 31.4. Риск ложных срабатываний

Митигируется:

* correlation;
* deduplication;
* baseline;
* severity threshold;
* operator feedback;
* suppression rules.

### 31.5. Риск недоступности LLM

Митигируется:

* fallback report без LLM;
* retry;
* degraded mode;
* отдельные probes;
* отдельный capacity planning.

---

## 32. Рекомендуемая конфигурация алертов для раннего обнаружения

### 32.1. Kubernetes

* частые restarts;
* OOMKilled;
* CrashLoopBackOff;
* Pending pods;
* node pressure;
* unschedulable pods;
* image pull errors;
* CPU throttling;
* memory near limit;
* PVC near full.

### 32.2. Application / HTTP

* рост 5xx;
* рост latency p95/p99;
* рост timeout;
* снижение request rate;
* рост saturation;
* error budget burn.

### 32.3. PostgreSQL

* connections > 80%;
* replication lag;
* deadlocks;
* long transactions;
* locks;
* slow queries;
* disk usage;
* WAL growth.

### 32.4. Kafka

* consumer lag;
* under-replicated partitions;
* offline partitions;
* broker down;
* ISR shrink;
* controller change.

### 32.5. Ceph

* HEALTH_WARN/ERR;
* slow ops;
* OSD down;
* PG degraded;
* nearfull/full;
* MON quorum lost.

### 32.6. Vault

* sealed;
* standby/active issues;
* token renewal failures;
* audit errors;
* storage backend latency.

### 32.7. Consul

* no leader;
* failed health checks;
* raft peers issues;
* DNS errors;
* ACL denied spikes.

### 32.8. Proxy layer

* upstream 5xx;
* backend down;
* queue growth;
* timeout;
* TLS errors;
* reload failure.

---

## 33. Пример Helm values

```yaml
replicaCount:
  api: 2
  worker: 3
  scheduler: 1

image:
  repository: registry.local/sre-ai-assistant
  tag: "0.1.0"

serviceAccount:
  create: true
  name: sre-ai

resources:
  api:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: "1"
      memory: 1Gi
  worker:
    requests:
      cpu: "1"
      memory: 2Gi
    limits:
      cpu: "2"
      memory: 4Gi

llm:
  enabled: true
  endpoint: http://vllm:8000/v1
  model: local-sre-instruct

networkPolicy:
  enabled: true
  denyInternet: true

email:
  smtpHost: smtp.internal.local
  smtpPort: 587
  from: sre-ai@company.local
  defaultRecipients:
    - sre-oncall@company.local

integrations:
  prometheus:
    enabled: true
    url: http://prometheus.monitoring.svc:9090
  grafana:
    enabled: true
    url: http://grafana.monitoring.svc:3000
  opensearch:
    enabled: true
    hosts:
      - https://opensearch.logging.svc:9200
  kubernetes:
    enabled: true
    readOnly: true
```

---

## 34. Definition of Done для первой промышленной версии

Решение готово к промышленной эксплуатации, если выполнено:

1. Пройден security review.
2. Подтверждён запрет внешнего egress.
3. Подтверждён read-only RBAC.
4. Настроены backup/restore.
5. Настроен мониторинг самого SRE-AI Assistant.
6. Подготовлены runbooks для эксплуатации самого решения.
7. Проведены E2E-тесты на synthetic incidents.
8. Подготовлен набор golden incidents.
9. Настроены SMTP-группы.
10. Описаны процедуры обновления моделей.
11. Описана процедура отката.
12. Описаны лимиты и capacity planning.
13. Настроена политика хранения данных.
14. Подготовлена инструкция для дежурной смены.
15. Подтверждено отсутствие write actions в production.

---

## 35. Рекомендуемый результат MVP

После внедрения MVP дежурный инженер должен получать не просто сырой алерт, а письмо вида:

* что произошло;
* где произошло;
* насколько критично;
* какие данные проверены;
* какая наиболее вероятная причина;
* какие компоненты затронуты;
* какие действия выполнить вручную;
* насколько система уверена в выводе;
* каких данных не хватило;
* где открыть Grafana/OpenSearch/Kubernetes для проверки.

Главная ценность решения — сокращение времени первичной диагностики, снижение шума от алертов и раннее выявление деградаций до полноценного отказа.

