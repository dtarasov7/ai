Предоставляю развернутый план по аудиту инсталляции Kubernetes v1.24, включая Ansible playbook, рекомендации по совместимым версиям и настройке Nexus proxy-репозиториев.

## План аудита и резервного копирования

### Этап 1: Инвентаризация кластера

**Цель**: Собрать информацию о текущем состоянии кластера, развернутых компонентах и их версиях. [kubernetes](https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/)

1. Инвентаризация версий компонентов (kubelet, kubeadm, containerd, CNI)
2. Сбор списка всех запущенных pods во всех namespace
3. Извлечение манифестов всех Kubernetes объектов (Deployments, StatefulSets, DaemonSets, Services, ConfigMaps, Secrets)
4. Идентификация Helm releases через `helm list -A` [helm](https://helm.sh/docs/helm/helm_get_manifest/)
5. Извлечение манифестов Helm releases через `helm get manifest` [helm](https://helm.sh/docs/helm/helm_get_manifest/)
6. Сбор информации о container images (используемые образы и их digest)
7. Инспекция измененных контейнеров через containerd

### Этап 2: Резервное копирование etcd

**Цель**: Создать snapshot базы данных etcd для возможности восстановления. [kubernetes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/)

1. Создание snapshot через `etcdctl snapshot save`
2. Резервное копирование сертификатов etcd из `/etc/kubernetes/pki/etcd/`
3. Верификация snapshot через `etcdutl snapshot status`
4. Сохранение snapshot в безопасном месте с датой и временем

### Этап 3: Извлечение и документирование

**Цель**: Сохранить все конфигурации для возможного восстановления или миграции.

1. Экспорт всех ресурсов через `kubectl get all -A -o yaml`
2. Экспорт CRDs (Custom Resource Definitions)
3. Экспорт RBAC политик (Roles, ClusterRoles, RoleBindings)
4. Документирование кастомизаций контейнеров
5. Сохранение конфигураций containerd и Cilium

## Ansible Playbook для аудита

```yaml
---
- name: Kubernetes Cluster Audit and Backup
  hosts: k8s_masters
  become: yes
  gather_facts: yes
  vars:
    backup_dir: "/tmp/k8s_audit_{{ ansible_date_time.iso8601_basic_short }}"
    local_backup_dir: "./k8s_audit_results"
    
  tasks:
    - name: Create backup directory on remote host
      file:
        path: "{{ backup_dir }}"
        state: directory
        mode: '0755'

    - name: Collect component versions
      shell: |
        echo "=== KUBELET VERSION ===" > {{ backup_dir }}/versions_{{ ansible_hostname }}.txt
        kubelet --version >> {{ backup_dir }}/versions_{{ ansible_hostname }}.txt 2>&1
        echo "=== KUBEADM VERSION ===" >> {{ backup_dir }}/versions_{{ ansible_hostname }}.txt
        kubeadm version >> {{ backup_dir }}/versions_{{ ansible_hostname }}.txt 2>&1
        echo "=== KUBECTL VERSION ===" >> {{ backup_dir }}/versions_{{ ansible_hostname }}.txt
        kubectl version --client >> {{ backup_dir }}/versions_{{ ansible_hostname }}.txt 2>&1
        echo "=== CONTAINERD VERSION ===" >> {{ backup_dir }}/versions_{{ ansible_hostname }}.txt
        containerd --version >> {{ backup_dir }}/versions_{{ ansible_hostname }}.txt 2>&1
        echo "=== ETCD VERSION ===" >> {{ backup_dir }}/versions_{{ ansible_hostname }}.txt
        kubectl exec -n kube-system etcd-{{ ansible_hostname }} -- etcd --version >> {{ backup_dir }}/versions_{{ ansible_hostname }}.txt 2>&1 || echo "Failed to get etcd version"
      args:
        executable: /bin/bash
      ignore_errors: yes

    - name: Export all Kubernetes resources
      shell: |
        kubectl get all -A -o yaml > {{ backup_dir }}/all_resources_{{ ansible_hostname }}.yaml
        kubectl get configmap -A -o yaml > {{ backup_dir }}/configmaps_{{ ansible_hostname }}.yaml
        kubectl get secrets -A -o yaml > {{ backup_dir }}/secrets_{{ ansible_hostname }}.yaml
        kubectl get pv,pvc -A -o yaml > {{ backup_dir }}/persistent_volumes_{{ ansible_hostname }}.yaml
        kubectl get ingress -A -o yaml > {{ backup_dir }}/ingress_{{ ansible_hostname }}.yaml
        kubectl get networkpolicies -A -o yaml > {{ backup_dir }}/networkpolicies_{{ ansible_hostname }}.yaml
      args:
        executable: /bin/bash
      run_once: true
      ignore_errors: yes

    - name: Export CRDs and RBAC
      shell: |
        kubectl get crd -o yaml > {{ backup_dir }}/crds_{{ ansible_hostname }}.yaml
        kubectl get clusterroles -o yaml > {{ backup_dir }}/clusterroles_{{ ansible_hostname }}.yaml
        kubectl get clusterrolebindings -o yaml > {{ backup_dir }}/clusterrolebindings_{{ ansible_hostname }}.yaml
        kubectl get roles -A -o yaml > {{ backup_dir }}/roles_{{ ansible_hostname }}.yaml
        kubectl get rolebindings -A -o yaml > {{ backup_dir }}/rolebindings_{{ ansible_hostname }}.yaml
      args:
        executable: /bin/bash
      run_once: true
      ignore_errors: yes

    - name: List Helm releases
      shell: |
        helm list -A -o yaml > {{ backup_dir }}/helm_releases_{{ ansible_hostname }}.yaml
        helm list -A | tail -n +2 | awk '{print $1","$2}' > {{ backup_dir }}/helm_list_{{ ansible_hostname }}.txt
      args:
        executable: /bin/bash
      run_once: true
      ignore_errors: yes

    - name: Extract Helm manifests
      shell: |
        mkdir -p {{ backup_dir }}/helm_manifests
        while IFS=',' read -r release namespace; do
          helm get manifest "$release" -n "$namespace" > {{ backup_dir }}/helm_manifests/${release}_${namespace}_{{ ansible_hostname }}.yaml 2>&1
          helm get values "$release" -n "$namespace" -o yaml > {{ backup_dir }}/helm_manifests/${release}_${namespace}_values_{{ ansible_hostname }}.yaml 2>&1
        done < {{ backup_dir }}/helm_list_{{ ansible_hostname }}.txt
      args:
        executable: /bin/bash
      run_once: true
      ignore_errors: yes

    - name: Collect container images information
      shell: |
        crictl images --output json > {{ backup_dir }}/images_{{ ansible_hostname }}.json
        crictl images | grep -v "IMAGE ID" > {{ backup_dir }}/images_list_{{ ansible_hostname }}.txt
      args:
        executable: /bin/bash
      ignore_errors: yes

    - name: Backup etcd snapshot
      shell: |
        ETCDCTL_API=3 etcdctl \
          --endpoints=https://127.0.0.1:2379 \
          --cacert=/etc/kubernetes/pki/etcd/ca.crt \
          --cert=/etc/kubernetes/pki/etcd/server.crt \
          --key=/etc/kubernetes/pki/etcd/server.key \
          snapshot save {{ backup_dir }}/etcd_snapshot_{{ ansible_hostname }}.db
        
        ETCDCTL_API=3 etcdctl \
          --endpoints=https://127.0.0.1:2379 \
          --cacert=/etc/kubernetes/pki/etcd/ca.crt \
          --cert=/etc/kubernetes/pki/etcd/server.crt \
          --key=/etc/kubernetes/pki/etcd/server.key \
          snapshot status {{ backup_dir }}/etcd_snapshot_{{ ansible_hostname }}.db -w table > {{ backup_dir }}/etcd_snapshot_status_{{ ansible_hostname }}.txt
      args:
        executable: /bin/bash
      ignore_errors: yes

    - name: Backup Kubernetes PKI certificates
      shell: |
        tar -czf {{ backup_dir }}/k8s_pki_{{ ansible_hostname }}.tar.gz /etc/kubernetes/pki/
        tar -czf {{ backup_dir }}/etcd_pki_{{ ansible_hostname }}.tar.gz /etc/kubernetes/pki/etcd/
      args:
        executable: /bin/bash
      ignore_errors: yes

    - name: Backup Kubernetes manifests
      shell: |
        tar -czf {{ backup_dir }}/k8s_manifests_{{ ansible_hostname }}.tar.gz /etc/kubernetes/manifests/
      args:
        executable: /bin/bash
      ignore_errors: yes

    - name: Collect containerd configuration
      shell: |
        cp /etc/containerd/config.toml {{ backup_dir }}/containerd_config_{{ ansible_hostname }}.toml || echo "No containerd config found"
        containerd config dump > {{ backup_dir }}/containerd_config_dump_{{ ansible_hostname }}.toml
      args:
        executable: /bin/bash
      ignore_errors: yes

    - name: Collect Cilium configuration
      shell: |
        kubectl get configmap -n kube-system cilium-config -o yaml > {{ backup_dir }}/cilium_config_{{ ansible_hostname }}.yaml 2>&1 || echo "No Cilium config found"
        kubectl get pods -n kube-system -l k8s-app=cilium -o yaml > {{ backup_dir }}/cilium_pods_{{ ansible_hostname }}.yaml 2>&1
      args:
        executable: /bin/bash
      run_once: true
      ignore_errors: yes

    - name: Collect node information
      shell: |
        kubectl get nodes -o yaml > {{ backup_dir }}/nodes_{{ ansible_hostname }}.yaml
        kubectl describe nodes > {{ backup_dir }}/nodes_describe_{{ ansible_hostname }}.txt
      args:
        executable: /bin/bash
      run_once: true
      ignore_errors: yes

    - name: Create audit summary
      shell: |
        cat > {{ backup_dir }}/audit_summary_{{ ansible_hostname }}.txt << EOF
        Kubernetes Cluster Audit Summary
        ================================
        Date: $(date)
        Hostname: {{ ansible_hostname }}
        
        Component Versions:
        $(cat {{ backup_dir }}/versions_{{ ansible_hostname }}.txt)
        
        Total Pods: $(kubectl get pods -A --no-headers | wc -l)
        Total Services: $(kubectl get svc -A --no-headers | wc -l)
        Total Deployments: $(kubectl get deploy -A --no-headers | wc -l)
        Total StatefulSets: $(kubectl get sts -A --no-headers | wc -l)
        Total DaemonSets: $(kubectl get ds -A --no-headers | wc -l)
        
        Helm Releases: $(helm list -A --no-headers | wc -l)
        
        Container Images Count: $(crictl images --quiet | wc -l)
        EOF
      args:
        executable: /bin/bash
      ignore_errors: yes

    - name: Create local backup directory
      local_action:
        module: file
        path: "{{ local_backup_dir }}"
        state: directory
        mode: '0755'
      run_once: true

    - name: Fetch backup files to ansible controller
      synchronize:
        mode: pull
        src: "{{ backup_dir }}/"
        dest: "{{ local_backup_dir }}/{{ ansible_hostname }}/"
        recursive: yes
      
    - name: Cleanup remote backup directory
      file:
        path: "{{ backup_dir }}"
        state: absent
```

## Совместимые версии компонентов для Kubernetes v1.24

### Основные компоненты

| Компонент | Рекомендуемая версия | Диапазон совместимости |
|-----------|---------------------|------------------------|
| kubelet | v1.24.17 | v1.24.x (последний patch)  [kubernetes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/) |
| kubeadm | v1.24.17 | v1.24.x (соответствует kubelet)  [kubernetes](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/kubelet-integration/) |
| containerd | v1.6.x - v1.7.x | v1.6.8+, v1.7.0+  [kubernetes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/) |
| etcd | v3.5.x | v3.5.3+  [kubernetes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/) |
| nginx-ingress | v1.9.1 (текущая) | v1.7.x - v1.9.x  [kubernetes](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/kubelet-integration/) |
| Cilium | v1.12.x - v1.13.x | v1.11+ |
| CoreDNS | v1.8.6 | v1.8.x - v1.9.x |
| Helm | v3.9.x - v3.14.x | v3.8+ |

### Важные замечания

- Kubernetes v1.24 удалил поддержку dockershim, поэтому containerd является правильным выбором [kubernetes](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/kubelet-integration/)
- Используйте последний patch версии v1.24 (v1.24.17) для безопасности
- nginx-ingress controller v1.9.1 совместим с k8s 1.24-1.28 [stackoverflow](https://stackoverflow.com/questions/77430448/nginx-ingress-version-for-a-specific-kubernetes-version)
- etcd должен быть минимум v3.5.3+ для production использования [kubernetes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/)

## Рекомендации по тюнингу для High Load

### Настройки etcd

```yaml
# /etc/kubernetes/manifests/etcd.yaml
spec:
  containers:
  - command:
    - etcd
    - --quota-backend-bytes=8589934592  # 8GB
    - --heartbeat-interval=100
    - --election-timeout=1000
    - --snapshot-count=10000
    - --max-snapshots=5
    - --max-wals=5
    - --auto-compaction-retention=1
```

### Настройки kube-apiserver

```yaml
# /etc/kubernetes/manifests/kube-apiserver.yaml
spec:
  containers:
  - command:
    - kube-apiserver
    - --max-requests-inflight=400       # default: 400
    - --max-mutating-requests-inflight=200  # default: 200
    - --event-ttl=1h                     # default: 1h
    - --watch-cache-sizes=persistentvolumeclaims#1000,pods#5000
    - --default-watch-cache-size=100
```

### Настройки kubelet

```yaml
# /var/lib/kubelet/config.yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
maxPods: 110
podsPerCore: 10
enableControllerAttachDetach: true
serializeImagePulls: false
registryPullQPS: 10
registryBurst: 20
eventRecordQPS: 50
evictionHard:
  memory.available: "500Mi"
  nodefs.available: "10%"
  nodefs.inodesFree: "5%"
systemReserved:
  cpu: "1000m"
  memory: "2Gi"
kubeReserved:
  cpu: "1000m"
  memory: "2Gi"
```

### Настройки containerd для High Load

```toml
# /etc/containerd/config.toml
version = 2

[plugins."io.containerd.grpc.v1.cri"]
  max_concurrent_downloads = 10
  max_container_log_line_size = 16384

[plugins."io.containerd.grpc.v1.cri".containerd]
  snapshotter = "overlayfs"
  
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
  runtime_type = "io.containerd.runc.v2"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
  SystemdCgroup = true

[plugins."io.containerd.grpc.v1.cri".registry]
  config_path = "/etc/containerd/certs.d"
```

### Sysctl оптимизации для worker nodes

```bash
# /etc/sysctl.d/99-kubernetes.conf
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 10
net.core.somaxconn = 32768
net.ipv4.tcp_max_syn_backlog = 8192
net.core.netdev_max_backlog = 5000
net.ipv4.neigh.default.gc_thresh1 = 4096
net.ipv4.neigh.default.gc_thresh2 = 8192
net.ipv4.neigh.default.gc_thresh3 = 16384
fs.inotify.max_user_watches = 524288
fs.inotify.max_user_instances = 512
vm.max_map_count = 262144
```

### Cilium оптимизации

```yaml
# values.yaml для Cilium
bpf:
  masquerade: true
  tproxy: true
  
k8s:
  requireIPv4PodCIDR: true
  
kubeProxyReplacement: strict

tunnel: disabled  # используйте native routing для лучшей производительности

ipam:
  mode: kubernetes
  
operator:
  replicas: 2
  resources:
    limits:
      cpu: 1000m
      memory: 1Gi
    requests:
      cpu: 100m
      memory: 128Mi

resources:
  limits:
    cpu: 2000m
    memory: 2Gi
  requests:
    cpu: 500m
    memory: 512Mi
```

## Настройка Nexus Repository как прокси

### Создание Docker proxy repository

```bash
# Через REST API
curl -u admin:admin123 -X POST "http://nexus-server:8081/service/rest/v1/repositories/docker/proxy" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "docker-proxy",
    "online": true,
    "storage": {
      "blobStoreName": "default",
      "strictContentTypeValidation": true
    },
    "proxy": {
      "remoteUrl": "https://registry-1.docker.io",
      "contentMaxAge": 1440,
      "metadataMaxAge": 1440
    },
    "negativeCache": {
      "enabled": true,
      "timeToLive": 1440
    },
    "httpClient": {
      "blocked": false,
      "autoBlock": true,
      "connection": {
        "retries": 3,
        "timeout": 60
      }
    },
    "docker": {
      "v1Enabled": false,
      "forceBasicAuth": true,
      "httpPort": 8082,
      "httpsPort": null
    },
    "dockerProxy": {
      "indexType": "HUB"
    }
  }'
```

### Создание Helm proxy repository

```bash
curl -u admin:admin123 -X POST "http://nexus-server:8081/service/rest/v1/repositories/helm/proxy" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "helm-proxy",
    "online": true,
    "storage": {
      "blobStoreName": "default",
      "strictContentTypeValidation": true
    },
    "proxy": {
      "remoteUrl": "https://kubernetes-charts.storage.googleapis.com",
      "contentMaxAge": 1440,
      "metadataMaxAge": 1440
    },
    "negativeCache": {
      "enabled": true,
      "timeToLive": 1440
    },
    "httpClient": {
      "blocked": false,
      "autoBlock": true
    }
  }'
```

### Создание PyPI proxy repository

```bash
curl -u admin:admin123 -X POST "http://nexus-server:8081/service/rest/v1/repositories/pypi/proxy" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "pypi-proxy",
    "online": true,
    "storage": {
      "blobStoreName": "default",
      "strictContentTypeValidation": true
    },
    "proxy": {
      "remoteUrl": "https://pypi.org",
      "contentMaxAge": 1440,
      "metadataMaxAge": 1440
    },
    "negativeCache": {
      "enabled": true,
      "timeToLive": 1440
    },
    "httpClient": {
      "blocked": false,
      "autoBlock": true
    }
  }'
```

### Создание raw proxy для бинарных файлов

```bash
curl -u admin:admin123 -X POST "http://nexus-server:8081/service/rest/v1/repositories/raw/proxy" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "k8s-binaries-proxy",
    "online": true,
    "storage": {
      "blobStoreName": "default",
      "strictContentTypeValidation": false
    },
    "proxy": {
      "remoteUrl": "https://dl.k8s.io",
      "contentMaxAge": 1440,
      "metadataMaxAge": 1440
    },
    "httpClient": {
      "blocked": false,
      "autoBlock": true
    }
  }'
```

## Использование Nexus proxy-репозиториев

### Настройка containerd для использования Nexus Docker registry

```toml
# /etc/containerd/certs.d/_default/hosts.toml
server = "https://registry-1.docker.io"

[host."http://nexus-server:8082"]
  capabilities = ["pull", "resolve"]
  skip_verify = false
```

Или создать конфигурацию для конкретных репозиториев: [rtfm.co](https://rtfm.co.ua/en/nexus-configuring-docker-proxy-repository-and-containerd-in-kubernetes/)

```toml
# /etc/containerd/certs.d/docker.io/hosts.toml
server = "https://docker.io"

[host."http://nexus-server:8082"]
  capabilities = ["pull", "resolve"]
  skip_verify = false
  override_path = true
```

### Настройка Helm для использования Nexus

```bash
# Добавить Nexus как Helm репозиторий
helm repo add nexus-stable http://nexus-server:8081/repository/helm-proxy/
helm repo update

# Использовать при установке
helm install my-release nexus-stable/chart-name
```

### Настройка pip для использования Nexus PyPI proxy

```bash
# ~/.config/pip/pip.conf
[global]
index-url = http://nexus-server:8081/repository/pypi-proxy/simple
trusted-host = nexus-server
```

Или через переменные окружения:

```bash
export PIP_INDEX_URL=http://nexus-server:8081/repository/pypi-proxy/simple
export PIP_TRUSTED_HOST=nexus-server
```

### Настройка apt/yum для использования Nexus

```bash
# Для apt (создать /etc/apt/apt.conf.d/99nexus-proxy)
Acquire::http::Proxy "http://nexus-server:8081";
Acquire::https::Proxy "http://nexus-server:8081";

# Для yum/dnf (добавить в /etc/yum.conf)
proxy=http://nexus-server:8081
```

### Автоматизация настройки через Ansible

```yaml
- name: Configure containerd to use Nexus proxy
  hosts: k8s_all_nodes
  become: yes
  tasks:
    - name: Create containerd certs.d directory
      file:
        path: /etc/containerd/certs.d/docker.io
        state: directory
        mode: '0755'

    - name: Configure containerd registry mirror
      copy:
        dest: /etc/containerd/certs.d/docker.io/hosts.toml
        content: |
          server = "https://docker.io"
          
          [host."http://{{ nexus_server }}:8082"]
            capabilities = ["pull", "resolve"]
            skip_verify = false
            override_path = true
        mode: '0644'
      
    - name: Restart containerd
      systemd:
        name: containerd
        state: restarted
        enabled: yes
```

Этот план предоставляет полную стратегию аудита, резервного копирования и оптимизации вашего Kubernetes v1.24 кластера в изолированной среде с использованием Nexus в качестве прокси. [kubernetes](https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/)
