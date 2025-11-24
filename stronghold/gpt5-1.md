Ниже — 4 рабочих способа доставлять секреты из Deckhouse Stronghold в приложения в кластере Deckhouse (в том числе когда Stronghold развёрнут вне кластера). Для каждого — архитектура, требования к приложению, примеры конфигов и плюсы/минусы.

Важно: Stronghold совместим с API HashiCorp Vault, поэтому большинство инструментов/подходов «как для Vault» применимы без изменений. В Deckhouse есть отдельный модуль secrets-store-integration, который автоматизирует внедрение секретов в Pods как переменные окружения и как файлы через CSI. 

Подготовка (общая)
- В Stronghold создайте KV v2-монтирование и секрет, политику, и роль, привязанную к ServiceAccount вашего приложения (SA/NS). Пример CLI-команд и рекомендуемый TTL (обычно ~10m) есть в руководстве по secrets-store-integration; там же — инструкции для локального и удалённого (external) Stronghold и для разных путей аутентификации (authPath). 
- Для Kubernetes‑аутентификации Stronghold должен уметь делать TokenReview/SubjectAccessReview. Дайте либо вашему приложению роль system:auth-delegator, либо настройте у Stronghold отдельный reviewer SA с нужными правами. 

Решение 1. Инжекция как переменных окружения через модуль secrets-store-integration (mutating webhook)
Когда применять
- Нужно получать секреты в ENV на старте контейнера без хранения их в Kubernetes Secret/etcd.
- Нужна простая интеграция «аннотациями» в манифестах.

Как работает (кратко)
- В кластере появляется mutating-webhook. Если в Pod есть аннотация secrets-store.deckhouse.io/role, в Pod добавляется init-контейнер, который кладёт статический бинарник-инжектор в общую tmp‑директорию Pod’а. Этот бинарник заменяет команду старта контейнера: логинится в Stronghold по Kubernetes Auth, тянет секреты и устанавливает их в ENV процесса, затем делает execve оригинальной команды. 

Шаги
1) Включите модуль:
yaml
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: secrets-store-integration
spec:
  enabled: true
  version: 1
# для внешнего Stronghold укажите URL/AuthPath/CA:
# settings:
#   connection:
#     url: "https://stronghold.example.com"
#     authPath: "remote-kube-1"
#     caCert: |-
#       -----BEGIN CERTIFICATE-----...-----END CERTIFICATE-----
#   connectionConfiguration: Manual
# По умолчанию DiscoverLocalStronghold для «локального» Stronghold.
2) В Stronghold подготовьте kv2 и роль (пример из документации):
bash
stronghold secrets enable -path=demo-kv -version=2 kv
stronghold kv put demo-kv/myapp-secret DB_USER="username" DB_PASS="secret-password"
stronghold policy write myapp-ro-policy - <<'EOF'
path "demo-kv/data/myapp-secret" { capabilities = ["read"] }
EOF
stronghold write auth/kubernetes_local/role/myapp-role \
  bound_service_account_names=myapp-sa \
  bound_service_account_namespaces=myapp-namespace \
  policies=myapp-ro-policy \
  ttl=10m
3) Пример Pod с «веткой» секретов (все ключи одного KV-секрета):
yaml
apiVersion: v1
kind: Pod
metadata:
  name: myapp1
  namespace: myapp-namespace
  annotations:
    secrets-store.deckhouse.io/role: "myapp-role"
    secrets-store.deckhouse.io/env-from-path: demo-kv/data/myapp-secret
spec:
  serviceAccountName: myapp-sa
  containers:
  - name: app
    image: alpine:3.20
    command: ["sh","-c","env; sleep 3600"]
4) Точечная подстановка отдельных ключей:
yaml
containers:
- name: app
  image: alpine:3.20
  env:
  - name: DB_USER
    value: secrets-store:demo-kv/data/myapp-secret#DB_USER
  - name: DB_PASS
    value: secrets-store:demo-kv/data/myapp-secret#DB_PASS
  command: ["sh","-c","printenv | grep DB_; sleep 3600"]

PlantUML (sequence)
plantuml
@startuml
actor Dev as D
participant "Mutating Webhook\n(secrets-store-integration)" as WH
participant Pod
participant "Injector (entrypoint wrapper)" as IJ
participant "Stronghold\n(Kubernetes Auth + KV v2)" as SH

D -> Pod : kubectl apply (Pod with annotations)
Pod -> WH : AdmissionReview (CREATE)
WH --> Pod : mutate: add init + wrapper
Pod -> IJ : start wrapper
IJ -> SH : auth/kubernetes: login(jwt SA)
SH --> IJ : client_token (ttl~10m)
IJ -> SH : GET demo-kv/data/myapp-secret
SH --> IJ : {DB_USER, DB_PASS}
IJ -> Pod : setenv + exec original cmd
@enduml

Требования к приложению
- Принимает секреты через ENV на старте. Для «горячего» обновления потребуется перезапуск Pod’а (ENV не обновляется на лету).

Плюсы
- Нет хранения секрета в etcd/Kubernetes Secret.
- Максимально «нативно» для Deckhouse; минимум манифестов. 

Минусы
- Обновление секретов требует рестарта Pod.
- ENV попадает в /proc/<pid>/environ и может засветиться в отладочных дампах — учитывайте операционные риски.

Решение 2. Монтирование секретов как файлов через CSI (SecretsStoreImport)
Когда применять
- Приложению проще читать конфигурацию/ключи из файлов.
- Нужны «горячие» обновления без рестарта (приложение должно уметь перечитывать файл или ловить SIGHUP).

Как работает
- CR SecretsStoreImport описывает какие ключи из Stronghold смонтировать в Pod через CSI-драйвер secrets-store.csi.deckhouse.io. Контроллер аутентифицируется в Stronghold и кладёт файлы в volume. Есть нюансы с subPath: при его использовании обновления файлов не попадут в контейнер. 

Пример CR + Pod
yaml
apiVersion: deckhouse.io/v1alpha1
kind: SecretsStoreImport
metadata:
  name: myapp-ssi
  namespace: myapp-namespace
spec:
  type: CSI
  role: myapp-role
  files:
    - name: "db-password"
      source:
        path: "demo-kv/data/myapp-secret"
        key: "DB_PASS"
---
apiVersion: v1
kind: Pod
metadata:
  name: myapp3
  namespace: myapp-namespace
spec:
  serviceAccountName: myapp-sa
  containers:
  - name: app
  - image: alpine:3.20
    command: ["sh","-c","while cat /mnt/secrets/db-password; do echo; sleep 5; done"]
    volumeMounts:
    - name: secrets
      mountPath: /mnt/secrets
  volumes:
  - name: secrets
    csi:
      driver: secrets-store.csi.deckhouse.io
      volumeAttributes:
        secretsStoreImport: "myapp-ssi"

PlantUML (component)
plantuml
@startuml
node "K8s Node" {
  [Pod: App] -down- (CSI Volume)
  (CSI Volume) -down- [secrets-store.csi.deckhouse.io]
}
[secrets-store-integration ctrl] -right-> [Stronghold]
[Pod: App] ..> (files under /mnt/secrets) : read()
@enduml

Требования к приложению
- Читает секреты из файлов; желательно уметь перечитывать при изменении.

Плюсы
- Секреты не хранятся в etcd.
- Можно обновлять содержимое файлов без рестарта приложения (если приложение это поддерживает). 

Минусы
- Дополнительная зависимость от CSI‑тома.
- Нельзя использовать subPath, если хотите получать обновления. 

Решение 3. External Secrets Operator (ESO): синхронизация в Kubernetes Secret
Когда применять
- Требуется «стандартный» для экосистемы K8s паттерн: все приложения работают с обычным Secret.
- Есть ограничения/политики, запрещающие admission‑мутаторы/CSI.

Как работает
- ESO периодически читает секреты из внешнего менеджера (в нашем случае — Stronghold по Vault‑совместимому API), создаёт/обновляет нативные Kubernetes Secret, а поды используют их как обычно: envFrom/volume. Это удобно, но секрет попадает в etcd (шифруйте на уровне кластера). 

Пример конфигов (Vault‑provider указывает на Stronghold):
yaml
# доступ к Stronghold (Vault provider)
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: stronghold
  namespace: myapp-namespace
spec:
  provider:
    vault:
      server: "https://stronghold.example.com"          # Stronghold URL
      path: "kubernetes_local"                           # authPath
      version: v2
      auth:
        kubernetes:
          mountPath: "kubernetes_local"                  # тот же путь
          role: "myapp-role"
          serviceAccountRef:
            name: myapp-sa
---
# указываем, какой ключ/поле вытащить
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: myapp-es
  namespace: myapp-namespace
spec:
  refreshInterval: 1m
  secretStoreRef:
    name: stronghold
    kind: SecretStore
  target:
    name: myapp-secret
    creationPolicy: Owner
  data:
    - secretKey: DB_USER
      remoteRef:
        key: demo-kv/data/myapp-secret
        property: DB_USER
    - secretKey: DB_PASS
      remoteRef:
        key: demo-kv/data/myapp-secret
        property: DB_PASS
---
# пример использования секрета приложением
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  namespace: myapp-namespace
spec:
  replicas: 1
  selector: { matchLabels: { app: myapp } }
  template:
    metadata: { labels: { app: myapp } }
    spec:
      serviceAccountName: myapp-sa
      containers:
      - name: app
        image: alpine:3.20
        envFrom:
        - secretRef: { name: myapp-secret }

PlantUML (sequence)
plantuml
@startuml
participant "ESO Controller" as ESO
participant "Stronghold (Vault API)" as SH
participant "Kubernetes API" as K8s
participant "Pod"

ESO -> SH : auth (Kubernetes Auth, role=myapp-role)
ESO -> SH : read demo-kv/data/myapp-secret
SH --> ESO : {DB_USER, DB_PASS}
ESO -> K8s : upsert Secret/myapp-secret
Pod -> K8s : mount envFrom Secret
@enduml

Требования к приложению
- Любой стандартный способ работы с Kubernetes Secret (envFrom, volume).

Плюсы
- Простая логика в приложениях и CI/CD; привычные объекты Secret.
- Гибкая шаблонизация и отслеживание изменений ESO.

Минусы
- Секреты сохраняются в etcd (учтите политику шифрования и бэкапы). 
- Дополнительный оператор в кластере.

Решение 4. Sidecar c Vault Agent (без инжектора)
Когда применять
- Нужен полностью автономный от Deckhouse‑модулей способ, в т.ч. для кластера без secrets-store‑integration.
- Хотите рендерить файлы по шаблонам и самостоятельно управлять сигналами перезагрузки приложения.

Идея
- Запускаем в Pod sidecar hashicorp/vault с agent‑режимом, настраиваем auto_auth через Kubernetes, на выход рендерим файлы (templates) в shared emptyDir; приложение читает их с диска. Поскольку Stronghold — Vault‑совместим, Agent работает «как с Vault». 

Пример (сокращённо)
yaml
apiVersion: v1
kind: Pod
metadata:
  name: myapp-agent
  namespace: myapp-namespace
spec:
  serviceAccountName: myapp-sa
  volumes:
  - name: secrets
    emptyDir: {}
  - name: agent-config
    configMap:
      name: agent-config
  containers:
  - name: app
    image: alpine:3.20
    volumeMounts:
    - { name: secrets, mountPath: /secrets }
    command: ["sh","-c","while cat /secrets/db-pass; do echo; sleep 5; done"]
  - name: vault-agent
    image: hashicorp/vault:1.15
    args: ["agent","-config=/config/agent.hcl","-log-level=info"]
    env:
    - name: VAULT_ADDR
      value: https://stronghold.example.com
    volumeMounts:
    - { name: secrets, mountPath: /secrets }
    - { name: agent-config, mountPath: /config }
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-config
  namespace: myapp-namespace
data:
  agent.hcl: |
    exit_after_auth = false
    pid_file = "/tmp/vault-agent.pid"
    auto_auth {
      method "kubernetes" {
        mount_path = "auth/kubernetes_local"
        config = {
          role = "myapp-role"
        }
      }
      sink "file" { config = { path = "/tmp/token" } }
    }
    template {
      destination = "/secrets/db-pass"
      contents = <<EOH
{{ with secret "demo-kv/data/myapp-secret" }}{{ .Data.data.DB_PASS }}{{ end }}
EOH
    }

PlantUML (sequence)
plantuml
@startuml
participant "Vault Agent (sidecar)" as A
participant "Stronghold" as SH
participant "App Container" as APP

A -> SH : auto_auth (Kubernetes Auth)
SH --> A : client_token
A -> SH : render template: get demo-kv/data/myapp-secret
SH --> A : secret data
A -> APP : write /secrets/db-pass
APP -> APP : read file /secrets/db-pass
@enduml

Требования к приложению
- Чтение секретов из файлов; желательно уметь безопасно перезагружать конфигурацию по сигналу/изменению файла.

Плюсы
- Полный контроль над шаблонами/таймерами/сигналами.
- Работает и с внешним Stronghold, и в «голом» Kubernetes.

Минусы
- Больше ручной обвязки (sidecar, конфиги).
- В отличие от варианта 1/2 нет «готового» webhook/CSI от Deckhouse.

Требования к самому приложению (обобщённо)
- Минимум: не хранить секреты в образе и логах; уметь принимать секреты через ENV (решение 1/3) или из файлов (решение 2/4).
- Для «горячей» ротации без рестартов:
  - файл‑ориентированные варианты (2/4): приложение должно либо наблюдать файл (inotify), либо корректно реагировать на SIGHUP/USR1 и перечитывать файл.
  - ENV‑варианты (1/3): требуются рестарты Pod’ов. Используйте перезапуск по событию (например, через reloader) или rollout.
- Не запускаться под root (желательно) и иметь минимальные FS‑права только на нужные пути.
- Журналирование: исключать значения секретов из логов; маскировать чувствительные ENV.
- RBAC: использовать отдельный SA на namespace/приложение; следовать принципу наименьших привилегий.

Короткое сравнение
- ENV-инжекция (решение 1): нативно, быстро, без Secrets в etcd; зато обновления — через рестарт. 
- CSI‑файлы (решение 2): не хранит в etcd, можно обновлять «на лету»; но зависит от CSI, есть ограничения с subPath. 
- ESO (решение 3): максимально совместимо со всем, удобно для GitOps; но секрет хранится в etcd (включайте шифрование и политику бэкапов). 
- Vault Agent (решение 4): гибко и автономно, но больше ручной настройки; полезно, когда нельзя ставить Deckhouse‑модули.

Особенности внешнего Stronghold
- В secrets-store-integration можно явно указать URL/authPath/CA для внешнего Stronghold (см. settings.connection.*). Для «локального» Stronghold достаточно просто включить модуль. 
- В Stronghold предусмотрены Kubernetes/JWT‑аутентификация и поддержка удалённых кластеров (отдельный authPath, роли). 

Нужна помощь подобрать оптимальный вариант под ваш стек (как приложение читает конфиг, требуются ли горячие обновления, ограничения по модулям/CRD)? Опишите, пожалуйста:
- Где живёт Stronghold: в этом же кластере или отдельно (URL, TLS)?
- Как ваш сервис принимает секреты: ENV, файлы, оба?
- Требуется ли ротация без рестартов?
- Есть ли запреты на появление Secret в etcd? 

Я предложу точные манифесты под ваш случай.
