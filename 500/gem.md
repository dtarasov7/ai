Для эффективной работы worker node с такими мощными ресурсами (128 ядер, 1 ТБ RAM) и высокой плотностью подов (500 шт.) на Red OS 7.3 (базируется на экосистеме RHEL/CentOS 7), необходимо выполнить глубокую настройку ядра Linux, лимитов и самого kubelet.

Стандартные настройки Linux рассчитаны на обычные серверы, и при запуске 500 подов вы гарантированно столкнетесь с проблемами (ARP-штормы, исчерпание файловых дескрипторов, ошибки inotify).

Ниже приведен чек-лист необходимых настроек.

---

### 1. Настройка параметров ядра (Sysctl)

Это самый критичный этап. Создайте файл конфигурации:
`sudo nano /etc/sysctl.d/99-k8s-high-density.conf`

Добавьте следующие параметры:

```ini
# --- Сеть и пересылка ---
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1

# --- Увеличение таблиц ARP (КРИТИЧНО для 500 подов) ---
# При большом кол-ве подов таблица соседей (ARP) переполняется, и сеть "встает"
net.ipv4.neigh.default.gc_thresh1 = 8192
net.ipv4.neigh.default.gc_thresh2 = 32768
net.ipv4.neigh.default.gc_thresh3 = 65536

# --- Conntrack (Отслеживание соединений) ---
# 500 подов могут создавать сотни тысяч соединений.
# Учитывая 1 ТБ RAM, можно ставить высокие значения.
net.netfilter.nf_conntrack_max = 2097152
net.netfilter.nf_conntrack_tcp_timeout_established = 86400

# --- Файловые дескрипторы и Inotify ---
# K8s и логирование используют много inotify вотчеров.
fs.inotify.max_user_watches = 1048576
fs.inotify.max_user_instances = 8192
fs.file-max = 10000000

# --- Настройки процессов ---
kernel.pid_max = 4194304
kernel.threads-max = 4194304

# --- Память (Swap отключен, OOM поведение) ---
vm.swappiness = 0
vm.overcommit_memory = 1
vm.panic_on_oom = 0
```

Примените настройки:
```bash
sudo sysctl --system
```
*Примечание: Если возникнет ошибка, что модули netfilter не загружены, выполните `modprobe br_netfilter` и `modprobe nf_conntrack` перед применением.*

---

### 2. Отключение Swap и настройка модулей

Kubernetes требует полного отключения swap.

1. **Отключить сейчас:**
   ```bash
   sudo swapoff -a
   ```
2. **Отключить навсегда:**
   Закомментируйте строку со swap в `/etc/fstab`.

3. **Загрузка модулей:**
   Создайте файл `/etc/modules-load.d/k8s.conf`:
   ```bash
   overlay
   br_netfilter
   nf_conntrack
   ```
   Включите их: `sudo systemctl restart systemd-modules-load`

---

### 3. Лимиты ресурсов (Ulimits)

Вам нужно увеличить лимиты открытых файлов для процессов (особенно для Container Runtime).

Создайте/отредактируйте `/etc/security/limits.d/k8s.conf`:

```ini
*       soft    nofile  1048576
*       hard    nofile  1048576
root    soft    nofile  1048576
root    hard    nofile  1048576
*       soft    nproc   unlimited
*       hard    nproc   unlimited
```

---

### 4. Настройка Kubelet (Kubernetes 1.24)

В версии 1.24 по умолчанию используется Containerd (dockershim удален). Вам нужно явно указать kubelet, что он может запускать 500 подов.

1.  Отредактируйте конфиг kubelet (обычно `/var/lib/kubelet/config.yaml`). Если его нет, параметры можно передать аргументами в systemd, но конфиг предпочтительнее.

    Найдите или добавьте параметр `maxPods`:
    ```yaml
    apiVersion: kubelet.config.k8s.io/v1beta1
    kind: KubeletConfiguration
    maxPods: 500
    # Рекомендуется также увеличить burst для событий
    eventBurst: 50
    eventRecordQPS: 25
    # Защита ноды от перегрузки (резерв ресурсов под ОС)
    systemReserved:
      cpu: "2000m"  # 2 ядра под ОС (у вас их 128, не жалко)
      memory: "4Gi" # 4 ГБ под ОС
    kubeReserved:
      cpu: "1000m"
      memory: "2Gi"
    ```

2.  Перезапустите kubelet:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart kubelet
    ```

---

### 5. Сетевая подсистема (CNI и IPVS)

Это критически важный момент для 500 подов.

1.  **IPVS vs Iptables:**
    При таком количестве подов и сервисов режим `iptables` (стандартный для kube-proxy) начинает сильно грузить процессор при обновлении правил.
    **Настоятельно рекомендуется переключить Kube-Proxy в режим IPVS.**
    Для этого на ноде должны быть установлены пакеты `ipset` и `ipvsadm`.
    В Red OS: `sudo yum install ipset ipvsadm`.

2.  **Размер подсети (Node CIDR):**
    Стандартная сеть ноды в K8s — `/24` (254 IP-адреса).
    Для 500 подов вам **не хватит** IP-адресов.
    В настройках вашего CNI (Calico, Cilium, Flannel) или в Controller Manager (`--node-cidr-mask-size`) нужно убедиться, что этой ноде выделяется минимум **/23** (510 адресов), а лучше **/22** (1022 адреса).

---

### 6. Настройка Container Runtime (Containerd)

Поскольку K8s 1.24 использует CRI, скорее всего у вас Containerd. Его конфиг `/etc/containerd/config.toml` стоит проверить.

Убедитесь, что используется Systemd Cgroup драйвер (стандарт для 1.24+):
```toml
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
  SystemdCgroup = true
```

---

### 7. Firewalld

На Red OS по умолчанию включен `firewalld`. Он часто конфликтует с правилами iptables, которые создает Kubernetes.
Рекомендация: **Отключить firewalld** и полагаться на CNI плагин и встроенные политики K8s.

```bash
sudo systemctl stop firewalld
sudo systemctl disable firewalld
```
Если политика безопасности требует включенного фаервола, необходимо добавить интерфейс CNI (обычно `cni0` или `calico+`) и интерфейс подов в зону `trusted` и разрешить маскарадинг.

### Итоговое резюме
1.  **Ядро:** Поднять лимиты ARP, conntrack, inotify (см. пункт 1).
2.  **Kubelet:** Прописать `maxPods: 500`.
3.  **Сеть:** Выделить подсеть `/23` или `/22` для этой ноды.
4.  **Режим:** Использовать IPVS вместо iptables для kube-proxy.
