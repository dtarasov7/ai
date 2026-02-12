Ниже — практичный чек‑лист именно **настройки ОС (РЕД ОС 7.3)** для worker‑ноды под **Kubernetes 1.24** с целью **поднять лимит до ~500 Pod’ов**. Я разделю на: *обязательный минимум* (чтобы нода вообще корректно работала) и *донастройки под высокую плотность Pod’ов*.

---

## 0) Важные вводные (чтобы не наступить на «мины»)

1) **Kubernetes 1.24 уже EOL** (ветка 1.24 закончила жизненный цикл **2023‑07‑28**, финальный патч 1.24.17 вышел уже “после EOL” под CVE). Если это прод — стоит иметь в виду риски безопасности и совместимости.   

2) В **Kubernetes 1.24 удалён dockershim**, то есть worker‑ноды должны работать с **CRI‑runtime** (обычно `containerd` или `CRI-O`, либо Docker через `cri-dockerd`).   

3) **500 Pod’ов на одной ноде** — это выше дефолта (110) и может упереться не в CPU/RAM, а в:
- сеть (CNI/IP‑адреса на ноду, iptables/ipvs, conntrack),
- PID’ы/limits systemd,
- файловые дескрипторы / inotify,
- производительность kubelet / containerd.  
Сам лимит kubelet задаётся параметром `maxPods` (дефолт **110**).   

---

## 1) Обязательные настройки ОС для worker node (РЕД ОС 7.3 + containerd + k8s 1.24)

Ниже — то, что прямо требуется/рекомендуется в документации Kubernetes и базе знаний РЕД ОС.

### 1.1 Отключить swap (и навсегда)
Kubelet по умолчанию не стартует при включенном swap (параметр `failSwapOn` по умолчанию `true`).   

По РЕД ОС (и это же типовой подход):
```bash
swapoff -a
swapoff -a && sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
```
  

---

### 1.2 Загрузить нужные модули ядра (overlay, br_netfilter)
```bash
cat > /etc/modules-load.d/containerd.conf <<'EOF'
overlay
br_netfilter
EOF

modprobe overlay
modprobe br_netfilter
lsmod | egrep "br_netfilter|overlay"
```
  

---

### 1.3 Проставить sysctl для сетевой части Kubernetes (bridge + forwarding)
```bash
cat > /etc/sysctl.d/99-kubernetes-cri.conf <<'EOF'
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
EOF

sysctl --system
```
  

---

### 1.4 Разрешить FORWARD (важно для Pod networking)
В инструкции РЕД ОС для Kubernetes 1.24 отдельно выставляют policy:
```bash
iptables -P FORWARD ACCEPT
```
  

> Если у вас включён firewall/зональная политика — лучше аккуратно оформить правила (а не просто ACCEPT везде), но **суть**: форвардинг трафика между интерфейсами для pod‑сети должен работать.

---

### 1.5 containerd: включить systemd‑cgroup драйвер
Kubernetes прямо подчёркивает: kubelet и runtime должны использовать **один и тот же cgroup driver**, и при systemd как init — обычно выбирают **systemd**.   

По РЕД ОС:
```bash
containerd config default > /etc/containerd/config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml

systemctl enable --now containerd
systemctl enable kubelet.service
```
  

---

### 1.6 Убедиться, что вы не «случайно» на cgroup v2 без тестов
cgroup v2 стал **stable только с Kubernetes 1.25**, а в 1.24 это ещё не GA.   

Проверка:
```bash
stat -fc %T /sys/fs/cgroup/
```
- `cgroup2fs` = cgroup v2
- `tmpfs` (с отдельными mount’ами контроллеров) = cgroup v1  
  

---

## 2) Донастройки ОС под 500 Pod’ов на одной ноде (самое полезное)

Это не «одна волшебная конфигурация», а набор типовых узких мест, которые на плотных нодах всплывают первыми.

### 2.1 PID’ы / systemd TasksMax (защита от PID exhaustion)
Kubernetes отдельно отмечает, что PID’ы легко «закончить», иногда при довольно низких дефолтах ОС.   

Что сделать на ОС:
1) Посмотреть текущие лимиты:
```bash
sysctl kernel.pid_max
ulimit -u
systemctl show --property=DefaultTasksMax
```

2) Практика для плотных нод: поднять PID и убрать/поднять TasksMax хотя бы для `kubelet` и `containerd` (иначе можно упереться в systemd‑лимиты задач при росте Pod’ов).

Пример override для systemd (идея):
```bash
mkdir -p /etc/systemd/system/kubelet.service.d
cat > /etc/systemd/system/kubelet.service.d/10-limits.conf <<'EOF'
[Service]
TasksMax=infinity
LimitNPROC=infinity
EOF

mkdir -p /etc/systemd/system/containerd.service.d
cat > /etc/systemd/system/containerd.service.d/10-limits.conf <<'EOF'
[Service]
TasksMax=infinity
LimitNPROC=infinity
EOF

systemctl daemon-reload
systemctl restart containerd kubelet
```

---

### 2.2 Файловые дескрипторы + inotify (часто «внезапная» причина проблем)
При большом числе Pod’ов растут:
- открытые файлы/сокеты,
- количество inotify watchers (особенно если много приложений, которые активно следят за файлами).

Сами параметры `fs.file-max`, `fs.nr_open`, `fs.inotify.*` — стандартные sysctl’ы ОС (в документации облачных k8s‑провайдеров они прямо вынесены как настраиваемые параметры).   

Пример разумного стартового тюнинга (под вашу RAM можно смело выше, но лучше мониторить):
```bash
cat > /etc/sysctl.d/98-k8s-density.conf <<'EOF'
# file descriptors
fs.file-max = 2097152
fs.nr_open = 2097152

# inotify (часто нужно для больших инсталляций)
fs.inotify.max_user_watches = 1048576
fs.inotify.max_user_instances = 8192
EOF

sysctl --system
```
  

Плюс проверьте `LimitNOFILE` для kubelet/containerd (systemd overrides), потому что один sysctl `fs.file-max` не гарантирует высокий лимит для конкретного сервиса.

> В kubelet есть отдельная настройка `maxOpenFiles` (дефолт 1,000,000), но это лимит **процесса kubelet**, и он всё равно упрётся в то, что разрешит systemd/ulimit на ноде.   

---

### 2.3 Conntrack и kube-proxy (особенно важно при NAT/Service трафике)
`kube-proxy` управляет conntrack‑параметрами и имеет настройки:
- `--conntrack-max-per-core` (дефолт **32768**)
- `--conntrack-min` (дефолт **131072**)   

На **128 cores** дефолтная формула “per-core” потенциально даёт очень большой верхний предел (миллионы записей). Это может быть нормально на 1 ТБ RAM, но:
- проверьте фактическое значение `net.netfilter.nf_conntrack_max`,
- следите за `conntrack -S`, дропами и памятью,
- и лучше фиксировать настройки kube-proxy осознанно (через config kube-proxy), чем «как получится».

---

### 2.4 ipvs vs iptables (для 500 Pod’ов обычно IPVS проще масштабировать)
В РЕД ОС инструкции на k8s 1.24 ставят пакеты под IPVS (`ipvsadm`, `conntrack`, `ebtables` и т.п.).   
Если у вас kube-proxy в режиме iptables и много сервисов/эндпоинтов — правила могут разрастаться и деградировать. IPVS часто ведёт себя стабильнее на больших таблицах.

---

## 3) Настройка лимита Pod’ов до 500 (это не sysctl, но делается на ноде)

Чтобы реально получить 500 Pod’ов на worker’е, нужно задать kubelet:
- `maxPods: 500` (дефолт 110)   
- при необходимости `podsPerCore: 0` (чтобы не ограничивало по ядрам)   

Где обычно править:
- kubeadm‑кластеры: `/var/lib/kubelet/config.yaml` (и/или через kubeadm KubeletConfiguration),
- затем `systemctl restart kubelet`.

---

## 4) Две проверки, без которых «500 Pod’ов» часто не взлетает

1) **PodCIDR / пул адресов CNI**  
Если у вас на ноду выдаётся, например, `/24`, то там физически не хватит IP под 500 Pod’ов. Это уже не настройка ОС, но это самый частый блокер.

2) **Ёмкость ephemeral ports при SNAT**  
При массовом egress‑трафике можно упереться в диапазон исходящих портов. В Kubernetes `net.ipv4.ip_local_port_range` считается “safe sysctl” (его можно менять безопасно).   
На уровне ОС часто расширяют диапазон, например до `1024 65535` (если не конфликтует с NodePort/политиками).

---

## 5) Мини‑чеклист “готова ли нода”
```bash
# swap
swapon --show

# модули
lsmod | egrep "overlay|br_netfilter"

# sysctl
sysctl net.ipv4.ip_forward net.bridge.bridge-nf-call-iptables net.bridge.bridge-nf-call-ip6tables

# runtime
containerd --version
crictl info | head

# kubelet видит runtime и поднялся
systemctl status kubelet --no-pager
journalctl -u kubelet -n 50 --no-pager
```

---

### Небольшой, но важный “практический” совет
Если цель именно **уплотнение**, часто надёжнее (по отказоустойчивости и обслуживанию) разрезать один “монстр‑сервер” на 2–4 worker‑ноды (VM/metal‑виртуализация), чем держать 500 Pod’ов на одном kubelet. Но если у вас жёсткое требование “одна железка = одна нода”, то настройки выше — базовый минимум, чтобы это не ломалось на ровном месте.

--- 

Если нужно — могу дать **готовые файлы** (`sysctl.d`, `modules-load.d`, systemd drop-in’ы) “как шаблон” именно под РЕД ОС 7.3 и kubeadm/kubelet, чтобы вы просто развернули их через Ansible и получили воспроизводимую конфигурацию.
