Для VictoriaMetrics Cluster + Keycloak (OIDC) я рекомендую использовать `vmauth` как единую точку авторизации перед кластером, но разделить пользовательский и сервисный доступ.

Это позволит одновременно решить три задачи:

1. Реализовать SSO для пользователей, работающих в `vmui` через браузер.
2. Использовать OAuth2/JWT для `vmagent`, Prometheus, Grafana и других сервисов.
3. Обеспечить изоляцию пользователей и сервисов по tenant (`accountID:projectID`) и разграничение прав на чтение и запись метрик.

## 1. Целевая архитектура

Логическая схема. Перед vmauth рекомендуется разместить TLS-терминирующий балансировщик / Ingress.

Для кластера важно, что `vmui` предоставляется компонентом `vmselect`, а не `vminsert`. Его внутренний адрес имеет вид:

```
http://vmselect:8481/select/1:0/vmui/
```

Где `1:0` — идентификатор tenant.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.victoriametrics.com\&sz=32)

docs.victoriametrics.com

+1



При этом внешнему пользователю желательно не разрешать самостоятельно выбирать tenant через URL. Его нужно определять по проверенным claims токена, выпущенного Keycloak.

## 2. Конфигурация vmauth для кластерной VictoriaMetrics

Ниже пример единого `auth.yaml` для `vmauth` версии 1.153.0+.

Предполагается, что Keycloak выдаёт JWT с пользовательским claim `vm_role` (`viewer` или `writer`) и claim `vm_access` с идентификаторами tenant.

Пример конфигурации для адаптации и тестирования, а не готовый production-манифест.

```
sso:
  - src_host: 'metrics\.example\.com'
    oidc:
      issuer: 'https://keycloak.example.com/realms/monitoring'
      client_id: 'victoriametrics-ui'
      client_secret: 'REPLACE_WITH_SECRET'
      cookie_secret: 'REPLACE_WITH_RANDOM_SECRET'
      scopes: ['openid', 'profile']
      session_duration: '30m'

users:
  # 1. Browser SSO: доступ к vmui и read API
  - jwt:
      oidc:
        issuer: 'https://keycloak.example.com/realms/monitoring'
      match_claims:
        aud: 'victoriametrics-ui'
        vm_role: 'viewer'
        vm_access.metrics_account_id: '[0-9]+'
        vm_access.metrics_project_id: '[0-9]+'
    url_map:
      - src_hosts:
          - 'metrics\.example\.com'
        src_paths:
          - '/select/[^/]+/vmui/.*'
          - '/select/[^/]+/prometheus/api/v1/(query|query_range|series|labels|metadata|label/[^/]+/values)'
        drop_src_path_prefix_parts: 2
        url_prefix:
          - 'http://vmselect-1:8481/select/{{.MetricsTenant}}/'
          - 'http://vmselect-2:8481/select/{{.MetricsTenant}}/'

  # 2. Service API: только чтение
  - jwt:
      oidc:
        issuer: 'https://keycloak.example.com/realms/monitoring'
      match_claims:
        aud: 'metrics-api'
        vm_role: 'reader'
        vm_access.metrics_account_id: '[0-9]+'
        vm_access.metrics_project_id: '[0-9]+'
    url_map:
      - src_hosts:
          - 'metrics-api\.example\.com'
        src_paths:
          - '/api/v1/query'
          - '/api/v1/query_range'
          - '/api/v1/series'
          - '/api/v1/labels'
          - '/api/v1/label/[^/]+/values'
        url_prefix:
          - 'http://vmselect-1:8481/select/{{.MetricsTenant}}/prometheus/'
          - 'http://vmselect-2:8481/select/{{.MetricsTenant}}/prometheus/'

  # 3. Service API: только запись
  - jwt:
      oidc:
        issuer: 'https://keycloak.example.com/realms/monitoring'
      match_claims:
        aud: 'metrics-api'
        vm_role: 'writer'
        vm_access.metrics_account_id: '[0-9]+'
        vm_access.metrics_project_id: '[0-9]+'
    url_map:
      - src_hosts:
          - 'metrics-api\.example\.com'
        src_paths:
          - '/api/v1/write'
        url_prefix:
          - 'http://vminsert-1:8480/insert/{{.MetricsTenant}}/prometheus/'
          - 'http://vminsert-2:8480/insert/{{.MetricsTenant}}/prometheus/'
```

Здесь применяются официально поддерживаемые возможности: `sso`, `jwt.match_claims`, `url_map`, `drop_src_path_prefix_parts` и `{{.MetricsTenant}}`.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.victoriametrics.com\&sz=32)

docs.victoriametrics.com

+2



Особенность GUI-маршрута: первые два сегмента внешнего пути (`/select/<tenant>/`) заменяются на tenant, полученный из проверенного JWT. Поэтому изменение идентификатора tenant в URL само по себе не даёт доступ к чужим данным.

Для полноценной работы всех функций `vmui` потребуется проверить и при необходимости дополнить белый список read-only API. Широкий маршрут `/select/.*` без ограничений использовать не рекомендую.

## 3. Настройка claims в Keycloak

Для кластерной схемы важен специальный claim `vm_access`.

Пример токена пользовательского доступа:

```
{
  "aud": "victoriametrics-ui",
  "vm_role": "viewer",
  "vm_access": {
    "metrics_account_id": 12,
    "metrics_project_id": 0
  }
}
```

В этом случае `vmauth` автоматически подставляет `12:0` в адрес `vmselect`.

Для сервисов схема аналогичная, но `aud` будет `metrics-api`, а роль — `reader` или `writer`.

Здесь есть важный нюанс: для браузерного SSO Keycloak должен включать нужные claims в ID Token, а для сервисной аутентификации — в Access Token. Эти параметры настраиваются через Protocol Mappers в Keycloak.

## 4. Настройка защиты от перебора паролей

В Keycloak можно включить Brute Force Detection через `Realm Settings → Security Defenses → Brute Force Detection`.

В актуальных версиях Keycloak можно выбрать постоянную или временную блокировку и установить `Max Login Failures = 10`.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.keycloak.org\&sz=32)

keycloak.org

+1



Разделение требований получится следующим:

| Объект защиты                                | Реализация                            |
| -------------------------------------------- | ------------------------------------- |
| Пользовательский пароль                      | Keycloak                              |
| Блокировка после 10 ошибок                   | Keycloak Brute Force Detection        |
| MFA для сотрудников                          | Keycloak                              |
| Авторизация запросов                         | vmauth                                |
| Доступ только к своему tenant                | vmauth + JWT                          |
| Разделение чтения и записи                   | vmauth URL rules                      |
| Защита сервисных credentials                 | Keycloak, rate limiting, аудит        |
| Сетевая изоляция vmstorage/vmselect/vminsert | Kubernetes NetworkPolicy или firewall |

У сервисов, работающих через Client Credentials Flow, ограничение числа ошибок должно применяться к аутентификации OAuth-клиента. Настройка пользовательской блокировки в Keycloak не заменяет такую защиту.

## 5. Что дополнительно учесть в промышленном кластере

Я бы разместил минимум две реплики `vmauth` за балансировщиком и использовал одинаковые конфигурацию и SSO-секреты на репликах. Backend-компоненты должны быть недоступны напрямую извне.

Особенно важно исключить доступ обычных клиентов к `/select/multitenant/...`, `/insert/multitenant/...` и административным API, а также проверить обработку `AccountID` и `ProjectID` HTTP-заголовков. ВикторияMetrics отдельно предупреждает об этих рисках.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.victoriametrics.com\&sz=32)

docs.victoriametrics.com

+1



И ещё один нюанс: если требуется немедленная блокировка доступа после отключения пользователя в Keycloak, одной JWT-проверки в `vmauth` недостаточно. Уже выданные токены могут продолжать работать до истечения `exp`. Для жёсткого отзыва потребуются дополнительные меры.

## Итог

Для вашей кластерной архитектуры Keycloak + vmauth — подходящий вариант, позволяющий выполнить требования по пользовательской аутентификации и реализовать сервисную авторизацию без хранения пользовательских паролей в VictoriaMetrics.

Официальные материалы: [vmauth SSO/JWT](https://docs.victoriametrics.com/vmauth/?utm_source=chatgpt.com) и [кластерная интеграция с OIDC](https://docs.victoriametrics.com/guides/grafana-vmauth-openid-configuration/?utm_source=chatgpt.com).

Остаётся один существенный архитектурный вопрос: кластер развёрнут в Kubernetes (через VictoriaMetrics Operator/Helm) или на виртуальных машинах/Docker? Это определяет, как правильнее организовать HA `vmauth`, секреты Keycloak и публикацию GUI/API.
