Deckhouse Stronghold Community Edition (CE) позволяет построить полноценное хранилище секретов с KV v2, Kubernetes Auth, интеграцией с Ansible и HA. Но в CE отсутствуют некоторые важные для production возможности: Namespaces, аудит обращений, автоматические резервные копии и межкластерная репликация.

Я проверил официальную матрицу редакций Stronghold, актуальную на октябрь 2026 года.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://deckhouse.io\&sz=32)

Deckhouse Stronghold



## 1. Сравнение Stronghold CE и EE

| Возможность                                  | Community Edition | Enterprise Edition |
| -------------------------------------------- | ----------------- | ------------------ |
| KV v1 / KV v2                                |                   |                    |
| Несколько KV mounts                          |                   |                    |
| ACL Policies                                 |                   |                    |
| Kubernetes Auth                              |                   |                    |
| JWT / OIDC / LDAP                            |                   |                    |
| SAML Auth                                    |                   |                    |
| Интеграция с Ansible и Terraform             |                   |                    |
| PKI / Database / SSH Engines                 |                   |                    |
| Web UI                                       |                   |                    |
| Управление ACL и ролями через UI             |                   |                    |
| Namespaces                                   |                   |                    |
| HA (внутри кластера)                         |                   |                    |
| Межкластерная репликация                     |                   |                    |
| Автоматические резервные копии по расписанию |                   |                    |
| Audit Logging                                |                   |                    |
| Встроенный Auto-unseal без внешнего KMS      |                   |                    |
| Managed Keys                                 |                   |                    |
| Air-gapped установка                         |                   |                    |
| Отдельный исполняемый файл                   |                   |                    |

Источник: [официальное сравнение редакций Deckhouse Stronghold](https://deckhouse.io/products/stronghold/documentation/about/editions/?utm_source=chatgpt.com). Отсутствие автоматических backup не означает запрет на ручное резервное копирование.

## 2. Какие ограничения критичны для твоего проекта

1\. Нет Namespaces

Ты не сможешь организовать структуру `Namespace → KV mount → Secret`.

Но предложенная схема с пятью mounts полностью поддерживается:

```
Stronghold CE
├── certs/  (KV v2)
├── infra/  (KV v2)
├── apps/   (KV v2)
├── cicd/   (KV v2)
└── users/  (KV v2)
```

Разделение доступа будет обеспечиваться ACL Policies. Для одной платформенной команды этого может быть достаточно.

2\. Нет Audit Logging

Это, на мой взгляд, наиболее серьёзное ограничение для корпоративного применения.

В CE отсутствует встроенная функциональность аудита Stronghold, поэтому нельзя рассчитывать на полноценный audit trail обращений к секретам средствами продукта.

Особенно критично для `users/`, `infra/` и `cicd/`, где важно расследовать, кто и когда получал доступ к чувствительным данным.

3\. Нет автоматического резервного копирования по расписанию

Придётся самостоятельно организовать backup-процедуры, безопасное хранение snapshots, контроль выполнения и регулярную проверку восстановления.

4\. Нет межкластерной репликации

HA внутри одного Stronghold-кластера доступна.

Но если ты захочешь разместить независимые Stronghold-кластеры в двух ЦОД и организовать между ними Performance Replication или Disaster Recovery Replication, потребуется EE.

## 3. Как это влияет на Deckhouse SSI

Для твоего сценария:

Stronghold CE

apps/ (KV v2)

Deckhouse Prod

SSI + K8s Auth

Deckhouse Stage

SSI + K8s Auth

Deckhouse Dev

SSI + K8s Auth

Ты сможешь использовать отдельные Kubernetes Auth mounts для каждого кластера и отдельные ACL Policies для приложений.

Для этого не нужны Enterprise Namespaces.

## 4. Лицензирование Community Edition

Согласно документации, Stronghold CE:

- Доступен без отдельного лицензионного ключа Stronghold EE.
- Может использоваться с Deckhouse Platform, включая Community Edition.
- Не требует покупки клиентских лицензий Stronghold EE.
- Работает как модуль Deckhouse; в отличие от EE, standalone executable не предусмотрен.&#x20;

  [image](https://www.google.com/s2/favicons?domain=https://deckhouse.io\&sz=32)

  Deckhouse Stronghold

  +1



Переход с CE на EE предусмотрен установкой лицензионного ключа. По документации, при таком переключении сохраняются секреты, политики, подключённые движки и методы аутентификации.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://deckhouse.ru\&sz=32)

Deckhouse Stronghold



## 5. Стоит ли использовать Stronghold CE в твоём случае?

| Твой сценарий                                        | CE достаточно?                                     |
| ---------------------------------------------------- | -------------------------------------------------- |
| Хранение готовых сертификатов для Ansible            | Да                                                 |
| Пароли Grafana / Prometheus / OpenSearch             | Да                                                 |
| Секреты K8s через Deckhouse SSI                      | Да                                                 |
| Пароли CI/CD                                         | Да                                                 |
| Персональные секреты пользователей                   | Функционально да, но отсутствие аудита существенно |
| Строгое разделение административных доменов          | Лучше EE                                           |
| Production с обязательным аудитом и межкластерным DR | EE                                                 |

Моя рекомендация: технически пять KV v2 mounts можно реализовать в Stronghold CE без потери основных функций хранения и выдачи секретов. Но если это единый корпоративный Vault для production, я бы прежде всего оценивал необходимость аудита обращений и межкластерного DR.

Именно эти два требования, а не Namespaces, могут стать решающими при выборе между Stronghold CE и EE.
