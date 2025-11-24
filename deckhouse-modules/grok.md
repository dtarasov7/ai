| Модуль Deckhouse          | Основан на / Аналог OSS                  | Описание кратко                                                                 | Примечания |
|---------------------------|------------------------------------------|---------------------------------------------------------------------------------|------------|
| **ingress-nginx**         | NGINX Ingress Controller                 | Ingress-контроллер для маршрутизации трафика в Kubernetes                       | Интегрируется с cert-manager для SSL |
| **prometheus**            | Prometheus                               | Система мониторинга и alerting на основе time-series данных                     | Заменяется на Prom++ в новых версиях |
| **cert-manager**          | Cert-Manager (Jetstack)                  | Автоматическое управление SSL/TLS сертификатами                                 | Поддержка ACME, Let's Encrypt |
| **metallb**               | MetalLB                                  | Load Balancer для bare-metal кластеров                                           | Использует BGP/ARP для объявления IP |
| **loki**                  | Loki (Grafana Labs)                      | Система агрегации и хранения логов                                              | Индексация меток, хранение объектов |
| **grafana**               | Grafana                                  | Платформа визуализации дашбордов и графиков                                     | Интеграция с Prometheus/Loki |
| **istio**                 | Istio                                    | Service Mesh для трафика, безопасности и observability                          | Использует Sail Operator в Deckhouse |
| **kiali**                 | Kiali                                    | Визуализация и управление Istio service mesh                                    | Топология сервисов и метрики |
| **runtime-audit-engine**  | Falco                                    | Runtime security и обнаружение угроз в контейнерах                              | Основан на eBPF для аудита |
| **operator-trivy**        | Trivy Operator (Aqua Security)           | Сканирование уязвимостей в образах и конфигурациях                              | Интеграция с Kubernetes |
| **node-exporter**         | Node Exporter (Prometheus)               | Экспорт метрик аппаратного обеспечения и ОС                                     | Для мониторинга узлов |
| **oauth2-proxy**          | OAuth2 Proxy                             | Прокси для аутентификации через OAuth/OIDC                                      | Поддержка провайдеров как Google, GitHub |
| **keepalived**            | Keepalived                               | High-availability и load balancing для IP                                       | VRRP протокол для failover |
| **shell-operator**        | Shell-operator (Flant)                   | Фреймворк для написания Kubernetes операторов на shell скриптах                 | Open-source от Flant |
| **addon-operator**        | Addon-operator (Flant)                   | Управление аддонами и модулями в Kubernetes                                     | База модульной системы Deckhouse |
| **delivery**              | Argo CD                                  | GitOps инструмент для declarative deployments                                   | Поддержка multi-tenancy |
| **fluxcd-source-controller** | Flux CD Source Controller             | Управление Git репозиториями для GitOps                                         | Часть Flux экосистемы |
| **snapshot-controller**   | CSI Snapshot Controller (Kubernetes)     | Управление снапшотами persistent volumes                                        | Стандартный Kubernetes компонент |
| **static-routing-manager**| Нет прямого аналога (custom)             | Управление статической маршрутизацией в кластере                                 | Может быть заменен через ModuleSource |
| **cni-cilium**            | Cilium                                   | eBPF-based networking, security и observability для Kubernetes                  | Альтернатива Calico |
| **cni-flannel**           | Flannel                                  | Простая overlay сеть для подов                                                  | Backend как VXLAN |
| **cni-simple-bridge**     | Bridge CNI Plugin (Kubernetes)           | Базовый мост для локальной сети подов                                           | Стандартный CNI |
| **kubevirt**              | KubeVirt                                 | Виртуализация VM в Kubernetes как нативных ресурсов                             | На базе libvirt |
| **memcached**             | Memcached                                | In-memory key-value store для кэширования                                       | Высокопроизводительный |
| **nginx**                 | NGINX                                    | Web-сервер, reverse proxy и load balancer                                       | Используется в ingress |
| **trickster**             | Trickster                                | Proxy/cache для time-series баз данных (Prometheus)                             | Ускорение запросов |
| **jq**                    | jq                                       | Командно-строковый процессор JSON                                               | Используется в скриптах |
| **secrets-store-integration** | Secrets Store CSI Driver (Kubernetes) | Интеграция с внешними secrets managers (Vault, AWS SM и т.д.)                   | CSI driver для монтирования секретов |
| **pod-reloader**          | Reloader (Stakater)                      | Автоматический reload подов при изменениях ConfigMap/Secret                      | Поддержка annotations для триггеров |
| **user-authn**            | Dex                                      | OpenID Connect провайдер для Kubernetes аутентификации                          | Интеграция с LDAP, GitHub и т.д. |
| **log-shipper**           | Vector                                   | Легковесный агент для сбора, трансформации и отправки логов                    | Альтернатива Fluentd |
| **kube-state-metrics**    | kube-state-metrics                       | Генерация метрик из Kubernetes API объектов                                     | Для Prometheus |
| **prometheus-metrics-adapter** | Kubernetes Metrics Adapter           | Адаптер для custom metrics в HPA                                                | На базе Prometheus |
| **vertical-pod-autoscaler** | Vertical Pod Autoscaler (Kubernetes)   | Автоматическая корректировка CPU/memory requests                                | Рекомендации на основе использования |
| **multitenancy-manager**  | Capsule / Hierarchical Namespace Controller | Управление мультитенантностью через виртуальные кластеры и namespaces          | Поддержка квот и политик |
| **stronghold**            | HashiCorp Vault (API-совместимый)        | Хранилище секретов с KV engine                                                  | Нативная альтернатива Vault в Deckhouse |
| **kyverno**               | Kyverno                                  | Policy engine для валидации и мутации ресурсов                                  | Альтернатива OPA/Gatekeeper |

**Примечания:**
- Deckhouse модули часто являются обертками или улучшенными версиями upstream open-source проектов, адаптированными для enterprise использования с преднастроенными конфигурациями и интеграциями.
- Некоторые модули (например, shell-operator, addon-operator) разработаны Flant и являются open-source.
- Информация основана на документации Deckhouse (deckhouse.io), GitHub репозитории (github.com/deckhouse/deckhouse) и общих альтернативах из OSS сообщества.
- Для полного списка модулей и их версий рекомендуется проверять актуальную документацию Deckhouse.
