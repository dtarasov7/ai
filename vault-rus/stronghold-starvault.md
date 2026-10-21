Да. И StarVault, и Deckhouse Stronghold поддерживают Namespaces, аналогичные пространствам имён HashiCorp Vault Enterprise.

Причём эта функциональность появилась в обоих продуктах в 2025 году.

## 1. Сравнение поддержки Namespaces

| Возможность                              | Deckhouse Stronghold | StarVault        |
| ---------------------------------------- | -------------------- | ---------------- |
| Поддержка Namespaces                     | Да, с версии 1.16    | Да, с версии 1.3 |
| Иерархические Namespaces                 | Да                   | Да               |
| Изоляция Secrets Engines                 | Да                   | Да               |
| Отдельные ACL Policies                   | Да                   | Да               |
| Управление через CLI/API                 | Да                   | Да               |
| Управление через Web UI                  | Да                   | Да               |
| Разделение команд внутри одного кластера | Да                   | Да               |

Особенности редакций:

- Stronghold: Namespaces доступны в Enterprise Edition (EE), но не в Community Edition (CE).&#x20;

  [image](https://www.google.com/s2/favicons?domain=https://deckhouse.ru\&sz=32)

  Deckhouse Stronghold

  +1

- StarVault: Namespaces появились в версии 1.3, представленной в ноябре 2025 года.&#x20;

  [image](https://www.google.com/s2/favicons?domain=https://zoom.cnews.ru\&sz=32)

  ZOOM.CNews.ru



Официальная документация:

- [Stronghold — Namespaces](https://deckhouse.io/products/stronghold/documentation/admin/namespaces/?utm_source=chatgpt.com)
- [StarVault — Namespaces](https://wiki.orionsoft.ru/starvault/latest/admin-guide/namespaces/how-to-use-namespaces/?utm_source=chatgpt.com)

## 2. Как это меняет твою архитектуру

Раньше мы рассматривали пять KV v2 mounts в корневом пространстве:

```
Vault
├── certs/
├── infra/
├── apps/
├── cicd/
└── users/
```

Теперь у тебя появляется дополнительный уровень изоляции:

```
Vault Cluster
│
├── Namespace: infrastructure
│   ├── certs/            # KV v2
│   └── infra/            # KV v2
│
├── Namespace: applications
│   ├── prod/
│   │   └── apps/         # KV v2
│   ├── stage/
│   │   └── apps/         # KV v2
│   └── dev/
│       └── apps/         # KV v2
│
├── Namespace: automation
│   └── cicd/             # KV v2
│
└── Namespace: personal
    └── users/            # KV v2
```

Здесь `prod`, `stage`, `dev` внутри `applications` — тоже Namespaces, а не каталоги KV.

### Чем это лучше пяти mounts в root?

Namespace позволяет изолировать не только секреты, но и конфигурацию доступа.

Например, в `applications/prod` могут быть собственные:

- KV Secrets Engines;
- Kubernetes Auth Methods;
- ACL Policies;
- Identity Entities и Groups;
- Vault Roles и Tokens.

Администратор пространства `applications/prod` может управлять своими объектами без предоставления ему административных прав на `infrastructure` или `personal`.

## 3. Что я рекомендую для твоего проекта

Я бы использовал Namespaces для административного и организационного разделения, а KV mounts — для разделения категорий секретов.

Не рекомендую создавать Namespace для каждого Kubernetes-приложения или сертификата: это добавляет много объектов и усложняет эксплуатацию.

Практически достаточно 4–6 Namespaces, а приложения внутри них разделять через KV Paths и ACL Policies.

### Важный нюанс лицензирования

В контексте сравнения StarVault и Stronghold надо отдельно уточнить у вендоров:

1. Есть ли ограничения на количество Namespaces в лицензии.
2. Учитываются ли клиенты каждого Namespace отдельно или дедуплицируются на уровне всей инсталляции.
3. Как считаются одинаковые Kubernetes ServiceAccounts, аутентифицирующиеся в разных Namespaces.

Особенно важен второй вопрос: один технический сервис, работающий с несколькими Namespaces, потенциально может влиять на количество лицензируемых клиентов.

Итог: в обоих продуктах ты можешь построить архитектуру `Cluster → Namespace → KV v2 Mount → Path → Secret`. Это более гибкая модель, чем пять KV mounts в root, и я бы рассматривал её как базовую для корпоративной эксплуатации Stronghold EE или StarVault.
