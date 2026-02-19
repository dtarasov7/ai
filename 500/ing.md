Ок, профиль понятен: **8 vCPU / 16 GB**, **Kubernetes + nginx-ingress-controller**, **TLS termination**, **Cilium**. Для high load тут обычно упираются в **FD/ulimit**, **очереди/буферы TCP**, **эпhemeral ports**, и (очень часто) **conntrack/таблицы Cilium (BPF maps)** + CPU на TLS.

Ниже — что я бы менял на **ноде** в первую очередь (без “магии”, безопасные стартовые значения).

---

## 1) Лимиты файловых дескрипторов (самое частое)

### Sysctl

`/etc/sysctl.d/99-highload.conf`

```conf
fs.file-max = 2000000
```

### systemd лимиты для container runtime

nginx-ingress в контейнере наследует лимиты от runtime. Поднимите `LimitNOFILE` у **containerd** (или docker, если он у вас).

```ini
# systemctl edit containerd
[Service]
LimitNOFILE=1048576
LimitNPROC=1048576
```

Проверка:

* `cat /proc/$(pidof containerd)/limits`
* в контейнере ingress: `cat /proc/1/limits`

---

## 2) Очереди accept / backlog (всплески соединений и TLS)

```conf
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.core.netdev_max_backlog = 16384
```

Если при пиках видите `listen drops/overflows` (в `ss -s` / `netstat -s`) — это прям must-have.

---

## 3) Эфемерные порты (upstream коннекты к сервисам)

nginx ingress делает много исходящих коннектов к endpoints, поэтому:

```conf
net.ipv4.ip_local_port_range = 10240 65535
```

---

## 4) TCP keepalive / fin timeout (для большого числа коннектов)

```conf
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 5
```

---

## 5) Сетевые буферы (умеренно)

```conf
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
net.ipv4.tcp_rmem = 4096 87380 67108864
net.ipv4.tcp_wmem = 4096 65536 67108864
net.ipv4.tcp_mtu_probing = 1
```

---

## 6) BBR (часто помогает на WAN и по tail latency)

Если в вашем ядре доступен BBR:

```conf
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
```

Проверка:

* `sysctl net.ipv4.tcp_congestion_control`
* `sysctl net.core.default_qdisc`

---

## 7) Память/VM (чтобы не уходить в своп и держать кэши)

```conf
vm.swappiness = 10
vm.vfs_cache_pressure = 50
```

---

# Важное про Cilium (и почему “nf_conntrack_max” может быть не главным)

С Cilium (особенно в kube-proxy replacement / eBPF datapath) “классический” `net.netfilter.nf_conntrack_*` может **не быть вашим узким местом**, потому что часть state/conntrack живёт в **BPF maps Cilium**. Поэтому:

### Что проверить по Cilium на ноде

* Заполненность conntrack/мап:

  * `cilium status --verbose`
  * `cilium bpf ct list global | head` (или метрики)
* Метрики дропов:

  * `cilium metrics list` / Prometheus: `cilium_drop_count_total`, `cilium_errors_warnings_total`, etc.
* Hubble (если есть) — откуда дропы.

### Типовые действия (не sysctl, но критично)

* Увеличение размеров BPF conntrack / NAT tables (делается через ConfigMap/values Helm Cilium).
* Если включён **L7 policy / Envoy** в Cilium — это отдельная большая нагрузка (и тогда тюнинг “только sysctl” не спасает).

Я не буду гадать конкретные значения для Cilium maps без ваших текущих цифр (`ct/nat map max`, usage), но **симптом** простой: при нагрузке растут дропы/ошибки Cilium и connection resets/timeouts при нормальных sysctl.

---

# nginx-ingress (в связке с OS)

Хотя вы спросили про ОС, для TLS termination под high load обычно ещё 3 вещи “в лоб” дают эффект:

1. **worker_connections / worker_rlimit_nofile** (в конфиге nginx ingress через ConfigMap)
2. **reuseport** (часто включают для распределения accept по ядрам)
3. **keepalive** к upstream (чтобы не сжигать ephemeral ports и CPU на handshake)

Если это не настроено, OS-тюнинг будет упираться в сам nginx.

---

## Быстрые проверки “куда упираемся” (5 минут)

На ноде:

* `ss -s` (timewait, estab, orphan, listen drops)
* `netstat -s | egrep -i "listen|drop|overflow|retrans|SYN"`
* `cat /proc/sys/fs/file-nr` (FD usage)
* `top` / `pidstat -u 1` (CPU: nginx/ingress vs ksoftirqd vs cilium-agent)
* `mpstat -P ALL 1` (перекос по ядрам)
* `cilium status --verbose` + метрики дропов

---

## Готовый базовый sysctl-файл (можете применить сразу)

`/etc/sysctl.d/99-highload.conf`

```conf
fs.file-max = 2000000

net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.core.netdev_max_backlog = 16384

net.ipv4.ip_local_port_range = 10240 65535

net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 5

net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
net.ipv4.tcp_rmem = 4096 87380 67108864
net.ipv4.tcp_wmem = 4096 65536 67108864
net.ipv4.tcp_mtu_probing = 1

vm.swappiness = 10
vm.vfs_cache_pressure = 50

# опционально, если BBR доступен:
# net.core.default_qdisc = fq
# net.ipv4.tcp_congestion_control = bbr
```

Применить:

* `sysctl --system`

---

Если вы дадите **2 вывода** (можно просто вставить сюда):

1. `ss -s`
2. `cilium status --verbose` (без секретов)

— я скажу точнее, что из этого реально нужно именно вам (backlog/ports/FD vs Cilium ct/nat vs softirq/TLS CPU) и какие параметры Cilium стоит поднять.

