Да, оба сценария — вход пользователей через браузер и аутентификация сервисов — можно реализовать через внешний OIDC-провайдер, например Keycloak, с использованием `vmauth`.

Причём для вашего случая, где есть требование ИБ блокировать пользователя после 10 неверных паролей, я бы рекомендовал единую архитектуру аутентификации, но с двумя разными механизмами получения токенов.

## 1. Рекомендуемая архитектура

Здесь:

- Keycloak проверяет пользователей, пароли, MFA, политики блокировки, а также выдаёт токены сервисам.
- vmauth проверяет JWT, разрешает или запрещает доступ, направляет запросы к нужным API.
- VictoriaMetrics занимается хранением, записью и чтением метрик.

Такая интеграция поддерживается официально. Браузерный SSO появился в `vmauth` версии 1.153.0, а проверка JWT через OIDC Discovery доступна с 1.138.0.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.victoriametrics.com\&sz=32)

docs.victoriametrics.com

+1



## 2. Вариант №1 — пользователи через браузер

Для пользователей, которые заходят в `vmui` (веб-интерфейс VictoriaMetrics), в современной версии `vmauth` можно настроить полноценный OIDC SSO.

1. Пользователь открывает `https://metrics.example.com/vmui/`.
2. `vmauth` направляет пользователя в Keycloak.
3. Keycloak проверяет пароль, MFA и наличие блокировки.
4. После входа браузер возвращается в `vmauth` с authorization code.
5. `vmauth` обменивает code на токен и создаёт сессионную cookie.
6. Дальнейшие запросы к VictoriaMetrics проходят с проверкой токена и его claims.

Пример `auth.yaml` для single-node VictoriaMetrics:

```
sso:
  - src_host: 'metrics\.example\.com'
    oidc:
      issuer: 'https://keycloak.example.com/realms/monitoring'
      client_id: 'victoriametrics-ui'
      client_secret: 'REPLACE_WITH_SECRET'
      cookie_secret: 'REPLACE_WITH_RANDOM_SECRET_32_CHARS'
      scopes: ['openid', 'profile', 'email']
      session_duration: '1h'

users:
  - jwt:
      oidc:
        issuer: 'https://keycloak.example.com/realms/monitoring'
      match_claims:
        aud: 'victoriametrics-ui'
      default_vm_access_claim: {}
    url_prefix: 'http://victoriametrics:8428/'
```

Для этого клиента в Keycloak нужно зарегистрировать Redirect URI:

```
https://metrics.example.com/_vmauth/sso/callback
```

Это базовая иллюстрация SSO. Для production также необходимо ограничить доступ по ролям, защитить секреты, настроить HTTPS и не допускать обхода `vmauth`.

Важный момент: блокировка после 10 ошибок происходит именно в Keycloak, потому что пароль вводится там, а не в `vmauth`.

Подробности: [официальная документация vmauth SSO](https://docs.victoriametrics.com/vmauth.html?utm_source=chatgpt.com#single-sign-on-sso).

## 3. Вариант №2 — аутентификация сервисов через OIDC

Для сервисов — `vmagent`, Prometheus, приложений, выполняющих запросы к API VictoriaMetrics — лучше использовать OAuth 2.0 Client Credentials Flow.

В этом случае сервису не нужны логин и пароль обычного пользователя. Вместо них применяются `client_id` и `client_secret` либо другой поддерживаемый способ аутентификации клиента.

Последовательность:

1. Сервис аутентифицируется в Keycloak по своим credentials.
2. Keycloak выдаёт короткоживущий access token (JWT).
3. Сервис отправляет API-запрос с `Authorization: Bearer ...`.
4. `vmauth` проверяет подпись, срок действия, issuer и разрешённые claims.
5. Если проверка успешна, запрос перенаправляется в VictoriaMetrics.

Например, сервис может получить токен:

```
curl -X POST \
  https://keycloak.example.com/realms/monitoring/protocol/openid-connect/token \
  -d 'grant_type=client_credentials' \
  -d 'client_id=vmagent-prod' \
  -d 'client_secret=YOUR_SECRET'
```

А затем использовать полученный `access_token`:

```
curl \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://metrics-api.example.com/api/v1/query?query=up"
```

Здесь уже нет пользовательского пароля, который можно ошибочно ввести 10 раз. Для защиты сервисных credentials используются отдельные политики: ограничение попыток получения токена, срок действия секретов, их ротация и аудит.

### Пример конфигурации vmagent

В `vmagent` получение и обновление OAuth2-токенов можно автоматизировать.

```
vmagent \
  -promscrape.config=/etc/vmagent/scrape.yml \
  -remoteWrite.url=https://metrics-api.example.com/api/v1/write \
  -remoteWrite.oauth2.clientID=vmagent-prod \
  -remoteWrite.oauth2.clientSecretFile=/etc/secrets/client-secret \
  -remoteWrite.oauth2.tokenUrl=https://keycloak.example.com/realms/monitoring/protocol/openid-connect/token
```

Этот сценарий есть в официальном руководстве VictoriaMetrics по интеграции `vmagent` с OIDC.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.victoriametrics.com\&sz=32)

Multi-Tenant remote write & OIDC:

+1



## 4. Как разграничить права пользователей и сервисов

Я бы предусмотрел отдельные OIDC-клиенты:

| OIDC-клиент          | Назначение                     | Доступ                      |
| -------------------- | ------------------------------ | --------------------------- |
| `victoriametrics-ui` | Люди, работающие через браузер | Чтение метрик, UI           |
| `vmagent-prod`       | Отправка метрик                | Только запись               |
| `monitoring-reader`  | Сервисные API-запросы          | Только чтение               |
| `monitoring-admin`   | Административные интеграции    | Строго необходимые операции |

В Keycloak токенам можно назначать роли и audience, которые затем проверяет `vmauth`.

Упрощённый пример для сервисов:

```
users:
  - jwt:
      oidc:
        issuer: "https://keycloak.example.com/realms/monitoring"
      match_claims:
        aud: "victoriametrics-api"
        role: "metrics-reader"
      default_vm_access_claim: {}
    url_prefix: "http://victoriametrics:8428/"
```

В данном примере Keycloak должен действительно выдавать access token с такими claims. Для ограничения записи и чтения нужно дополнительно использовать `url_map` и разрешать только нужные API-маршруты. Одна проверка роли сама по себе не делает backend доступным только для чтения.

Также желательно использовать разные hostnames для браузерного и сервисного доступа, например `metrics.example.com` и `metrics-api.example.com`, чтобы независимо управлять SSO, cookies, JWT и маршрутами.

## 5. Какой результат получаем по требованиям ИБ

| Требование                             | GUI (пользователи)                | API (сервисы)                    |
| -------------------------------------- | --------------------------------- | -------------------------------- |
| Централизованная аутентификация        | Keycloak OIDC                     | Keycloak OAuth2                  |
| Блокировка после 10 неверных паролей   | Реализуется в Keycloak            | Неприменимо в той же форме       |
| MFA                                    | Да                                | Обычно не применяется            |
| Разграничение прав                     | JWT claims + vmauth               | JWT claims + vmauth              |
| Отзыв доступа                          | Через IdP, с учётом срока токенов | Отключение клиента, срок токенов |
| Аудит аутентификации                   | Keycloak                          | Keycloak                         |
| Наличие паролей пользователей в vmauth | Не требуется                      | Не требуется                     |

Стоит помнить: `vmauth` локально проверяет уже выданные JWT. Поэтому блокировка учётной записи в Keycloak не обязательно мгновенно прекращает доступ с ранее выданным токеном. Это надо учитывать при настройке TTL.

## 6. Что я рекомендую для вашей архитектуры

Если у вас VictoriaMetrics версии 1.153.0 или новее, оптимальный вариант — использовать штатный SSO в `vmauth` для GUI и OAuth2 Client Credentials для сервисных интеграций.

Если версия более ранняя, браузерный SSO можно организовать с помощью внешнего `oauth2-proxy`, а сервисы по-прежнему могут использовать JWT-аутентификацию `vmauth`, если версия её поддерживает.

Это позволит централизовать управление аутентификацией, выполнить требования ИБ для пользовательских паролей и не подвергать мониторинговые интеграции риску блокировки из-за ошибочного пароля.

Основные документы:

- [vmauth — аутентификация, JWT и SSO](https://docs.victoriametrics.com/vmauth.html?utm_source=chatgpt.com)
- [Официальный пример Keycloak + Grafana + vmauth](https://docs.victoriametrics.com/guides/grafana-vmauth-openid-configuration/?utm_source=chatgpt.com)
- [Передача OAuth-токенов из Grafana в VictoriaMetrics](https://docs.victoriametrics.com/victoriametrics/integrations/grafana/datasource/?utm_source=chatgpt.com)

Единственное, что важно уточнить для точной схемы развёртывания: у вас VictoriaMetrics работает в Single Node или Cluster (`vmselect`, `vminsert`, `vmstorage`)? Для кластерного варианта желательно сразу учитывать tenant isolation, а для single-node схема будет существенно проще.
