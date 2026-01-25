Да, nginx-ingress-controller (ingress-nginx) версии 1.9.1 **можно использовать на Kubernetes 1.24**, хотя официально она поддерживает K8s 1.25–1.28. Последняя **официально совместимая версия с 1.24** — v1.8.4 (поддержка 1.24–1.27). Обновление до неё (или даже до 1.9.1, если уже работает) **рекомендуется** для фиксов безопасности, багов и производительности, но не критично, если кластер стабилен. Путь обновления простой: обновите тег образа (image) в Deployment `ingress-nginx-controller` (например, `registry.k8s.io/ingress-nginx/controller:v1.8.4`), rollout'те и проверьте Ingress'ы.

### Настройки для HighLoad на dedicated ingress-ноде (8 vCPU, 16 GB RAM)
У вас 8 worker-процессов nginx — это оптимально (по 1 на core, auto-tune работает хорошо). Фокус на kernel tunings (sysctl), ConfigMap nginx и resources Pod'а. Тестируйте под нагрузкой (wrk/ab/locust) с мониторингом (Prometheus + Grafana).

#### 1. **Настройки хоста (node-level sysctl)**
Примените **непосредственно на ноде** (sysctl -w или /etc/sysctl.conf + sysctl -p), т.к. dedicated. Или via InitContainer в Deployment (kubectl patch, пример ниже).

Рекомендуемые значения для high concurrency/throughput:
```
net.core.somaxconn = 32768
net.ipv4.ip_local_port_range = 1024 65000
net.core.netdev_max_backlog = 30000
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_max_syn_backlog = 32768
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15
vm.overcommit_memory = 1
vm.swappiness = 10
fs.file-max = 1000000
fs.nr_open = 1048576
```

**Применение via InitContainer** (patch Deployment ingress-nginx-controller):
```bash
kubectl patch deployment ingress-nginx-controller -n ingress-nginx --patch '{
  "spec": {
    "template": {
      "spec": {
        "initContainers": [{
          "name": "sysctl-tuner",
          "image": "busybox:1.36",
          "command": ["sh", "-c", "sysctl -w net.core.somaxconn=32768 && ..."],
          "securityContext": { "privileged": true }
        }]
      }
    }
  }
}'
```
Полный пример: https://kubernetes.github.io/ingress-nginx/examples/customization/sysctl/.

#### 2. **ConfigMap для nginx-ingress-controller** (nginx.conf tunings)
Обновите ConfigMap `ingress-nginx-controller` в namespace `ingress-nginx`. Ключевые для HighLoad (concurrency, buffering, keepalives).

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ingress-nginx-controller
  namespace: ingress-nginx
data:
  # Workers (уже 8 — хорошо)
  worker-processes: "8"  # или "auto"
  worker-cpu-affinity: "auto"  # bind to cores

  # Connections/files (увеличить concurrency)
  max-worker-connections: "32768"
  max-worker-open-files: "65535"

  # Buffers (для throughput)
  proxy-buffer-size: "8k"
  proxy-buffers-number: "8"  # или 16
  proxy-busy-buffers-size: "128k"
  large-client-header-buffers: "8 16k"
  client-header-buffer-size: "4k"
  client-body-buffer-size: "64k"

  # Timeouts/keepalives (reuse connections)
  keep-alive: "300s"
  keep-alive-requests: "10000"
  upstream-keepalive-connections: "1024"
  upstream-keepalive-timeout: "30s"
  proxy-connect-timeout: "10s"
  proxy-read-timeout: "300s"
  proxy-send-timeout: "300s"
  worker-shutdown-timeout: "60s"

  # Другие perf
  enable-multi-accept: "true"
  reuse-port: "true"
  enable-brotli: "true"  # compression
  brotli-level: "6"
  use-http2: "true"
```
Примените: `kubectl apply -f configmap.yaml`, rollout Deployment. Мониторьте RSS/CPU workers.

#### 3. **Requests/Limits для Pod'а (Deployment ingress-nginx-controller)**
По умолчанию limits нет (может OOM), requests низкие (~500m CPU). Для dedicated ноды 8vCPU/16GB (single replica, nodeSelector/affinity на ноду):

```yaml
spec:
  template:
    spec:
      containers:
      - name: controller
        resources:
          requests:
            cpu: 250m     # базовый overhead
            memory: 256Mi
          limits:
            cpu: 7        # 7/8 cores (оставить 1 на kubelet/OS)
            memory: 14Gi  # 14/16 GB (оставить буфер)
```
Это даёт ~100k+ RPS под нагрузкой (зависит от трафика). Масштабируйте replicas=2–3 при >1M RPS. Рекомендация из практик: CPU limit ≥1 core, mem ≥2Gi на replica.

**Дополнительно для HA/HighLoad:**
- HPA по CPU 70–80%.
- NodePort или HostNetwork mode для baremetal/low latency.
- Rate limiting в Ingress annotations если DDoS.
- Мониторинг: nginx-vts-exporter + Prometheus.

Тестируйте поэтапно, rollback если issues. Если коммерческий NGINX Inc — docs отличаются.
