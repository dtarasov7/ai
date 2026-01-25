Ниже — практичный план: (1) зафиксировать текущее состояние кластера “как есть”, (2) выгрузить/восстановить манифесты и Helm-релизы в воспроизводимом виде, (3) собрать офлайн‑зеркала образов/чартов через Nexus, (4) подготовить рекомендации по High Load, не меняя версию Kubernetes (v1.24).

## 1) Аудит “as-is” (инвентаризация)
Цель — получить полный снапшот: версии, что где запущено, откуда пришло, и какие “ручные” изменения есть.

- Снимите версии и состояние control-plane:
  - `kubectl version -o yaml`, `kubectl get nodes -o wide`
  - `kubectl -n kube-system get pods -o wide`
  - `kubeadm version`, `kubeadm config view`, `kubeadm token list` (если доступно)
  - Для статических подов: содержимое `/etc/kubernetes/manifests/*.yaml` на каждом мастере.
- Инвентаризация установленных компонентов:
  - Helm: `helm ls -A`, `helm env`, `helm repo list` (даже если chart’ы потеряны, релизы в Secret/ConfigMap обычно остались).
  - Cilium: `cilium status`, `cilium config view` (или `kubectl -n kube-system get cm cilium-config -o yaml`).
  - Ingress: `kubectl -n ingress-nginx get all -o yaml` и `kubectl describe deploy/daemonset ...`.
- Проверка “ручных правок” образов и контейнеров:
  - На узлах: `crictl images -v`, `ctr -n k8s.io images ls`, `crictl inspecti <image>`; снимите `RepoTags`, `RepoDigests`, `imageID`, размер.
  - Сравнение с “официальным” образом делайте по digest: если у вас “etcd:v2.6.7”, но digest другой — это уже *не* официальный образ (важно для цепочки доверия/ИБ).
- ИБ/политики:
  - RBAC: `kubectl get clusterrole,clusterrolebinding,role,rolebinding -A -o yaml`
  - Admission: проверьте включенные admission plugins у apiserver (в манифесте kube-apiserver) и наличие OPA/Gatekeeper/Kyverno (если есть).
- Логи и метрики:
  - kubelet/containerd/systemd: снимите `journalctl -u kubelet --since ...`, `journalctl -u containerd --since ...`
  - apiserver/controller-manager/scheduler — если они как static pod’ы, логи через `kubectl -n kube-system logs ...` или с хоста.

Результат этого этапа: “паспорт кластера” (версии, список аддонов, источники, конфиги, digests образов, риски).

## 2) Резервные копии манифестов и “восстановление” Helm
### Экспорт всего из API (то, что реально применено)
- Базовый дамп всех объектов (кроме некоторых ephemeral):
  - `kubectl get all -A -o yaml`
  - Отдельно CRD: `kubectl get crd -o yaml`
  - Отдельно “важное”: `kubectl get cm,secret,sa,role,rolebinding,clusterrole,clusterrolebinding,ingress,netpol,pvc,pv -A -o yaml`
- Важно: Secrets лучше экспортировать **в зашифрованном** виде (например, SOPS/age), либо исключить и бэкапить через etcd-снапшот.

### Снятие фактических значений Helm-релизов
Даже если chart’ов нет, вы можете восстановить:
- Values: `helm get values -A <release> -n <ns> -a`
- Полный манифест, который Helm применял: `helm get manifest <release> -n <ns>`
- Метаданные: `helm get all <release> -n <ns>`

Далее:
- Соберите “репозиторий инфраструктуры” (git):  
  - `/cluster-dump/YYYY-MM-DD/…` (kubectl exports)  
  - `/helm/<release>/values.yaml`, `/helm/<release>/manifest.yaml`  
  - `/node-config/<node>/etc-kubernetes-manifests/…`, `/etc/containerd/config.toml`, и т.д.

### Бэкап etcd (раз etcd в контейнере)
- Найдите как запущен etcd (статический под/Deployment) и где лежат данные (`--data-dir`).
- Делайте снапшот через `etcdctl snapshot save ...` из *того же контейнера/с теми же сертификатами*, что использует etcd.
- Храните минимум: (а) snapshot, (б) все TLS-ключи/сертификаты etcd, (в) манифест запуска etcd и параметры.

## 3) Официальные образы и Helm-чарты (офлайн‑загрузка через Nexus)
У вас есть Nexus с Интернетом — делайте его центральным кешем/прокси, а в изолированном контуре все ноды должны тянуть только через него.

### Nexus: Helm proxy/hosted
Nexus поддерживает Helm proxy репозитории: создаёте репозиторий `helm (proxy)` и задаёте Remote storage URL (например, `https://charts.helm.sh/stable` или нужный vendor repo). [help.sonatype](https://help.sonatype.com/en/helm-repositories.html)
Для внутренней публикации чартов создайте `helm (hosted)` и загружайте tgz (через UI или `curl --upload-file`). [help.sonatype](https://help.sonatype.com/en/helm-repositories.html)

Как использовать с клиента Helm:
- `helm repo add <name> http://<nexus-host>:8081/repository/<helm-proxy>/ --username ... --password ...` [help.sonatype](https://help.sonatype.com/en/helm-repositories.html)

### Nexus: Docker proxy (для образов) + containerd mirrors
В Nexus создайте `docker (proxy)` и укажите Remote storage `https://registry-1.docker.io` (или quay/ecr/ghcr — отдельными proxy‑репо) и включите Docker Bearer Token Realm (Security → Realms). [sysadmintalks](https://sysadmintalks.ru/nexus-docker-proxy/)
Docker proxy в Nexus обычно требует отдельного порта (HTTP connector), который вы укажете при создании репозитория `docker (proxy)`. [sysadmintalks](https://sysadmintalks.ru/nexus-docker-proxy/)

Настройка containerd на нодах на использование Nexus как mirror:
- Для containerd (пример из практики): в конфиге добавляется mirror для `docker.io` с endpoint на ваш Nexus Docker proxy. [sysadmintalks](https://sysadmintalks.ru/nexus-docker-proxy/)
- В варианте с отдельными `hosts.toml` (в зависимости от вашей версии containerd и конфигурации) создаётся `/etc/containerd/certs.d/docker.io/hosts.toml` и прописывается host вашего Nexus как endpoint для pull/resolve. [sysadmintalks](https://sysadmintalks.ru/nexus-docker-proxy/)

Минимально необходимое правило эксплуатации: **запретить прямой egress** на DockerHub/Quay из нод и разрешить только Nexus, иначе кеш будет неполным и “воспроизводимость” потеряется.

## 4) Совместимые версии для k8s v1.24
Так как кластер обновлять нельзя, ориентируйтесь на “подходящие” версии вокруг 1.24 и правила version-skew.

- Kubernetes компоненты (kubeadm/kubelet/kubectl):
  - Держите их в одной minor-версии 1.24.x (разный patch допускается), и следите за version-skew политикой между компонентами (особенно kubelet ↔ apiserver). [kubernetes](https://kubernetes.io/releases/version-skew-policy/)
- Container runtime:
  - Начиная с Kubernetes 1.24 dockershim удалён, нужен CRI‑runtime (containerd/CRI-O). [kubernetes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/)
  - Для выбора точной версии containerd используйте матрицу совместимости containerd↔Kubernetes (ориентируйтесь на ветку containerd 1.6.x как типичную для эпохи k8s 1.24; точный выбор закрепляйте тестом в стейдже). [deepwiki](https://deepwiki.com/containerd/containerd.io/2.4-kubernetes-compatibility)
- Ingress:
  - У вас nginx ingress controller v1.9.1; проверяйте матрицу совместимости ingress‑nginx с Kubernetes при фиксации/апдейте patch‑версий контроллера (даже без апгрейда k8s). [kubernetes](https://kubernetes.io/blog/2021/07/26/update-with-ingress-nginx/)

Если хотите — перечислю “рекомендуемые pin’ы” (kubelet/kubeadm/containerd/cilium/ingress-nginx) именно для вашей ОС/дистрибутива, но для этого нужно: какой Linux на нодах, как ставили kubeadm/kubelet (deb/rpm/тарбол), и текущая версия containerd.

## 5) Тюнинг для High Load (без апгрейда k8s)
Ниже — то, что обычно даёт максимальный эффект на 1.24, не требуя смены версии, но требует аккуратного теста.

- Control-plane и etcd:
  - Выделите ресурсы (CPU/RAM/IOPS) под etcd; диски NVMe/SSD, latency важнее throughput.
  - Проверьте флаги etcd и лимиты (compaction/defrag/quotas), частоту snapshot’ов и размер базы; делайте регулярную maintenance (особенно если много объектов/лейблов/CRD).
- kube-apiserver:
  - Проверьте `--max-requests-inflight`, `--max-mutating-requests-inflight`, `--default-watch-cache-size`, параметры audit (слишком подробный audit может “убить” IO).
  - Следите за количеством watchers (Prometheus, controllers, операторы): они грузят watch cache.
- kubelet/containerd:
  - Image GC, eviction thresholds, maxPods, file descriptors, conntrack.
  - Для containerd: настройте registry mirrors на Nexus и лимиты параллелизма pull, чтобы не упираться в сеть/диск.
- Cilium:
  - Проверьте режим (tunnel vs native routing), kube-proxy replacement, Hubble (если включён), BPF map sizes; на high PPS это критично.
- Ingress-NGINX:
  - Тюнинг worker_processes/worker_connections, keepalive, upstream keepalive, buffering, timeouts; масштабирование контроллера (replicas/daemonset), topology spread.
- План емкости:
  - Отдельно посчитать: apiserver QPS, etcd ops/s, p95 latency на API, число объектов в etcd, число pod’ов/endpoint’ов/service’ов, conntrack usage.

***

Какие вводные нужны, чтобы сделать план “под ключ” (с конкретными командами и чек-листом ожидаемых значений):
1) Как разворачивали кластер: kubeadm? rancher? kubespray? self-made?  
2) ОС/ядро на мастерах/воркерах, версии containerd (`containerd --version`) и runc.  
3) Где именно крутится etcd (static pod? deployment? отдельный контейнер вне k8s?) и какие пути к certs/data-dir.  
4) Нужны ли офлайн‑зеркала только для DockerHub, или ещё quay.io/ghcr.io/k8s.gcr.io(registry.k8s.io) и репозитории Cilium/Ingress.

Если ответите на эти 4 пункта — дам точный пошаговый runbook (команды, структура каталогов бэкапов, политики в Nexus, и “золотые” pin-версии под ваш стек).
