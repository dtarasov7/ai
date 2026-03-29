Да. Ниже — **два параллельных примера для `nginx` с Basic Auth**, если вместо HashiCorp Vault использовать **Deckhouse Stronghold**.

Ключевая разница такая:

* **Вариант A:** напрямую ходим в **Stronghold API** из `initContainer`, получаем `htpasswd` и кладём его в `emptyDir`.
* **Вариант B:** используем **Deckhouse `secrets-store-integration` + CSI**, и файл `htpasswd` монтируется в Pod без собственного кода/скрипта.

Почему это корректно:
Stronghold заявлен как **HashiCorp Vault API-compatible**, доступен по `/v1`, поддерживает аутентификацию сервисными аккаунтами Kubernetes и политики. У Deckhouse есть отдельный модуль `secrets-store-integration`, который монтирует секреты в Pod как volume через CSI; сам Deckhouse пишет, что это предпочтительный путь, а для аналога Vault Agent Injector у них **“no implementation plans”**. ([Deckhouse][1])

---

# Общая идея для обоих примеров

Мы храним в Stronghold **готовую строку `htpasswd`**, например:

```text
demo:$2y$05$.....................................................
```

`nginx` читает её из файла через `auth_basic_user_file`. Это проще и безопаснее, чем пытаться склеивать plaintext-логин/пароль внутри `nginx`. Сам Stronghold — key-value хранилище, совместимое с Vault API. ([Deckhouse][1])

---

# Предварительная настройка Stronghold

## 1) Включить KV v2 и записать секрет

Deckhouse в примерах использует KV v2 и путь вида `demo-kv/data/...`. ([Deckhouse][2])

### CLI

```bash
d8 stronghold secrets enable -path=demo-kv -version=2 kv

d8 stronghold kv put demo-kv/nginx-basic-auth \
  HTPASSWD='demo:$2y$05$.....................................................'
```

### HTTP API

```bash
curl \
  --header "X-Vault-Token: ${VAULT_TOKEN}" \
  --request POST \
  --data '{"type":"kv","options":{"version":"2"}}' \
  ${VAULT_ADDR}/v1/sys/mounts/demo-kv

curl \
  --header "X-Vault-Token: ${VAULT_TOKEN}" \
  --header "Content-Type: application/json" \
  --request POST \
  --data '{
    "data": {
      "HTPASSWD": "demo:$2y$05$....................................................."
    }
  }' \
  ${VAULT_ADDR}/v1/demo-kv/data/nginx-basic-auth
```

KV v2 mount через `/v1/sys/mounts/...` и запись в `/v1/<mount>/data/<path>` соответствуют документации Deckhouse/Stronghold examples. ([Deckhouse][2])

## 2) Создать policy

```hcl
path "demo-kv/data/nginx-basic-auth" {
  capabilities = ["read"]
}
```

### CLI

```bash
cat > nginx-basic-auth-policy.hcl <<'EOF'
path "demo-kv/data/nginx-basic-auth" {
  capabilities = ["read"]
}
EOF

d8 stronghold policy write nginx-basic-auth-policy nginx-basic-auth-policy.hcl
```

### HTTP API

```bash
curl \
  --header "X-Vault-Token: ${VAULT_TOKEN}" \
  --header "Content-Type: application/json" \
  --request PUT \
  --data '{
    "policy": "path \"demo-kv/data/nginx-basic-auth\" { capabilities = [\"read\"] }"
  }' \
  ${VAULT_ADDR}/v1/sys/policies/acl/nginx-basic-auth-policy
```

Stronghold использует policy-based access control. ([Deckhouse][1])

## 3) Создать role для Pod ServiceAccount

В Deckhouse examples для локального Stronghold по умолчанию используется auth path `kubernetes_local`. Для роли указываются `bound_service_account_names`, `bound_service_account_namespaces`, `policies`, `ttl`; рекомендуемый TTL в примере — `10m`. ([Deckhouse][2])

### CLI

```bash
d8 stronghold write auth/kubernetes_local/role/nginx-basic-auth-role \
  bound_service_account_names=nginx-sa \
  bound_service_account_namespaces=web \
  policies=nginx-basic-auth-policy \
  ttl=10m
```

### HTTP API

```bash
curl \
  --header "X-Vault-Token: ${VAULT_TOKEN}" \
  --request PUT \
  --data '{
    "bound_service_account_names":"nginx-sa",
    "bound_service_account_namespaces":"web",
    "policies":"nginx-basic-auth-policy",
    "ttl":"10m"
  }' \
  ${VAULT_ADDR}/v1/auth/kubernetes_local/role/nginx-basic-auth-role
```

## 4) Дать ServiceAccount право логиниться через Kubernetes auth

Deckhouse отдельно пишет: если Stronghold использует JWT самого клиента для запросов в Kubernetes `TokenReview`, то ServiceAccount приложения должен иметь `system:auth-delegator`. ([Deckhouse][3])

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: web
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: nginx-sa
  namespace: web
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: nginx-sa-stronghold-auth-delegator
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:auth-delegator
subjects:
  - kind: ServiceAccount
    name: nginx-sa
    namespace: web
```

---

# Вариант A — напрямую через Stronghold API

Это путь “почти как с Vault API”, но без Vault Agent Injector. Вместо него `initContainer` делает два HTTP-вызова:

1. логинится в Stronghold по JWT service account,
2. читает `HTPASSWD` из KV v2,
3. пишет `/work/htpasswd` в `emptyDir`.

Deckhouse рекомендует самый безопасный вариант — когда приложение само ходит в Stronghold API по HTTPS с SA token; для нашего случая `nginx` сам этого не умеет, поэтому используем промежуточный `initContainer`. Это уже ближе к их варианту “intermediate application retrieves secrets”. ([Deckhouse][4])

## Конфиг `nginx`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-config
  namespace: web
data:
  default.conf: |
    server {
      listen 8080;
      server_name _;

      location / {
        auth_basic "Restricted";
        auth_basic_user_file /etc/nginx/auth/htpasswd;

        root /usr/share/nginx/html;
        index index.html;
      }
    }
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-html
  namespace: web
data:
  index.html: |
    <html>
      <body>
        <h1>NGINX + Stronghold API</h1>
      </body>
    </html>
```

## Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-stronghold-api
  namespace: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx-stronghold-api
  template:
    metadata:
      labels:
        app: nginx-stronghold-api
    spec:
      serviceAccountName: nginx-sa
      initContainers:
        - name: fetch-htpasswd
          image: alpine:3.20
          env:
            - name: STRONGHOLD_ADDR
              value: "https://stronghold.example.com"
            - name: ROLE
              value: "nginx-basic-auth-role"
            - name: AUTH_PATH
              value: "kubernetes_local"
            - name: SECRET_PATH
              value: "demo-kv/data/nginx-basic-auth"
          command:
            - sh
            - -ec
            - |
              apk add --no-cache curl jq

              JWT="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"

              LOGIN_RESP="$(
                curl -sS \
                  -H 'Content-Type: application/json' \
                  -X POST \
                  -d "{\"role\":\"${ROLE}\",\"jwt\":\"${JWT}\"}" \
                  "${STRONGHOLD_ADDR}/v1/auth/${AUTH_PATH}/login"
              )"

              CLIENT_TOKEN="$(echo "${LOGIN_RESP}" | jq -r '.auth.client_token')"

              test -n "${CLIENT_TOKEN}" && test "${CLIENT_TOKEN}" != "null"

              SECRET_RESP="$(
                curl -sS \
                  -H "X-Vault-Token: ${CLIENT_TOKEN}" \
                  "${STRONGHOLD_ADDR}/v1/${SECRET_PATH}"
              )"

              echo "${SECRET_RESP}" | jq -r '.data.data.HTPASSWD' > /work/htpasswd
              chmod 0400 /work/htpasswd
          volumeMounts:
            - name: auth-file
              mountPath: /work

      containers:
        - name: nginx
          image: nginx:1.27
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: auth-file
              mountPath: /etc/nginx/auth
              readOnly: true
            - name: nginx-config
              mountPath: /etc/nginx/conf.d
              readOnly: true
            - name: nginx-html
              mountPath: /usr/share/nginx/html
              readOnly: true

      volumes:
        - name: auth-file
          emptyDir:
            medium: Memory
        - name: nginx-config
          configMap:
            name: nginx-config
        - name: nginx-html
          configMap:
            name: nginx-html
```

## Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx-stronghold-api
  namespace: web
spec:
  selector:
    app: nginx-stronghold-api
  ports:
    - port: 80
      targetPort: 8080
```

### Что важно в этом варианте

Endpoint логина `/v1/auth/<path>/login` я использую как **прямое следствие Vault API compatibility** Stronghold и того, что Deckhouse показывает те же auth-paths (`auth/kubernetes_local/...`) и работу через `/v1`. Это обоснованная экстраполяция, но именно этот endpoint на найденных страницах Deckhouse у меня не был показан отдельным примером запроса. Остальная часть — KV v2 path, role path, `/v1` base path — подтверждается документацией напрямую. ([Deckhouse][1])

---

# Вариант B — через Deckhouse `secrets-store-integration` + CSI

Это более “родной” для Deckhouse путь. Модуль `secrets-store-integration` монтирует секреты в Pod как volume через CSI, а для файлов используется ресурс `SecretsStoreImport`. В документации есть ровно такой шаблон: `SecretsStoreImport` + `csi.driver: secrets-store.csi.deckhouse.io` + `volumeAttributes.secretsStoreImport`. ([Deckhouse][4])

## 1) Включить модуль

Если работаешь с локальным Stronghold в том же Deckhouse-кластере, `connectionConfiguration` по умолчанию — `DiscoverLocalStronghold`. Для этого достаточно включить `stronghold` и `secrets-store-integration`. ([Deckhouse][2])

```yaml
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: secrets-store-integration
spec:
  enabled: true
  version: 1
```

## 2) `SecretsStoreImport`

У `SecretsStoreImport` есть поля `type`, `role`, `files[].source.path`, `files[].source.key`, и он определяет соответствие между Vault-compatible storage и файлами в контейнере. ([Deckhouse][5])

```yaml
apiVersion: deckhouse.io/v1alpha1
kind: SecretsStoreImport
metadata:
  name: nginx-htpasswd
  namespace: web
spec:
  type: CSI
  role: nginx-basic-auth-role
  files:
    - name: htpasswd
      source:
        path: demo-kv/data/nginx-basic-auth
        key: HTPASSWD
```

## 3) `nginx` ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-config-csi
  namespace: web
data:
  default.conf: |
    server {
      listen 8080;
      server_name _;

      location / {
        auth_basic "Restricted";
        auth_basic_user_file /mnt/secrets/htpasswd;

        root /usr/share/nginx/html;
        index index.html;
      }
    }
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-html-csi
  namespace: web
data:
  index.html: |
    <html>
      <body>
        <h1>NGINX + Deckhouse CSI</h1>
      </body>
    </html>
```

## 4) Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-stronghold-csi
  namespace: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx-stronghold-csi
  template:
    metadata:
      labels:
        app: nginx-stronghold-csi
    spec:
      serviceAccountName: nginx-sa
      containers:
        - name: nginx
          image: nginx:1.27
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: secrets
              mountPath: /mnt/secrets
              readOnly: true
            - name: nginx-config
              mountPath: /etc/nginx/conf.d
              readOnly: true
            - name: nginx-html
              mountPath: /usr/share/nginx/html
              readOnly: true
      volumes:
        - name: secrets
          csi:
            driver: secrets-store.csi.deckhouse.io
            volumeAttributes:
              secretsStoreImport: "nginx-htpasswd"
        - name: nginx-config
          configMap:
            name: nginx-config-csi
        - name: nginx-html
          configMap:
            name: nginx-html-csi
```

## 5) Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx-stronghold-csi
  namespace: web
spec:
  selector:
    app: nginx-stronghold-csi
  ports:
    - port: 80
      targetPort: 8080
```

---

# Что выбрать

**Вариант A, direct API**, выбирай если:

* нужен максимально прозрачный, “vault-like” сценарий;
* хочешь полностью контролировать login/read flow;
* не хочешь зависеть от Deckhouse CSI интеграции.

**Вариант B, CSI**, выбирай если:

* ты уже в Deckhouse и хочешь нативный путь;
* приложение не умеет работать с секретным хранилищем;
* хочешь меньше кастомных скриптов в Pod.

На практике для `nginx` в Deckhouse я бы брал именно **CSI-вариант**. Deckhouse сам позиционирует CSI как реализованный и рекомендуемый путь для файлового доступа к секретам, а для “Vault Agent Injector” у них прямо указано, что планов на реализацию нет. ([Deckhouse][4])

---

# Минимальная проверка

После деплоя любого варианта:

```bash
kubectl -n web port-forward svc/nginx-stronghold-csi 8080:80
# или
kubectl -n web port-forward svc/nginx-stronghold-api 8080:80
```

Проверка:

```bash
curl -i http://127.0.0.1:8080/
curl -i -u demo:'S3cr3t-Passw0rd' http://127.0.0.1:8080/
```

---

# Самое важное отличие от HashiCorp Vault-варианта

При переходе с Vault на Stronghold:

* **policy / role / KV пути и `/v1` API в целом почти не меняются**, потому что Stronghold совместим с Vault API. ([Deckhouse][1])
* **меняется предпочтительный способ доставки секрета в Pod**: в Deckhouse это чаще **`secrets-store-integration` + CSI**, а не Vault Agent Injector. ([Deckhouse][4])

Если хочешь, следующим сообщением я соберу из этих двух примеров **готовый архив `zip`** с файлами `01-namespace.yaml`, `02-stronghold-policy.sh`, `03-nginx-api.yaml`, `04-nginx-csi.yaml`, `README.md`.

[1]: https://deckhouse.io/modules/stronghold/ "Stronghold module | Deckhouse modules"
[2]: https://deckhouse.io/modules/secrets-store-integration/usage.html "The secrets-store-integration module: usage | Deckhouse modules"
[3]: https://deckhouse.io/modules/secrets-store-integration/usage.html?utm_source=chatgpt.com "The secrets-store-integration module: usage"
[4]: https://deckhouse.io/modules/secrets-store-integration/ "The secrets-store-integration module | Deckhouse modules"
[5]: https://deckhouse.io/modules/secrets-store-integration/stable/cr.html "The secrets-store-integration module: Custom Resources | Deckhouse modules"
