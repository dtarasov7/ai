Ниже — таблица соответствия популярных модулей Deckhouse и открытого ПО, на котором они основаны или которое выполняет ту же функцию.

| Модуль Deckhouse | Основано на / аналогичное OSS | Кратко о назначении |
|---|---|---|
| ingress-nginx | NGINX Ingress Controller.  | Балансировка и терминация HTTP(S) трафика, поддержка нескольких контроллеров.  |
| cert-manager | cert-manager.  | Выпуск и автопродление сертификатов (Let’s Encrypt, Vault и др.).  |
| kube-dns | CoreDNS.  | DNS для кластера Kubernetes.  |
| node-local-dns | CoreDNS (NodeLocal DNSCache).  | Кеширующий DNS на каждом узле.  |
| cni-cilium | Cilium (eBPF CNI).  | Сетевой стек, может заменять kube-proxy, поддерживает eBPF/LB.  |
| cni-flannel | Flannel.  | Простая L3-сеть для Pod’ов.  |
| cilium-hubble | Hubble (часть экосистемы Cilium).  | Визуализация сетевого трафика/потоков.  |
| network-policy-engine | kube-router (firewall mode).  | Реализация Kubernetes NetworkPolicy через iptables.  |
| istio | Istio/Envoy.  | Service Mesh: mTLS, маршрутизация, авторизация, мультикластер.  |
| metallb | MetalLB.  | Поддержка Service type=LoadBalancer в bare-metal, L2/BGP.  |
| openvpn | OpenVPN.  | Доступ в кластер через VPN с веб‑админкой.  |
| keepalived | Keepalived.  | Виртуальные IP/VRRP для HA‑сценариев.  |
| dashboard | Kubernetes Dashboard.  | Веб‑UI для управления ресурсами кластера.  |
| prometheus | Prometheus, Grafana, Alertmanager, Trickster, memcached, экспортеры.  | Наблюдаемость: сбор метрик, алерты, дашборды, long‑term хранение/кеширование.  |
| operator-prometheus | Prometheus Operator.  | Управление Prometheus/Alertmanager через CRD (Prometheus, ServiceMonitor, PrometheusRule).  |
| prometheus-metrics-adapter | k8s‑prometheus‑adapter.  | HPA/VPA по кастомным метрикам из Prometheus; kubectl top через adapter.  |
| prometheus-pushgateway | Prometheus Pushgateway.  | Приём push‑метрик от приложений.  |
| vertical-pod-autoscaler | Kubernetes VPA.  | Рекомендации/автонастройка requests/limits.  |
| descheduler | Kubernetes Descheduler.  | Периодическое “переразмещение” Pod’ов по стратегиям.  |
| loki | Grafana Loki.  | Оперативное хранилище логов, интеграция с Grafana.  |
| log-shipper | Vector (агент).  | Сбор/обогащение/маршрутизация логов к Loki/ES/S3 и др.  |
| user-authn | Dex, oauth2‑proxy, dex‑k8s‑authenticator.  | Единая аутентификация (OIDC/SAML/LDAP и др.), генерация kubeconfig.  |
| user-authz | Стандартный Kubernetes RBAC (готовые роли).  | Набор ролей/ролебиндингов для удобного разграничения доступа.  |
| secrets-store-integration | Secrets Store CSI Driver + провайдер Vault (совместим с Vault API).  | Монтаж/синхронизация секретов из Vault‑совместимых хранилищ в Pod/Secret.  |
| pod-reloader | Stakater Reloader.  | Автоматический rollout workloads при изменении Secret/ConfigMap.  |
| kube-proxy | kube-proxy (встроенный компонент Kubernetes).  | Реализация service networking (iptables/ipvs) когда не используется Cilium LB.  |
| chrony | chrony.  | Синхронизация времени на узлах кластера.  |
| csi-ceph | Ceph-CSI (RBD/CephFS).  | Динамические PVC на базе Ceph.  |
| csi-nfs | NFS CSI Driver (nfs.csi.k8s.io).  | Использование NFS как хранилища томов, опционально RPC‑with‑TLS.  |
| operator-trivy | Trivy Operator.  | Регулярное сканирование образов/настроек на уязвимости и комплаенс.  |
| runtime-audit-engine | Falco (+ falcosidekick).  | Детектирование runtime‑угроз по системным вызовам и Kubernetes audit.  |

Примечания
- Это не полный список всех модулей Deckhouse; я включил наиболее часто используемые и те, где связь с OSS очевидна в официальной документации. Хотите — добавлю конкретные модули (например, облачных провайдеров, SDN/SDx, SDS‑* и т.п.).
- Некоторые модули являются “обвязкой”/оператором вокруг OSS (например, operator-prometheus), часть объединяет сразу несколько проектов (prometheus), а часть — собственные реализации с использованием стандартных механизмов Kubernetes (user-authz на базе RBAC). Ссылки указывают на официальные страницы Deckhouse, где упоминаются соответствующие OSS-компоненты.
