# Лаборатория K3s + Istio на РЕД ОС 8

Инструкция для предварительной проверки механизмов Istio при ограничении **10 ГБ
RAM на весь компьютер**. Создайте одну ВМ: **4 vCPU, 8 ГБ RAM, SSD 80 ГБ**,
РЕД ОС 8 x86_64 в минимальной серверной установке без графики. Остальную память
оставьте основной ОС. Если все 10 ГБ выделены отдельному серверу, можно использовать
их целиком. Это оценка для небольшого стенда, а не гарантированный максимум нагрузки.

Дата подготовки: 28.10.2026. Команды выполняются **на новой выделенной ВМ**.
Существующий кластер и Docker не нужны: K3s устанавливает собственный containerd.

## 1. Состав и версии

| Компонент | Зафиксированная версия / настройка |
|---|---|
| K3s | `v1.29.15+k3s1`, одноузловой server с SQLite |
| Kubernetes | `v1.29.15` внутри K3s |
| Istio | `1.21.6`, sidecar mode, один istiod |
| Gateway | Один Envoy, Service NodePort, HTTP `30080` |
| CNI / DNS | Штатные Flannel и CoreDNS из K3s |
| Traefik / ServiceLB | Выключены: вход обслуживает Istio через NodePort |
| Хранилище | Штатный local-path; базовые опыты не требуют PVC |
| Наблюдаемость | На первом этапе — `kubectl logs`, метрики Envoy и `kubectl top` |

Версии выбраны для близости к ветке Istio 1.21, используемой по умолчанию в
[исходниках Deckhouse 1.73.4](https://github.com/deckhouse/deckhouse/blob/v1.73.4/modules/110-istio/openapi/config-values.yaml).
Это не точная копия сборки Deckhouse: патчи, CNI, интеграция и настройки различаются.

Istio 1.21 поддерживал Kubernetes 1.26–1.29; сейчас обе выбранные ветки устарели.
Используйте стенд в лабораторной сети, без рабочих данных и публикации в Интернет.
Для нового рабочего кластера эти версии выбирать не следует.
Источники: [матрица Istio](https://istio.io/latest/docs/releases/supported-releases/),
[релиз Istio 1.21.6](https://github.com/istio/istio/releases/tag/1.21.6),
[релиз K3s](https://docs.k3s.io/release-notes-old/v1.29.X).

Prometheus, Kiali, Grafana, Jaeger и центральное хранилище логов в базовый состав
не входят. Для пунктов 5 и 19 они потребуют отдельной настройки и проверки памяти.
Не устанавливайте одновременно весь каталог `samples/addons`.

## 2. Доступы и сеть

ВМ должна иметь постоянный IPv4, доступный с вашей рабочей машины.
Далее `192.168.122.50` — **пример**, замените своим адресом.

Нужен исходящий HTTPS-доступ к GitHub (включая серверы release assets),
`get.k3s.io`, registry образов K3s и `docker.io` для Istio/Python,
а также доступ к репозиториям РЕД ОС. Если узел выходит через proxy или внутренний
registry, сначала настройте [proxy K3s](https://docs.k3s.io/advanced#configuring-an-http-proxy)
и [registries.yaml](https://docs.k3s.io/installation/private-registry).
Эта инструкция предполагает прямое подключение к Интернету.

Подсети K3s `10.42.0.0/16` (Pod) и `10.43.0.0/16` (Service) не должны пересекаться
с вашей LAN, VPN и маршрутами ВМ. Их нужно выбрать до установки.

На ВМ откройте root shell и выполняйте дальнейшие шаги в нём:

```bash
sudo -i
export LAB_IP=192.168.122.50
export LAB_DIR=/root/istio-lab
mkdir -p "$LAB_DIR"
cd "$LAB_DIR"
cat /etc/os-release
uname -m
ip -4 address
ip route
free -h
df -h /
```

Ожидается `x86_64`; `LAB_IP` должен действительно принадлежать интерфейсу ВМ.
При открытии нового root shell повторяйте два `export` и переход в `LAB_DIR`.
В этой инструкции `kubectl` запускается на ВМ, поэтому открывать Kubernetes API
на рабочую машину для первого прогона необязательно.

## 3. Подготовка РЕД ОС

```bash
dnf install -y curl tar gzip ca-certificates openssl python3 iproute iptables \
  procps-ng chrony policycoreutils
# python3 выше — название пакета ОС; в сценариях вызывается команда python.
# Проверяем её наличие и версию до установки: нужен Python 3.8 или более новый.
command -v python
python --version
systemctl enable --now chronyd
timedatectl status
hostnamectl set-hostname istio-lab
```

Нужно корректное время: оно влияет на сертификаты mTLS и срок действия JWT.

### Swap и сетевые параметры

В лаборатории отключаем swap; нехватку RAM нужно видеть по фактическому потреблению.
Сначала сохраните исходный fstab и проверьте существующие swap-записи.

```bash
cp -n /etc/fstab "$LAB_DIR/fstab.before-k3s"
swapon --show
swapoff -a
sed -i '/^[[:space:]]*#/!{/[[:space:]]swap[[:space:]]/s/^/# k3s-lab: /;}' /etc/fstab
modprobe overlay
modprobe br_netfilter
cat > /etc/modules-load.d/k3s-lab.conf <<'CONF'
overlay
br_netfilter
CONF
cat > /etc/sysctl.d/90-k3s-lab.conf <<'CONF'
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
CONF
sysctl --system
swapon --show
```

Последняя команда должна вывести пустой список. Если swap создаёт systemd/zram,
а не fstab, отключите соответствующий генератор/сервис по конфигурации вашей ВМ
и повторите проверку после перезагрузки до установки K3s.

### SELinux

Для этого небольшого стенда выбираем **permissive**, чтобы не зависеть от установки
Rancher SELinux RPM на РЕД ОС. Это осознанное упрощение лаборатории, не инструкция
по проверке SELinux или настройке защищённого рабочего кластера.

```bash
getenforce
cp -n /etc/selinux/config "$LAB_DIR/selinux-config.before-k3s"
if [ "$(getenforce)" = Enforcing ]; then
  setenforce 0
fi
sed -i 's/^SELINUX=enforcing$/SELINUX=permissive/' /etc/selinux/config
getenforce
```

Продолжайте при `Permissive` либо `Disabled`. Сохранённый ранее `Disabled` не меняем.
При необходимости оставить `Enforcing` нужен отдельный проверенный комплект
политик для вашей ОС; нельзя просто пропустить SELinux RPM и сохранить enforcing.
[Поддержка SELinux в K3s](https://docs.k3s.io/advanced#selinux-support).

### Firewalld

Если firewalld активен, разрешите трафик внутренних сетей и тестовый NodePort.
`--add-port` использует default zone: убедитесь, что сетевой интерфейс ВМ находится
в ней, либо укажите его фактическую зону через `--zone=<имя>` в командах открытия портов.

```bash
if systemctl is-active --quiet firewalld; then
  firewall-cmd --get-active-zones
  firewall-cmd --get-default-zone
  firewall-cmd --permanent --zone=trusted --add-source=10.42.0.0/16
  firewall-cmd --permanent --zone=trusted --add-source=10.43.0.0/16
  firewall-cmd --permanent --add-port=30080/tcp
  firewall-cmd --reload
fi
```

Если нужен удалённый `kubectl`, дополнительно откройте `6443/tcp` для доверенной
рабочей машины на firewall ВМ/гипервизора. Межузловой VXLAN здесь не нужен:
узел единственный. При собственных nftables-правилах настройте их эквивалентно.
[Сетевые требования K3s](https://docs.k3s.io/installation/requirements).

## 4. Установка K3s

Сохраняем параметры в конфигурационном файле. Если такой файл уже существует,
остановитесь: инструкция предназначена для новой ВМ, а не замены чужой конфигурации.

```bash
install -d -m 0755 /etc/rancher/k3s
set -e
test ! -e /etc/rancher/k3s/config.yaml
cat > /etc/rancher/k3s/config.yaml <<CONF
node-name: istio-lab
node-ip: "$LAB_IP"
advertise-address: "$LAB_IP"
tls-san:
  - "$LAB_IP"
write-kubeconfig-mode: "0600"
cluster-domain: cluster.local
cluster-cidr: 10.42.0.0/16
service-cidr: 10.43.0.0/16
selinux: false
disable:
  - traefik
  - servicelb
CONF
curl --fail --location --retry 3 https://get.k3s.io -o "$LAB_DIR/install-k3s.sh"
INSTALL_K3S_VERSION='v1.29.15+k3s1' \
INSTALL_K3S_SKIP_SELINUX_RPM=true \
INSTALL_K3S_SYMLINK=skip \
  sh "$LAB_DIR/install-k3s.sh" server
```

Не выполняйте последующий `cat`, если `test` показал существующий файл.
При запуске блоком в Bash можно перед этим включить `set -e`, чтобы ошибка
автоматически прервала выполнение. Просмотрите скачанный installer перед запуском;
`INSTALL_K3S_VERSION` фиксирует бинарник K3s, сам installer загружается текущий.
Сохраните installer вместе с протоколом установки.

Создаём отдельную команду kubectl для этой ВМ. На ней не должно быть ранее
установленного kubectl; если он уже есть, используйте `k3s kubectl` вместо symlink.

```bash
if ! command -v kubectl >/dev/null 2>&1; then
  ln -s /usr/local/bin/k3s /usr/local/bin/kubectl
fi
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl config current-context
systemctl is-active k3s
kubectl wait --for=condition=Ready node/istio-lab --timeout=180s
kubectl -n kube-system rollout status deployment/coredns --timeout=180s
kubectl get nodes -o wide
kubectl get pods -A -o wide
k3s --version
```

Ожидается один узел `Ready`, версия `v1.29.15+k3s1`, работающий CoreDNS;
Traefik и ServiceLB отсутствуют. При первом скачивании образов ожидание может
потребоваться повторить после устранения ошибок registry.

При открытии нового root shell снова выполните:

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```

Исходный kubeconfig обновляет K3s, поэтому на самой ВМ используем именно его.
[Установка и конфигурация K3s](https://docs.k3s.io/installation/configuration).

## 5. Установка Istio с ограничением ресурсов

Скачиваем конкретный выпуск для Linux x86_64 и устанавливаем его CLI.

```bash
cd "$LAB_DIR"
curl --fail --location --retry 3 \
  https://github.com/istio/istio/releases/download/1.21.6/istio-1.21.6-linux-amd64.tar.gz \
  -o istio-1.21.6-linux-amd64.tar.gz
tar -xzf istio-1.21.6-linux-amd64.tar.gz
install -m 0755 istio-1.21.6/bin/istioctl /usr/local/bin/istioctl
istioctl version --remote=false
istioctl x precheck
```

Далее — файл параметров для маленького стенда. requests — резерв планировщика,
limits — верхние границы контейнера; это не обещание фактического потребления.
Автомасштабирование выключено, чтобы не появлялись дополнительные реплики.

```bash
cat > "$LAB_DIR/istio-small.yaml" <<'YAML'
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: lab
  namespace: istio-system
spec:
  profile: default
  hub: docker.io/istio
  tag: 1.21.6
  meshConfig:
    enableTracing: false
  components:
    pilot:
      k8s:
        replicaCount: 1
        resources:
          requests:
            cpu: 250m
            memory: 256Mi
          limits:
            cpu: "1"
            memory: 768Mi
    ingressGateways:
      - name: istio-ingressgateway
        enabled: true
        k8s:
          replicaCount: 1
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: "1"
              memory: 256Mi
          service:
            type: NodePort
            ports:
              - name: status-port
                port: 15021
                targetPort: 15021
                nodePort: 31021
              - name: http2
                port: 80
                targetPort: 8080
                nodePort: 30080
              - name: https
                port: 443
                targetPort: 8443
                nodePort: 30443
  values:
    pilot:
      autoscaleEnabled: false
    gateways:
      istio-ingressgateway:
        autoscaleEnabled: false
    global:
      proxy:
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: "1"
            memory: 256Mi
YAML
istioctl install -y -f "$LAB_DIR/istio-small.yaml"
kubectl -n istio-system rollout status deployment/istiod --timeout=180s
kubectl -n istio-system rollout status deployment/istio-ingressgateway --timeout=180s
kubectl -n istio-system get deployment,service,pod
kubectl -n istio-system get hpa
istioctl version
```

Ожидаются по одной реплике istiod и gateway, отсутствие HPA, HTTP NodePort 30080.
HTTPS-порт зарезервирован, но TLS listener и сертификат пока не настроены.
ServiceLB выключен, поэтому используем `http://<IP-ВМ>:30080`, а не внешний IP
LoadBalancer. Файл IstioOperator читает CLI; отдельный постоянно работающий
Istio operator не устанавливается.

Если установка не проходит проверку, не добавляйте `--force`: сначала разберите
ошибку API/образов и журнал Pod. Параметры маленького istiod основаны на
[values Istio 1.21.6](https://github.com/istio/istio/blob/1.21.6/manifests/charts/istio-control/istio-discovery/values.yaml).

## 6. Контрольный опыт: injection, маршрут и STRICT mTLS

Создаём отдельный namespace с backend и двумя клиентами: mesh и plaintext.
Нужен доступ узла к образу `python:3.12-alpine`; это только пример образа.
Код совместим с Python 3.8 и использует бинарник `python`. При необходимости замените образ
во всех трёх Pod на полное имя образа вашего registry.

```bash
kubectl create namespace istio-smoke
kubectl label namespace istio-smoke istio-injection=enabled
kubectl -n istio-smoke apply -f - <<'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: backend
  labels:
    app: backend
spec:
  containers:
    - name: app
      image: python:3.12-alpine
      command: [python, -m, http.server, "8080"]
      ports:
        - containerPort: 8080
      readinessProbe:
        httpGet:
          path: /
          port: 8080
      resources:
        requests:
          cpu: 20m
          memory: 32Mi
        limits:
          memory: 128Mi
---
apiVersion: v1
kind: Service
metadata:
  name: backend
spec:
  selector:
    app: backend
  ports:
    - name: http
      port: 8080
      targetPort: 8080
---
apiVersion: v1
kind: Pod
metadata:
  name: client
spec:
  containers:
    - name: app
      image: python:3.12-alpine
      command: [python, -c, "import time; time.sleep(86400)"]
      resources:
        requests:
          cpu: 20m
          memory: 32Mi
        limits:
          memory: 128Mi
---
apiVersion: v1
kind: Pod
metadata:
  name: plain
  annotations:
    sidecar.istio.io/inject: "false"
spec:
  containers:
    - name: app
      image: python:3.12-alpine
      command: [python, -c, "import time; time.sleep(86400)"]
      resources:
        requests:
          cpu: 20m
          memory: 32Mi
        limits:
          memory: 128Mi
---
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: strict
spec:
  selector:
    matchLabels:
      app: backend
  mtls:
    mode: STRICT
YAML
kubectl -n istio-smoke wait --for=condition=Ready pod --all --timeout=180s
kubectl -n istio-smoke get pods
istioctl proxy-status
```

У `backend` и `client` должно быть `2/2` контейнера Ready, у `plain` — `1/1`.
В `proxy-status` backend и client должны иметь состояние `SYNCED`.

### Положительная проверка из mesh

```bash
kubectl -n istio-smoke exec -i client -c app -- python - <<'PYTHON'
# Стандартная библиотека Python 3.8; внешние pip-пакеты для HTTP не нужны.
import urllib.request

# Запрос исполняется внутри mesh-клиента; DNS Kubernetes находит тестовый Service.
url = "http://backend.istio-smoke.svc.cluster.local:8080/"
# Не ждём недоступный backend бесконечно: ограничиваем ожидание пятью секундами.
with urllib.request.urlopen(url, timeout=5) as response:
    # Сохраняем реальный HTTP-код и показываем его проверяющим.
    status = response.status
    print("mesh client:", status)
    # Успешный mesh-вызов должен остаться рабочим и после проверки отказа plaintext.
    assert status == 200, status
PYTHON
```

### Отказ plaintext-клиенту

Правило mTLS распространяется асинхронно. Проверяем отказ после успешного
mesh-вызова; при сетевой ошибке на обоих клиентах считать опыт пройденным нельзя.

```bash
kubectl -n istio-smoke exec -i plain -c app -- python - <<'PYTHON'
import time
import urllib.error
import urllib.request

# Тот же адрес проверяется из Pod без sidecar: автоматического mTLS у него нет.
url = "http://backend.istio-smoke.svc.cluster.local:8080/"
# Даём правилу STRICT распространиться: до 30 попыток с короткими паузами.
for attempt in range(30):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            print("Ожидаем STRICT, пока получен HTTP", response.status)
    except urllib.error.HTTPError as error:
        # HTTP-отказ политики ещё не доказывает отказ TLS-соединения.
        raise SystemExit(f"Получен HTTP {error.code}; это не доказательство STRICT mTLS")
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        # Ожидается именно разрыв/отказ соединения: обычный HTTP не проходит STRICT.
        print("Ожидаемый отказ соединения без mTLS:", error)
        break
    time.sleep(1)
# else цикла выполняется, только если не было ни одного ожидаемого отказа с break.
else:
    raise SystemExit("ОШИБКА: plaintext всё ещё разрешён")
PYTHON
kubectl -n istio-smoke get peerauthentication strict -o yaml
```

Повторите положительную mesh-проверку после отказа plaintext. Результат:
HTTP 200 через mesh и отказ обычного HTTP от клиента без proxy при STRICT.
Это контрольный опыт аутентификации канала, а не отдельная проверка бизнес-прав.

## 7. Контрольный опыт: вход через NodePort gateway

```bash
kubectl -n istio-smoke apply -f - <<'YAML'
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: smoke
spec:
  selector:
    istio: ingressgateway
  servers:
    - port:
        number: 80
        name: http
        protocol: HTTP
      hosts:
        - smoke.example.invalid
---
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: smoke
spec:
  hosts:
    - smoke.example.invalid
  gateways:
    - smoke
  http:
    - match:
        - uri:
            exact: /allowed
      rewrite:
        uri: /
      route:
        - destination:
            host: backend.istio-smoke.svc.cluster.local
            port:
              number: 8080
YAML
istioctl analyze -n istio-smoke
curl --noproxy '*' --fail --show-error --max-time 5 \
  -H 'Host: smoke.example.invalid' "http://${LAB_IP}:30080/allowed"
curl --noproxy '*' --silent --show-error --max-time 5 \
  -o /dev/null -w '%{http_code}\n' \
  -H 'Host: smoke.example.invalid' "http://${LAB_IP}:30080/blocked"
```

После распространения конфигурации `/allowed` возвращает страницу backend с
кодом 200, `/blocked` — 404. При первом 404 на `/allowed` проверьте `proxy-status`
и повторите запрос. Обычная HTML-страница Python — ожидаемый результат.

Те же два curl-запроса выполните **с рабочей машины**, подставив реальный IP ВМ
вместо `${LAB_IP}` либо задав переменную и там. Это проверяет внешний вход;
локальный запрос на самой ВМ не подтверждает настройки firewall гипервизора.
DNS для `smoke.example.invalid` не нужен — имя передаётся в Host.
Вход от рабочего места до gateway в этом опыте HTTP; gateway → backend использует
автоматический mTLS, так как backend с sidecar и STRICT.

## 8. Контроль RAM и диагностика

```bash
free -h
kubectl top nodes
kubectl top pods -A --sort-by=memory
kubectl describe node istio-lab
kubectl get pods -A
kubectl get events -A --sort-by=.lastTimestamp
journalctl -u k3s -n 100 --no-pager
kubectl -n istio-system logs deployment/istiod --tail=100
```

`kubectl top` начнёт работать после готовности metrics-server и первых измерений;
это не требует Prometheus. Для памяти хоста смотрите `available`, а не только `free`.
Ориентир — оставлять хотя бы 1–2 ГБ доступными перед следующим опытом; это запас
для этой лаборатории, а не норматив Kubernetes.

| Симптом | Что проверить |
|---|---|
| `ImagePullBackOff` | `kubectl describe pod`, DNS ВМ, HTTPS и registry credentials |
| Pod `Pending`, `Insufficient memory` | requests всех Pod через describe node; удалить закончившиеся опыты |
| `OOMKilled` / растут рестарты | describe pod, top pods; не снижать limits вслепую |
| Backend `1/1` вместо `2/2` | Метку namespace, webhook Istio, Ready istiod; после исправления пересоздать тестовый Pod |
| `istio-init` падает | Логи init-контейнера, iptables/br_netfilter, SELinux, права на NET_ADMIN |
| DNS внутри Pod не работает | CoreDNS, его логи, firewalld и доступность DNS из `/etc/resolv.conf` ВМ |
| NodePort недоступен с ПК | IP ВМ, маршруты/NAT гипервизора, TCP 30080, активную зону firewalld |
| Входящий 503 | Ready backend, endpoints и mTLS; compare proxy-status и журналы gateway |

После проверки установки удалите контрольный namespace, чтобы освободить память:

```bash
kubectl delete namespace istio-smoke --wait=true
```

Не держите все 19 испытаний одновременно. Для начала оставьте установленные
компоненты без дополнительных систем наблюдаемости.

## 9. Как это связано с каталогами 1–23

Дополнительно доступны [21: fault injection](21/README.md),
[22: retries](22/README.md) и [23: timeout](23/README.md): запускайте их
`01-prepare-k3s.sh`, затем обычные check/cleanup. Для них достаточно этого стенда.
[20: сервис на ВМ](20/README.md) требует отдельной ВМ с подключённым Istio-agent,
связью с control plane и mTLS identity. Обычного gateway на 30080 недостаточно.
Подготовка агента и ограничения РЕД ОС/версии описаны в README пункта 20.

**Скрипты `1–23/01-prepare.sh` рассчитаны на Deckhouse.** На чистом K3s
они остановятся на `kubectl get module istio`: ресурса Module здесь нет.
Это ожидаемая несовместимость предварительной проверки, а не ошибка установки.
В этой инструкции проверку установки выполняют самостоятельные опыты выше.

Во всех 19 каталогах подготовлены копии **`01-prepare-k3s.sh`**. В них проверка
Module заменена следующими проверками до создания тестовых ресурсов:

- rollout istiod завершён и имеется хотя бы одна готовая реплика;
- Service istiod имеет готовые endpoints;
- injection webhook указывает на Service нужного istiod в нужном namespace,
  использует `/inject` и непустой `caBundle`;
- CRD, необходимые конкретному пункту, имеют condition `Established`.

Исходные проверки версий API через `kubectl explain`, фактической injection
и работающего proxy сохранены. Проверка конфигурации webhook не заменяет реального
вызова: успешная injection подтверждается созданием и проверкой тестовых Pod далее.

Для стандартной установки из этой инструкции дополнительных параметров preflight
нет. Исключение — пункт 12: для адреса внешнего входа нужен `LAB_IP`, как ниже.
По умолчанию проверяются namespace `istio-system`, Deployment/Service `istiod`
и MutatingWebhookConfiguration `istio-sidecar-injector`.
Для установки в другом namespace задайте `ISTIO_NAMESPACE`. Если задан `ISTIO_REV`,
ожидаются имена `istiod-<ревизия>` и `istio-sidecar-injector-<ревизия>`;
это literal revision, а не revision tag. Метка namespace опыта использует ту же ревизию.

Например, из каталога пункта 1 на ВМ:

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
bash 01-prepare-k3s.sh
bash 02-check.sh
# Сохранить результат, затем очистить окружение, в том числе при сбое проверки.
bash 03-cleanup.sh
```

Выбирайте только один prepare за прогон: исходный и K3s-вариант создают одинаковый
namespace. Установка K3s/Istio выполняется заранее; копии не устанавливают компоненты.

Пункт 12 уже адаптирован в K3s-копиях: используется существующий gateway в
`istio-system`, selector `istio: ingressgateway`, exportTo в `istio-system`
и HTTP NodePort 30080. Из каталога `12` выполните:

```bash
export LAB_IP=192.168.122.50  # заменить своим IPv4-адресом ВМ
bash 01-prepare-k3s.sh
bash 02-check-k3s.sh
bash 03-cleanup-k3s.sh
```

`LAB_IP` нужен в prepare и check; `GATEWAY_CLASS`/`GATEWAY_URL` не задаются.
Check выполняйте с рабочей машины с kubeconfig, чтобы проверить внешний вход.
Prepare предварительно проверяет gateway и NodePort; cleanup удаляет только
namespace испытания. Описание — в [пункте 12](12/README.md#вариант-k3s).

Для полного комплекта остаются дополнительные условия:

- Для пункта 5 отдельно настроить нужные telemetry providers, сбор метрик,
  лог-хранилище и tracing backend. Базовая установка отключает tracing.
- Для пункта 19 подключить совместимый Kiali к Prometheus, собирающему метрики mesh.
  Без этих компонентов пункты 5/19 полностью не принимаются.

Остальные сетевые механизмы можно испытывать на K3s через `01-prepare-k3s.sh`.
Результат оформляется как проверка Istio на K3s; совместимость с Deckhouse,
его модулем и редакцией проверяется на целевой платформе отдельно.

## 10. Остановка и удаление стенда

Для паузы можно штатно выключить ВМ — после включения systemd запустит K3s.
Удалять кластер ради паузы не требуется.

Для полного удаления **данных этого одноузлового K3s-кластера** на выделенной ВМ:

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
istioctl uninstall --purge -y
kubectl delete namespace istio-system
/usr/local/bin/k3s-uninstall.sh
```

Uninstall K3s удаляет его локальные данные и хранилище local-path, включая PVC
размещённых там приложений. Выполнять только когда результаты опытов уже сохранены.
Если uninstall Istio не завершился, перед удалением K3s сохраните диагностику;
удаление самой ВМ также полностью удаляет лабораторию.

Настройки ОС (SELinux, swap, sysctl, firewall) uninstall K3s не возвращает.
Для чистого повторного прогона удобнее восстановить снимок новой ВМ,
сделанный до шага 3. При ручном возврате используйте сохранённые конфигурации
и удаляйте только добавленные для лаборатории правила.

## Проверка самой инструкции

Команды не выполнялись на РЕД ОС: доступа к такой ВМ в текущем окружении нет.
Bash-блоки проверены синтаксически, YAML и вложенный Python разобраны локально.
Установка пакетов, скачивание бинарников и реальное применение IstioOperator
требуют проверки на ВМ. В частности, инструкция не является подтверждением
сертифицированной совместимости K3s с РЕД ОС.
