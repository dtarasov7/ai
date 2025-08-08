# Установка DKP CSE в закрытом окружении

## Требования

1. Репозиторий образов контейнеров (далее Репозиторий) на базе одного из [поддерживаемых решений](https://deckhouse.ru/products/kubernetes-platform/documentation/v1/supported_versions.html#container-registry).
2. Не менее 20 Гбайт свободного дискового пространства в Репозитории.
3. Сетевой доступ к портам Репозитория должен предоставляться без ограничений для всех целевых узлов.
4. Доменное имя (в случае использования) Репозитория должно разрешаться для всех целевых узлов.
5. Рабочая станция или сервер (далее Станция) на базе ОС Linux, MacOS или Windows для проведения работ по установке DKP.
6. Не менее 20 Гбайт свободного дискового пространства на Станции.
7. Установленный на Станции пакет `docker` для запуска инсталлятора DKP.
8. SSH-доступ по ключу до узлов, которые будут узлами будущего кластера.
9. [Достаточное количество узлов](https://deckhouse.ru/products/kubernetes-platform/guides/hardware-requirements.html#выбор-ресурсов-для-узлов) для развертывания DKP с установленными на них [поддерживаемыми ОС](https://deckhouse.ru/products/kubernetes-platform/documentation/v1/supported_versions.html) в закрытом окружении.
10. Сетевой доступ от Станции по порту 22322/TCP.
11. На будущих узлах DKP не должно быть установлено пакетов container runtime, например containerd или Docker.
12. На будущих узлах DKP должен быть доступ к репозиториям с пакетами Linux используемой операционной системы, а также установлены менеджеры пакетов `apt` / `apt-get`, `yum` или `rpm` в зависимости от выбранной ОС.
13. На будущих узлах DKP необходимо наличие установленного `python`.

Под целевыми узлами понимаются:

- Узлы платформы DKP;
- Рабочие станции или серверы, с которых осуществляется управление Репозиторием, включая загрузку образов.

## Подготовка

1. Создайте зашифрованную base64 строку для доступа клиента Docker в Репозиторий, заменив `registry.example.com:5000` на адрес и порт вашего Репозитория. Пример:

```bash
base64 -w0 <<EOF
  {
    "auths": {
      "registry.example.com:5000": {
        "auth": "$(echo -n 'ВАШЕ_ИМЯ_ПОЛЬЗОВАТЕЛЯ:ВАШ_ПАРОЛЬ' | base64 -w0)"
      }
    }
  }
EOF
```

Данная строка потребуется в качестве значения параметра `registryDockerCfg` при заполнении файла конфигурации в п.3.

2. Задайте шаблон для системных доменных имен в формате `%s.some.domain.example.com`. Данная строка потребуется в качестве значения параметра `publicDomainTemplate` при заполнении файла конфигурации в п.3.

Шаблон определяет доменные имена для Dex, Grafana, Kubeconfig, Documentation и прочих системных интерфейсов. Например: `%s.cse.example.com` -> `grafana.cse.example.com`

Важно: если планируется использование собственного SSL-сертификата, необходимо убедиться, что он закрывает все системные доменные имена, либо имеет wildcard.

3. В случае использования собственного SSL-сертификата, подготовьте секрет заранее и добавьте его в конфигурационный файл `config.yml` перед установкой. Либо выполните эту операцию после установки платформы до добавления новых узлов в кластер.

Скрипт для создания секрета:

```bash
#!/bin/bash
# https://kubernetes.github.io/ingress-nginx/user-guide/tls/

CERT_NAME='example-com-tls'
KEY_FILE='example.com.key'
CERT_FILE='example.com.crt'

kubectl create secret tls ${CERT_NAME} \
    --key ${KEY_FILE} \
    --cert ${CERT_FILE} \
    -n d8-system \
    -o yaml \
    --dry-run=client
```

Шаг можно пропустить, если планируете использовать самоподписанные сертификаты с помощью модуля `cert-manager`.

4. Подготовьте конфигурационный файл `config.yml` для установщика DKP на основе предложенного ниже примера. Параметры, требующие внимания, имеют комментарии.

```yaml
---
apiVersion: deckhouse.io/v1
kind: ClusterConfiguration
clusterType: Static
# Не меняйте без крайней необходимости
podSubnetCIDR: 10.111.0.0/16
# Не меняйте без крайней необходимости
serviceSubnetCIDR: 10.222.0.0/16
# Поддерживаемые версии: 1.27, 1.29
kubernetesVersion: "1.29"
# Не меняйте без крайней необходимости
clusterDomain: "cluster.local"
---
apiVersion: deckhouse.io/v1
kind: InitConfiguration
deckhouse:
  # Путь до расположения образов DKP в Репозитории
  imagesRepo: registry.example.com:5000/your/path/to/cse
  # Строка аутентификации из п.1 раздела "Подготовка"
  registryDockerCfg: eyJhd...19Cg==
  # В случае использования собственного SSL сертификата помеcтите СА сертификат в блок ниже, либо удалите параметр
  registryCA: |
    -----BEGIN CERTIFICATE-----
    ...
    -----END CERTIFICATE-----
  devBranch: v1.67.1
---
apiVersion: deckhouse.io/v1
kind: StaticClusterConfiguration
internalNetworkCIDRs:
# Укажите диапазоны IP-адресов для назначения адресов узлам DKP.
- 10.0.0.0/24
- 10.0.1.0/24
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: deckhouse
spec:
  enabled: true
  version: 1
  settings:
    bundle: Default
    logLevel: Info
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: global
spec:
  version: 2
  settings:
    # В данном примере используется встроенный в платформу модуль local-path-provisioner.
    # Если планируете использовать другой класс по умолчанию, переопределите его ниже.
    # ВАЖНО: если этот класс не задан, для хранения данных подов будет использоваться EmptyDir,
    #        что будет приводить к потере данных при каждом перезапуске пода.
    defaultClusterStorageClass: sc-localpath-default
    modules:
      https:
        # В случае использования собственного сертификата, задайте в параметре secretName 
        # корректное имя секрета, куда будет записан сертификат
        customCertificate:
          secretName: example-com-tls
        mode: CustomCertificate
      # Строка с шаблоном системных доменных имен из п.2 раздела "Подготовка".
      # Доменные имена должны закрываться TLS/SSL сертификатом из секрета example-com-tls
      publicDomainTemplate: '%s.cse.example.com'
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: cni-cilium
spec:
  enabled: true
  version: 1
  settings:
    # Поменяйте значение на Disabled, если требуется отключить VXLAN
    tunnelMode: VXLAN
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: cilium-hubble
spec:
  # Поменяйте значение на true, если нужно включить модуль
  enabled: false
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: admission-policy-engine
spec:
  enabled: true
  version: 1
  settings:
    denyVulnerableImages:
      enabled: true
---
# Может потребоваться задать NTP серверы в закрытом окружении
# https://deckhouse.ru/products/kubernetes-platform/documentation/v1.67/modules/chrony/configuration.html
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: chrony
spec:
  enabled: true
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: control-plane-manager
spec:
  enabled: true
  version: 1
  settings:
    apiserver:
      auditPolicyEnabled: true
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: gost-integrity-controller
spec:
  enabled: true
---
# Если данный модуль не нужен, его можно выключить
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: cert-manager
spec:
  enabled: true
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: loki
spec:
  enabled: true
  version: 1
  settings:
    retentionPeriodHours: 24
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: node-manager
spec:
  enabled: true
  version: 2
  settings:
    earlyOomEnabled: false
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: operator-trivy
spec:
  enabled: true
  version: 1
  settings:
    linkCVEtoBDU: true
    tolerations:
    - operator: Exists
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: prometheus
spec:
  enabled: true
  version: 2
  settings:
    auth:
      allowedUserGroups:
      - admins
      - security
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: runtime-audit-engine
spec:
  enabled: true
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: user-authn
spec:
  enabled: true
  version: 2
  settings:
    controlPlaneConfigurator:
      dexCAMode: FromIngressSecret
    publishAPI:
      enabled: true
      https:
        mode: Global
        global:
          # В случае использования собственного сертификата помеcтите СА сертификат в блок ниже, либо замените на:
          # kubeconfigGeneratorMasterCA: ''
          kubeconfigGeneratorMasterCA: |
            -----BEGIN CERTIFICATE-----
            ...
            -----END CERTIFICATE-----
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: user-authz
spec:
  enabled: true
  version: 1
  settings:
    enableMultiTenancy: true
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: operator-prometheus
spec:
  enabled: true
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: log-shipper
spec:
  enabled: true
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: local-path-provisioner
spec:
  enabled: true
---
# Может потребоваться задать NTP серверы в закрытом окружении
# https://deckhouse.ru/products/kubernetes-platform/documentation/v1.67/modules/kube-dns/configuration.html
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: kube-dns
spec:
  enabled: true
  version: 1
  settings:
    enableLogs: true
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: ingress-nginx
spec:
  enabled: true
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: monitoring-kubernetes
spec:
  enabled: true
---
# Замените этот секрет секретом со вашими сертификатами
# https://kubernetes.github.io/ingress-nginx/user-guide/tls/
#
# Пример:
#
# CERT_NAME='example-com-tls'
# KEY_FILE='example.com.key'
# CERT_FILE='example.com.crt'
#
# kubectl create secret tls ${CERT_NAME} \
#     --key ${KEY_FILE} \
#     --cert ${CERT_FILE} \
#     -n d8-system \
#     --dry-run=client \
#     -oyaml
#
apiVersion: v1
data:
  tls.crt: ...
  tls.key: ...
kind: Secret
type: kubernetes.io/tls
metadata:
  name: example-com-tls
  namespace: d8-system
---
apiVersion: v1
data:
  audit-policy.yaml: YXBpVmVyc2lvbjogYXVkaXQuazhzLmlvL3YxICMgVGhpcyBpcyByZXF1aXJlZC4Ka2luZDogUG9saWN5CiMgRG9uJ3QgZ2VuZXJhdGUgYXVkaXQgZXZlbnRzIGZvciBhbGwgcmVxdWVzdHMgaW4gUmVxdWVzdFJlY2VpdmVkIHN0YWdlLgpvbWl0U3RhZ2VzOgogIC0gIlJlcXVlc3RSZWNlaXZlZCIKcnVsZXM6CiAgIyBBIGNhdGNoLWFsbCBydWxlIHRvIGxvZyBhbGwgb3RoZXIgcmVxdWVzdHMgYXQgdGhlIE1ldGFkYXRhIGxldmVsLgogIC0gbGV2ZWw6IE1ldGFkYXRhCiAgICAjIExvbmctcnVubmluZyByZXF1ZXN0cyBsaWtlIHdhdGNoZXMgdGhhdCBmYWxsIHVuZGVyIHRoaXMgcnVsZSB3aWxsIG5vdAogICAgIyBnZW5lcmF0ZSBhbiBhdWRpdCBldmVudCBpbiBSZXF1ZXN0UmVjZWl2ZWQuCiAgICBvbWl0U3RhZ2VzOgogICAgICAtICJSZXF1ZXN0UmVjZWl2ZWQiCgo=
kind: Secret
metadata:
  name: audit-policy
  namespace: kube-system
type: Opaque
---
apiVersion: deckhouse.io/v1
kind: CustomPrometheusRules
metadata:
  name: falco-critical-alerts
spec:
  groups:
  - name: falco-critical-alerts
    rules:
    - alert: FalcoCriticalAlertsAreFiring
      for: 1m
      annotations:
        description: |
          There is a suspicious activity on a node {{ $labels.node }}.
          Check you events journal for more details.
        summary: Falco detects a critical security incident
      expr: |
        sum by (node) (rate(falco_events{priority="Error|Critical|Warning|Notice"}[5m]) > 0)
---
apiVersion: deckhouse.io/v1alpha1
kind: FalcoAuditRules
metadata:
  name: fstec-additional-rules
spec:
  rules:
  - macro:
      name: always_true
      condition: (evt.num>=0)
  - macro:
      name: kevt
      condition: (jevt.value[/stage] in (k8s_audit_stages))
  - macro:
      name: consider_activity_events
      condition: (always_true)
  - macro:
      name: kactivity
      condition: (kevt and consider_activity_events)
  - macro:
      name: response_successful
      condition: (ka.response.code startswith 2)
  - macro:
      name: kcreate
      condition: ka.verb=create
  - macro:
      name: kdelete
      condition: ka.verb=delete
  - macro:
      name: pod
      condition: ka.target.resource=pods and not ka.target.subresource exists
  - rule:
      name: K8s Pod created
      condition: (kevt and kcreate and pod and response_successful)
      desc: Detect any attempt to create a pod
      output: K8s Pod Created (user=%ka.user.name pod=%ka.target.name ns=%ka.target.namespace resource=%ka.target.resource resp=%ka.response.code decision=%ka.auth.decision reason=%ka.auth.reason)
      priority: Informational
      tags:
      - fstec
      - container_drift
      source: K8sAudit
  - rule:
      name: K8s Pod deleted
      condition: (kevt and kdelete and pod and response_successful)
      desc: Detect any attempt to delete a pod
      output: K8s Pod Deleted (user=%ka.user.name pod=%ka.target.name ns=%ka.target.namespace resource=%ka.target.resource resp=%ka.response.code decision=%ka.auth.decision reason=%ka.auth.reason)
      priority: Informational
      tags:
      - fstec
      - container_drift
      source: K8sAudit
---
apiVersion: deckhouse.io/v1
kind: NodeGroup
metadata:
  name: system
spec:
  nodeTemplate:
    labels:
      node-role.deckhouse.io/system: ""
    taints:
      - effect: NoExecute
        key: dedicated.deckhouse.io
        value: system
  nodeType: Static
  disruptions:
    approvalMode: Manual
  kubelet:
    containerLogMaxFiles: 4
    containerLogMaxSize: 50Mi
---
apiVersion: deckhouse.io/v1
kind: NodeGroup
metadata:
  name: frontend
spec:
  nodeTemplate:
    labels:
      node-role.deckhouse.io/frontend: ""
    taints:
      - effect: NoExecute
        key: dedicated.deckhouse.io
        value: frontend
  nodeType: Static
  disruptions:
    approvalMode: Manual
  kubelet:
    containerLogMaxFiles: 4
    containerLogMaxSize: 50Mi
---
apiVersion: deckhouse.io/v1
kind: NodeGroup
metadata:
  name: worker
spec:
  nodeType: Static
  disruptions:
    approvalMode: Manual
  kubelet:
    containerLogMaxFiles: 4
    containerLogMaxSize: 50Mi
---
apiVersion: deckhouse.io/v1alpha1
kind: NodeGroupConfiguration
metadata:
  name: sysctl-tune-fstec
spec:
  weight: 100
  bundles:
  - "*"
  nodeGroups:
  - "*"
  content: |
    sysctl -w kernel.dmesg_restrict=1
    sysctl -w kernel.kptr_restrict=2
    sysctl -w net.core.bpf_jit_harden=2
    sysctl -w kernel.perf_event_paranoid=3
    sysctl -w kernel.kexec_load_disabled=1
    sysctl -w user.max_user_namespaces=0
    sysctl -w kernel.unprivileged_bpf_disabled=1
    sysctl -w vm.unprivileged_userfaultfd=0
    sysctl -w dev.tty.ldisc_autoload=0
    sysctl -w vm.mmap_min_addr=4096
    sysctl -w kernel.randomize_va_space=2
    sysctl -w kernel.yama.ptrace_scope=3
    sysctl -w fs.protected_symlinks=1
    sysctl -w fs.protected_hardlinks=1
    sysctl -w fs.protected_fifos=2
    sysctl -w fs.protected_regular=2
    sysctl -w fs.suid_dumpable=0
---
#
# Класс для хранения данных по умолчанию
#
apiVersion: deckhouse.io/v1alpha1
kind: LocalPathProvisioner
metadata:
  name: sc-localpath-default
spec:
  path: "/opt/local-path-provisioner-default"
  reclaimPolicy: Delete
---
#
# Класс для хранения данных на системных узлах (опционально)
#
apiVersion: deckhouse.io/v1alpha1
kind: LocalPathProvisioner
metadata:
  name: localpath-system
spec:
  nodeGroups:
  - system
  path: "/opt/local-path-provisioner-system"
  reclaimPolicy: Delete
---
#
# Класс для хранения данных по monitoring узлах (опционально)
#
apiVersion: deckhouse.io/v1alpha1
kind: LocalPathProvisioner
metadata:
  name: localpath-monitoring
spec:
  nodeGroups:
  - monitoring
  path: "/opt/local-path-provisioner-monitoring"
  reclaimPolicy: Delete
---
#
# Класс для хранения данных по узлах прочих нагрузок (опционально)
#
apiVersion: deckhouse.io/v1alpha1
kind: LocalPathProvisioner
metadata:
  name: localpath-worker
spec:
  nodeGroups:
  - worker
  path: "/opt/local-path-provisioner-worker"
  reclaimPolicy: Delete
```

## Шаг 1: Установка DKP на первый узел

1. Запустите установщик DKP из каталога, в котором размещен конфигурационный файл `config.yml`, командой ниже, указав корректный путь до образов DKP:

```bash
docker run -it \
    --pull=always \
    -v "$(pwd)/config.yml:/config.yml" \
    -v "$HOME/.ssh/:/tmp/.ssh/" \
    registry.example.com:5000/your/path/to/cse/install:v1.67.1 \
    bash
```

2. Внутри запущенного контейнера выполните команду, предварительно исправив обязательные параметры `ВАШЕ_ИМЯ_ПОЛЬЗОВАТЕЛЯ`, `IP_АДРЕС_МАСТЕР_УЗЛА`, `ВАШ_SSH_КЛЮЧ` на ваши значения:

```yaml
dhctl bootstrap --ssh-user='ВАШЕ_ИМЯ_ПОЛЬЗОВАТЕЛЯ' --ssh-host='IP_АДРЕС_МАСТЕР_УЗЛА' --ssh-agent-private-keys=/tmp/.ssh/ВАШ_SSH_КЛЮЧ --config=/config.yml --ask-become-pass
```

Установщик произведет необходимую настройку первого master узла кластера.

3. Дождитесь завершения установки DKP, после чего перейдите на master узел по SSH для выполнения дальнейших шагов.

## Шаг 2: Добавление новых узлов в кластер DKP

Для добавления новых узлов в кластер DKP используется встроенный функционал NodeGroup, который позволяет автоматически распределять различные виды нагрузок между группами узлов кластера.

* **Master узлы** предназначены для размещения ключевых компонентов, отвечающих за управление кластером DKP и его компонентами. Минимальное количество узлов: 1. Минимальное количество узлов для режима высокой доступности: 3.

* **System узлы** предназначены для запуска служебных компонентов DKP. Для тестовых окружений и окружений разработки допускается размещение Prometheus на данных узлах. Для боевых окружений Prometheus рекомендуется выносить на отдельные узлы группы Monitoring.

* **Monitoring узлы** предназначены для запуска Prometheus отдельно от других системных компонентов для боевых окружений.

* **Frontend узлы** предназначены для приема входящего трафика через Nginx Ingress Controller.

* **Worker узлы** предназначены для любых других нагрузок.

*Следование данному подходу не является обязательным. Вы можете иметь только лишь узлы группы Worker в своем кластере, либо создавать собственные группы узлов по своему усмотрению. Однако, стоит помнить, что группа узлов Master является обязательной, и должен существовать хотя бы 1 узел в этой группе*.

Важно: шаги 1-3 уже были автоматически выполнены, благодаря добавлению объектов в установочный конфигурационный файл `config.yml`, поэтому вы можете их пропустить.

1. Создание NodeGroup для System узлов происходит на master узле через вызов команды `kubectl create -f system.yml` для манифеста следующего содержания:

```yaml
apiVersion: deckhouse.io/v1
kind: NodeGroup
metadata:
  name: system
spec:
  nodeTemplate:
    labels:
      node-role.deckhouse.io/system: ""
    taints:
      - effect: NoExecute
        key: dedicated.deckhouse.io
        value: system
  nodeType: Static
```

2. Создание NodeGroup для Frontend узлов происходит на master узле через вызов команды `kubectl create -f frontend.yml` для манифеста следующего содержания:

```yaml
apiVersion: deckhouse.io/v1
kind: NodeGroup
metadata:
  name: frontend
spec:
  nodeTemplate:
    labels:
      node-role.deckhouse.io/frontend: ""
    taints:
      - effect: NoExecute
        key: dedicated.deckhouse.io
        value: frontend
  nodeType: Static
```

3. Создание NodeGroup для Worker узлов происходит на master узле через вызов команды `kubectl create -f worker.yml` для манифеста следующего содержания:

```yaml
apiVersion: deckhouse.io/v1
kind: NodeGroup
metadata:
  name: worker
spec:
  nodeType: Static
```

4. (Опционально) Создание NodeGroup для Monitoring узлов происходит на master узле через вызов команды `kubectl create -f monitoring.yml` для манифеста следующего содержания:

```yaml
apiVersion: deckhouse.io/v1
kind: NodeGroup
metadata:
  name: monitoring
spec:
  nodeTemplate:
    labels:
      node-role.deckhouse.io/monitoring: ""
    taints:
      - effect: NoExecute
        key: dedicated.deckhouse.io
        value: monitoring
  nodeType: Static
```

5. Посмотреть созданные NodeGroup можно командой:

```bash
kubectl get ng
```

6. Для каждой группы узлов можно получить bootstrap скрипт для автоматической настройки и введения узлов в кластер.

```bash
kubectl -n d8-cloud-instance-manager get secret manual-bootstrap-for-NODE_GROUP_NAME -o json | jq '.data."bootstrap.sh"' -r
```

Пример для группы узлов `system`:
```bash
kubectl -n d8-cloud-instance-manager get secret manual-bootstrap-for-system -o json | jq '.data."bootstrap.sh"' -r
```

7. Получите bootstrap скрипты для требуемых групп узлов командой из п.6, выполненной на master узле, и затем выполните полученные скрипты на целевых узлах, которые планируете ввести в кластер согласно выбранным группам, командой ниже:

```yaml
echo <Base64-КОД-СКРИПТА> | base64 -d | sudo bash
```

Важно: токены для добавления новых узлов в кластер действуют 4 часа. По истечении этого времени потребуется получить новый bootstrap скрипт, следуя указаниям в п.6 секции "Шаг 2: Добавление новых узлов в кластер DKP".

8. После завершения выполнения скриптов на всех узлах, проверьте корректность их добавления командой:

```bash
kubectl get ng
```

Добавление master узлов в кластер происходит по аналогии с узлами других групп.

Подробнее читайте в документации: [https://deckhouse.ru/documentation/v1/modules/040-control-plane-manager/faq.html#как-добавить-master-узел-в-статическом-или-гибридном-кластере](https://deckhouse.ru/documentation/v1/modules/040-control-plane-manager/faq.html#как-добавить-master-узел-в-статическом-или-гибридном-кластере)

**Важно:** при наличии в кластере DKP трех master узлов автоматически включается режим высокой доступности для таких компонентов как `etcd` и `deckhouse`. 

## Шаг 3: Первичная настройка DKP

### Настройка собственного SSL-сертификата (если не было сделано ранее при установке платформы)

1. Перенесите на master узел следующие файлы для вашего SSL-сертификата:

- файл с ключом от SSL-сертификата
- файл с SSL-сертификатом

2. Выполните команду ниже, чтобы создать в кластере DKP секрет с SSL-сертификатом:

```bash
kubectl create secret tls example-com-tls \
  --key example.com.key \
  --cert example.com.crt \
  -n d8-system
```

**Важно:** название секрета (в данном случае `example-com-tls`) должно совпадать с названием секрета, указанном в `customCertificate.secretName` для ModuleConfig `global` из конфигурационного файла `config.yml`.

Поменять название секрета после установки можно командой:

```bash
kubectl edit mc global
```

### Прием внешнего трафика

1. Создайте IngressNginxController, выполнив на master узле команду `kubectl create -f ingress.yml` для манифеста следующего содержания:

```yaml
apiVersion: deckhouse.io/v1
kind: IngressNginxController
metadata:
  name: main
spec:
  annotationValidationEnabled: false
  chaosMonkey: false
  disableHTTP2: true
  hsts: false
  ingressClass: nginx
  # inlet: HostWithFailover
  inlet: HostPort
  hostPort:
    httpPort: 80
    httpsPort: 443
  maxReplicas: 2
  minReplicas: 1
  nodeSelector:
    # Пример ниже предполагает наличие frontend узлов в кластере.
    # Замените на своё значение, если требуется
    node-role.kubernetes.io/frontend: ""
  tolerations:
  - effect: NoExecute
    key: dedicated.deckhouse.io
    value: frontend
  underscoresInHeaders: false
  validationEnabled: true
```

### Административный доступ

1. Создайте пользователя с правами `SuperAdmin`, выполнив на master узле команду `kubectl create -f user.yml` для манифеста следующего содержания:

```yaml
apiVersion: deckhouse.io/v1
kind: ClusterAuthorizationRule
metadata:
  name: admin
spec:
  subjects:
  - kind: User
    name: admin@deckhouse.ru
  # предустановленный шаблон уровня доступа
  accessLevel: SuperAdmin
  # разрешить пользователю делать kubectl port-forward
  portForwarding: true
---
apiVersion: deckhouse.io/v1
kind: User
metadata:
  name: admin
spec:
  # e-mail пользователя
  email: admin@deckhouse.ru
  # это хэш пароля yv6dw6p18h, сгенерированного сейчас
  # сгенерируйте свой или используйте этот, но только для тестирования
  # echo "yv6dw6p18h" | htpasswd -BinC 10 "" | cut -d: -f2 | base64 -w0
  # возможно, захотите изменить
  password: 'JDJhJDEwJGh5cVdMU2NNTWNFMGwuRVd0RkV4Ly42T0UwR2FRNUl6QnVrQnpnaVByRmVYZ211bXBlVy5L'
---
apiVersion: deckhouse.io/v1alpha1
kind: Group
metadata:
  name: admins
spec:
  name: admins
  members:
    - kind: User
      name: admin
```

## Шаг 4: Проверка корректности установки DKP

1. Убедитесь, что вывод команды `kubectl get clusteralerts.deckhouse.io` имеет примерно следующий вид:

```
NAME               ALERT                              SEVERITY   AGE     LAST RECEIVED   STATUS
XXXXXXX   D8DeckhouseIsNotOnReleaseChannel   9          3m49s   49s             firing
```

2. Убедитесь, что очередь Deckhouse пуста (нет задач в обработке):

Для кластера DKP с одним master узлом:

```bash
kubectl -n d8-system exec -ti deploy/deckhouse -- deckhouse-controller queue list
```

Для кластера DKP с несколькими master узлами:

```bash
kubectl -n d8-system exec -ti svc/deckhouse-leader -- deckhouse-controller queue list
```

3. Убедитесь, что есть доступ к системным веб-интерфейсам через браузер (может потребоваться дать согласие на использование самоподписанного сертификата). Например, для `publicDomainTemplate` со значением `%s.cse.example.com` системные веб-интерфейсы будут следующие:

- https://grafana.cse.example.com/
- https://grafana.cse.example.com/prometheus/alerts
- https://kubeconfig.cse.example.com/
- https://documentation.cse.example.com/
- https://hubble.cse.example.com (требуется включить модуль)

4. Проверьте, что на главной странице Grafana корректно отображаются все данные для установленных компонентов DKP.

## Шаг 5: Включение модуля Console (UI)

Модуль Console (UI) позволяет управлять платформой через веб-интерфейс, доступный по адресу вида `https://console.cse.example.com`, где `cse.example.com` соответствует шаблону `%s.cse.example.com`, указанному в переменной `publicDomainTemplate` модуля `Global`.

Включить модуль можно командой вида `kubectl create -f console.yml`, где содержимое файла `console.yml` имеет следующий вид:

```yaml
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: console
spec:
  enabled: true
```

Подробнее о настройках модуля можно узнать по ссылке [https://deckhouse.ru/products/kubernetes-platform/modules/console/stable/](https://deckhouse.ru/products/kubernetes-platform/modules/console/stable/).
