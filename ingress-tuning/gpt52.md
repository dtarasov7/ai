Ниже — практичный ответ именно под вашу ситуацию: **Kubernetes 1.24 (апгрейд нельзя), ingress-nginx controller 1.9.1, выделенный ingress‑сервер 8 vCPU / 16 GB RAM**.

## Коротко (самое важное)
1) **“Поднять версию ingress-nginx-controller” на Kubernetes 1.24 — в целом не рекомендую.** По официальной таблице совместимости **v1.9.1 тестировался с k8s 1.25–1.28**, а **последняя версия, где есть 1.24 в поддерживаемых — v1.8.4**.   
2) Дополнительно: проект **Ingress NGINX официально “retiring”** — best‑effort maintenance **до марта 2026**, дальше **не будет релизов/фиксов/секьюрити‑апдейтов**. Это прямой сигнал планировать миграцию на другой контроллер/Gateway API.   
3) **8 worker’ов на 8 vCPU — это нормально**: по умолчанию `worker-processes` = “auto/кол-во CPU”.   
4) Для HighLoad почти всегда дают максимальный эффект:
- лимиты ОС (fd/ports/backlog),
- keepalive (client + upstream),
- правильные `resources.requests` и **аккуратное отношение к CPU limits** (троттлинг).

---

## 1) Можно ли / нужно ли “поднять версию” ingress-nginx-controller?
С учётом **Kubernetes 1.24**:
- Вы сейчас на **ingress-nginx v1.9.1**, который **официально тестировался с k8s 1.25–1.28**.   
- Для **k8s 1.24** в таблице “supported versions” последняя строка — **v1.8.4 (k8s 1.24–1.27)**.   

Что это означает на практике:
- **Технически** 1.9.1 у вас может работать (раз уже работает), но вы **вне “tested matrix”** → выше риск “странных” багов/краевых случаев и меньше шансов на внятный апстрим‑саппорт.
- **Поднимать выше 1.9.1 на k8s 1.24** — ещё менее разумно (будете ещё дальше от tested matrix).

И отдельный фактор: **retirement проекта**. До **марта 2026** — best‑effort, потом обновлений не будет.   
Если это прод с HighLoad, я бы стратегически думал не про “апнуть controller”, а про план миграции (например, Envoy Gateway / Kong / Traefik / HAProxy / NGINX Inc controller и т.п.) — но это уже отдельная тема.

---

## 2) Почему у вас 8 nginx worker process и это ок
В ingress-nginx параметр `worker-processes` по умолчанию = **количество CPU** (“auto”).   
Поэтому на ноде с 8 vCPU вы и видите 8 worker’ов + 1 master — это нормальная базовая настройка для максимальной параллельности.

---

## 3) Настройки хоста (Linux) под HighLoad (самое “вкусное”)
NGINX (в роли reverse proxy) упирается в:
- backlog очереди accept,
- лимиты файловых дескрипторов,
- диапазон ephemeral ports (особенно когда есть много соединений NGINX→upstream),
- иногда conntrack (если много NAT/Service‑трафика).

### 3.1 Backlog / очередь входящих соединений
NGINX рекомендует смотреть и при необходимости увеличивать:
- `net.core.somaxconn`
- `net.core.netdev_max_backlog`   

Пример (как стартовые “вменяемые” значения):
```bash
# /etc/sysctl.d/99-ingress.conf
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 16384
```
(точные числа зависят от NIC/драйвера/пиков new connections; смысл — убрать очевидно низкие дефолты).   

### 3.2 File descriptors (ulimit / fs.file-max)
NGINX прямо отмечает: он может использовать **до 2 file descriptor на соединение** (клиентский сокет + upstream сокет), и при большом числе соединений надо поднимать лимиты:  
- `sys.fs.file_max` (системный лимит fd)
- `nofile` (user limit в limits.conf)   

Пример (стартовый, типовой для ingress‑нод):
```bash
# sysctl
fs.file-max = 1048576
```

И лимиты пользователя/сервиса (примерно):
```bash
# /etc/security/limits.conf (или systemd LimitNOFILE)
* soft nofile 1048576
* hard nofile 1048576
```

### 3.3 Ephemeral ports (важно для NGINX как proxy)
Если ingress активно проксирует в backend’ы и много коротких соединений/нет keepalive, можно упереться в ephemeral ports. NGINX советует при необходимости расширять `net.ipv4.ip_local_port_range` (пример: 1024–65000).   

Пример:
```bash
net.ipv4.ip_local_port_range = 1024 65000
```

### 3.4 Conntrack (часто забывают, а потом “мистические” дропы)
Если ingress‑нода активно участвует в сервисном NAT (kube-proxy iptables), conntrack может стать узким местом. В kube-proxy есть параметры conntrack (min/maxPerCore), а практическая формула настройки часто описывается как:
`nf_conntrack_max = max(min, maxPerCore * cpu_cores)` (и это увеличивает потребление RAM).   

---

## 4) Настройки ingress-nginx (ConfigMap/Service) под HighLoad

### 4.1 Соединения и keepalive (самый частый реальный буст)
**Downstream (клиент→ingress):**
- `keep-alive` (по умолчанию 75s)   
- `keep-alive-requests` (по умолчанию 1000)   

Для high concurrency часто имеет смысл увеличить `keep-alive-requests` до **10000**, чтобы уменьшить churn соединений / TIME_WAIT (особенно когда “один клиент льёт много запросов”). В облачных гайдах для high-traffic это прям типовая рекомендация.   

**Upstream (ingress→backend):**
- `upstream-keepalive-connections` (по умолчанию 320 на worker)   
В high‑concurrency часто повышают до **1000–2000**, чтобы не создавать/закрывать TCP к backend’ам на каждом чихе.   
- `upstream-keepalive-requests` по умолчанию 10000   
Но важно: слишком большое значение может ухудшать балансировку (документы прямо предупреждают про риск load imbalance при “слишком долгих” keepalive к upstream).   

Пример ConfigMap (идея, не “магические числа”):
```yaml
controller:
  config:
    keep-alive-requests: "10000"
    upstream-keepalive-connections: "1000"
    upstream-keepalive-requests: "10000"
```

### 4.2 max-worker-connections / open files
- `max-worker-connections` по умолчанию 16384 на worker.   
- Документация ingress-nginx говорит: **значение `0` в high load улучшает perf**, но **увеличивает потребление RAM даже в idle** (и `0` будет использовать `max-worker-open-files`).   

То есть это не “обязательная оптимизация”, а осознанный размен “RAM ради производительности/запаса по соединениям”.

### 4.3 reuse-port (у вас уже должно быть ок)
`reuse-port` по умолчанию **true** и включает SO_REUSEPORT (отдельный listen socket на worker, kernel сам раскидывает коннекты) — это обычно хорошо для high accept rate.   

### 4.4 Логи
На больших RPS access log может:
- грузить CPU,
- грузить I/O (пусть даже stdout),
- раздувать стоимость лог‑пайплайна.

В ingress-nginx можно:
- полностью отключить `disable-access-log`,   
- или включить буферизацию через `access-log-params` (например, `buffer=16k flush=1m`).   

### 4.5 Service: externalTrafficPolicy=Local (если применимо)
Если трафик приходит через Service типа NodePort/LoadBalancer, Kubernetes описывает, что `externalTrafficPolicy: Local`:
- сохраняет source IP,
- избегает “второго хопа на другую ноду”,
- но **если на ноде нет локальных endpoint’ов — пакеты дропаются**.   

На **выделенном ingress‑сервере** это часто именно то, что нужно (LB должен слать трафик только туда, где реально есть ingress‑pod).

---

## 5) Requests/Limits: что поставить на 8 vCPU / 16 GB (выделенная ingress‑нода)

### 5.1 Важный момент про CPU limits
- Kubernetes применяет requests/limits через cgroups.   
- CPU — “compressible”: при упоре в CPU limit контейнер **будет throttling’иться** (а не падать), что часто выражается в росте latency.   
- В Helm values ingress-nginx прямо написано: **“Ideally, there should be no limits.”** (и дефолтные requests там 100m/90Mi просто чтобы не было проблем с probes на занятых нодах).   

Отсюда типовая практика для ingress: **CPU request ставим**, а **CPU limit либо не ставим**, либо ставим очень высоким, чтобы не словить троттлинг на пиках.

### 5.2 Практические стартовые значения (без знания вашего RPS/трафика)
Так как нода выделенная, можно стартовать “смело, но с запасом под систему”.

**Вариант A (1 replica, самый простой):**
```yaml
resources:
  requests:
    cpu: "1500m"
    memory: "1Gi"
  limits:
    # cpu: не ставить (или поставить 6-8 CPU, если у вас политики требуют limits)
    memory: "4Gi"
```

**Вариант B (2 replicas на той же ноде — полезно для более мягких рестартов/роллинга):**
```yaml
controller:
  replicaCount: 2
  resources:
    requests:
      cpu: "1000m"
      memory: "1Gi"
    limits:
      # cpu: не ставить (или высокий)
      memory: "3Gi"
```
Но: **2 реплики на одной ноде не дают HA по ноде**, только чуть лучше переживаются reload/rolling update.

### 5.3 TerminationGracePeriodSeconds (чтобы не рубить соединения)
В values.yaml ingress-nginx есть явная подсказка: **дать до 300s**, чтобы успеть “слить” соединения.   
На highload это реально важно (особенно если keepalive/WebSocket/long polling).

---

## 6) Мини-чеклист “HighLoad ingress нода”
1) Поднимите **fd/ulimit**, backlog, port range.   
2) Подкрутите keepalive:
   - `keep-alive-requests: 10000`
   - `upstream-keepalive-connections: 1000` (аккуратно)   
3) Подумайте про access log (выкл/буфер).   
4) **requests выставить**, CPU limits — по возможности не ставить/ставить высоко.   
5) Помнить про “retirement” ingress-nginx в **марте 2026** (через считанные недели) и планировать замену.   

Если вы сделаете пункты 1–4, в большинстве реальных highload‑кейсов это даёт заметно больший эффект, чем “поднять версию контроллера” (тем более когда k8s 1.24 фиксирован).
