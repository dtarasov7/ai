На основе собранной информации, вот полный ответ:

## 1. Совместимость версий

v1.9.0 ingress-nginx официально поддерживает Kubernetes 1.28, 1.27, 1.26, 1.25 — **K8s 1.24 НЕ в списке поддерживаемых**.

v1.8.4 поддерживает K8s 1.27, 1.26, 1.25, 1.24 — это **максимальная версия** для K8s 1.24.

**Рекомендация:** Понизьте до **v1.8.4** (или v1.8.5 если есть). Версия 1.9.1 может работать, но не протестирована для 1.24 и могут быть неожиданные проблемы.

---

## 2. Настройки хоста (sysctl)

Рекомендуемые изменения: Backlog Queue setting `net.core.somaxconn` from 128 to 32768, Ephemeral Ports setting `net.ipv4.ip_local_port_range` from 32768 60999 to 1024 65000

Пример конфигурации для high concurrency включает initContainer с настройками sysctl: `net.core.somaxconn=65535`, `net.ipv4.ip_local_port_range="1024 65535"`, `net.ipv4.tcp_tw_reuse=1`

**На хосте или через initContainer:**

```yaml
initContainers:
- name: sysctl-tuning
  image: busybox
  securityContext:
    privileged: true
  command:
  - sh
  - -c
  - |
    sysctl -w net.core.somaxconn=65535
    sysctl -w net.ipv4.ip_local_port_range="1024 65535"
    sysctl -w net.ipv4.tcp_tw_reuse=1
    sysctl -w net.core.netdev_max_backlog=16384
    sysctl -w net.ipv4.tcp_max_syn_backlog=8192
    sysctl -w net.ipv4.tcp_fin_timeout=15
    sysctl -w fs.file-max=1048576
```

---

## 3. ConfigMap для nginx-ingress-controller (HighLoad)

Пример ConfigMap для high concurrency: `worker-processes: "auto"`, `keep-alive-requests: "10000"`, `upstream-keepalive-connections: "2000"`, `max-worker-connections: "65536"`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ingress-nginx-controller
  namespace: ingress-nginx
data:
  # Worker настройки
  worker-processes: "auto"           # Соответствует 8 vCPU
  max-worker-connections: "65536"
  
  # Keep-alive
  keep-alive: "75"
  keep-alive-requests: "10000"
  upstream-keepalive-connections: "1000"
  upstream-keepalive-timeout: "60"
  upstream-keepalive-requests: "10000"
  
  # Buffers
  proxy-buffer-size: "16k"
  proxy-buffers-number: "8"
  
  # Timeouts
  proxy-connect-timeout: "10"
  proxy-read-timeout: "60"
  proxy-send-timeout: "60"
  
  # Performance
  use-gzip: "true"
  gzip-level: "3"
  
  # Logging (для HighLoad можно отключить)
  disable-access-log: "false"         # или "true" для max perf
  
  # SSL optimization
  ssl-session-cache-size: "50m"
  ssl-session-timeout: "1h"
  ssl-protocols: "TLSv1.2 TLSv1.3"
  
  # Server hash
  server-name-hash-bucket-size: "256"
  server-name-hash-max-size: "1024"
```

---

## 4. Resources: request/limit для 8 vCPU / 16GB RAM

Рекомендуется не устанавливать resource limits для Nginx Ingress Controller, чтобы предотвратить прерывания трафика из-за OOM ошибок. Если необходимо установить limits, рекомендуется CPU limit минимум 1000 millicores и memory limit минимум 2 GiB.

Для **выделенного ingress-сервера** с 8 vCPU / 16GB RAM:

```yaml
resources:
  requests:
    cpu: "6"           # Оставляем запас для системы
    memory: "12Gi"
  limits:
    cpu: "7"           # Чуть меньше чем доступно
    memory: "14Gi"     # Запас для OOM protection
```

**Или более агрессивный вариант (Guaranteed QoS):**

```yaml
resources:
  requests:
    cpu: "7"
    memory: "14Gi"
  limits:
    cpu: "7"
    memory: "14Gi"
```

Частые reloads могут привести к высокому потреблению памяти и потенциальным OOM ошибкам. Это наиболее вероятно при проксировании трафика с long-lived connections (WebSocket, gRPC) и частых reloads. Старые NGINX workers не завершатся пока все соединения не будут закрыты, если не настроен `worker_shutdown_timeout`.

**Важно добавить в ConfigMap:**
```yaml
worker-shutdown-timeout: "240s"  # Ограничить время жизни старых workers
```

---

## 5. Итоговый чеклист

| Параметр | Рекомендация |
|----------|--------------|
| **Версия ingress-nginx** | Понизить до **v1.8.4** |
| **worker-processes** | `auto` (= 8) ✅ у вас уже так |
| **somaxconn** | 32768-65535 |
| **ip_local_port_range** | 1024 65535 |
| **max-worker-connections** | 65536 |
| **upstream-keepalive** | 500-2000 (зависит от backends) |
| **CPU request/limit** | 6-7 cores |
| **Memory request/limit** | 12-14 Gi |
| **QoS class** | Guaranteed (requests = limits) |
| **worker-shutdown-timeout** | 120-300s |
