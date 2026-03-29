Ниже — рабочая схема, где `nginx` проверяет **логин/пароль через Basic Auth**, а файл `htpasswd` **не хранится в Kubernetes Secret и не лежит в `env`**, а подтягивается из Vault через **Vault Agent Injector**. Nginx умеет проверять Basic Auth через директивы `auth_basic` и `auth_basic_user_file`. Vault Agent Injector подмешивает sidecar/init и рендерит секрет в файл по аннотациям Pod’а. Kubernetes auth в Vault позволяет Pod’у аутентифицироваться через токен `ServiceAccount`, а не через статический пароль. ([Nginx][1])

## Что получится

* в Vault хранится **не пароль в открытом виде**, а готовая строка для `htpasswd`, например `demo:$2y$...`
* Vault Agent кладет файл в Pod, например `/vault/secrets/htpasswd`
* `nginx` использует этот файл в `auth_basic_user_file`
* в `env` ничего чувствительного нет

---

## 1) Подготовь строку `htpasswd`

Для `nginx` нужен файл формата:

```text
demo:$2y$05$...
```

Лучше хранить **хэш**, а не plaintext. Nginx читает такой файл через `auth_basic_user_file`. ([Nginx][1])

Пример генерации строки локально:

```bash
htpasswd -nbB demo 'S3cr3t-Passw0rd'
```

Это вернет одну строку вида:

```text
demo:$2y$05$.....................................................
```

---

## 2) Положи `htpasswd` в Vault KV v2

### Через CLI

Если у тебя KV v2 смонтирован на `secret/`, запись делается командой `vault kv put`. Для KV v2 CLI сам пишет в versioned path. ([HashiCorp Developer][2])

```bash
vault kv put secret/nginx/basic-auth \
  htpasswd='demo:$2y$05$.....................................................'
```

### Через HTTP API Vault

Для KV v2 запись идет на endpoint вида `/v1/<mount>/data/<path>`. ([HashiCorp Developer][3])

```bash
curl \
  -H "X-Vault-Token: $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{
    "data": {
      "htpasswd": "demo:$2y$05$....................................................."
    }
  }' \
  https://vault.example.com/v1/secret/data/nginx/basic-auth
```

---

## 3) Создай policy в Vault

Эта policy даст Pod’у доступ только на чтение одного секрета.

### Через CLI

```bash
cat > nginx-basic-auth-policy.hcl <<'EOF'
path "secret/data/nginx/basic-auth" {
  capabilities = ["read"]
}
EOF

vault policy write nginx-basic-auth nginx-basic-auth-policy.hcl
```

### Через HTTP API

```bash
curl \
  -H "X-Vault-Token: $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -X PUT \
  -d @- \
  https://vault.example.com/v1/sys/policies/acl/nginx-basic-auth <<'JSON'
{
  "policy": "path \"secret/data/nginx/basic-auth\" { capabilities = [\"read\"] }"
}
JSON
```

Vault policy и ACL настраиваются именно через policy/API, а все маршруты API идут под префиксом `/v1/`. ([HashiCorp Developer][4])

---

## 4) Включи и настрой Kubernetes auth в Vault

### 4.1. Включить auth method

#### CLI

```bash
vault auth enable kubernetes
```

#### HTTP API

```bash
curl \
  -H "X-Vault-Token: $VAULT_TOKEN" \
  -X POST \
  https://vault.example.com/v1/sys/auth/kubernetes \
  -d '{"type":"kubernetes"}'
```

Kubernetes auth method в Vault предназначен как раз для аутентификации через токен Kubernetes Service Account. ([HashiCorp Developer][5])

### 4.2. Настроить auth method

Нужны:

* токен reviewer service account
* CA Kubernetes API
* адрес Kubernetes API

#### CLI

```bash
vault write auth/kubernetes/config \
  token_reviewer_jwt="$TOKEN_REVIEWER_JWT" \
  kubernetes_host="https://$KUBERNETES_SERVICE_HOST:$KUBERNETES_SERVICE_PORT" \
  kubernetes_ca_cert="$KUBERNETES_CA_CERT"
```

#### HTTP API

```bash
curl \
  -H "X-Vault-Token: $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -X POST \
  -d "{
    \"token_reviewer_jwt\": \"$TOKEN_REVIEWER_JWT\",
    \"kubernetes_host\": \"https://$KUBERNETES_SERVICE_HOST:$KUBERNETES_SERVICE_PORT\",
    \"kubernetes_ca_cert\": \"$KUBERNETES_CA_CERT\"
  }" \
  https://vault.example.com/v1/auth/kubernetes/config
```

Параметры конфигурации и role’и для Kubernetes auth документированы в API Vault. ([HashiCorp Developer][6])

### 4.3. Создать role, связанную с ServiceAccount

Допустим, Pod будет работать в namespace `web` под service account `nginx-vault`.

#### CLI

```bash
vault write auth/kubernetes/role/nginx-basic-auth \
  bound_service_account_names=nginx-vault \
  bound_service_account_namespaces=web \
  policies=nginx-basic-auth \
  ttl=1h
```

#### HTTP API

```bash
curl \
  -H "X-Vault-Token: $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{
    "bound_service_account_names": "nginx-vault",
    "bound_service_account_namespaces": "web",
    "policies": "nginx-basic-auth",
    "ttl": "1h"
  }' \
  https://vault.example.com/v1/auth/kubernetes/role/nginx-basic-auth
```

---

## 5) Kubernetes-манифесты

### Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: web
```

### ServiceAccount

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: nginx-vault
  namespace: web
```

### ConfigMap с конфигом nginx

Здесь `nginx` будет читать файл, который Vault Agent отрендерит в `/vault/secrets/htpasswd`. Поддержка `auth_basic` и `auth_basic_user_file` — штатная возможность nginx. ([Nginx][1])

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
        auth_basic_user_file /vault/secrets/htpasswd;

        root /usr/share/nginx/html;
        index index.html;
      }
    }
```

### ConfigMap со стартовой страницей

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-html
  namespace: web
data:
  index.html: |
    <html>
      <body>
        <h1>Protected by Vault + NGINX Basic Auth</h1>
      </body>
    </html>
```

### Deployment

Аннотации Injector нужно ставить именно на Pod template. Через аннотации можно указать, какой secret читать и как его отрендерить шаблоном. ([HashiCorp Developer][7])

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-basic-auth
  namespace: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx-basic-auth
  template:
    metadata:
      labels:
        app: nginx-basic-auth
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "nginx-basic-auth"

        # Говорим injector, какой секрет читать
        vault.hashicorp.com/agent-inject-secret-htpasswd: "secret/data/nginx/basic-auth"

        # И как из него сделать файл /vault/secrets/htpasswd
        vault.hashicorp.com/agent-inject-template-htpasswd: |
          {{- with secret "secret/data/nginx/basic-auth" -}}
          {{ .Data.data.htpasswd }}
          {{- end }}

        # Полезно, чтобы файл был готов до старта приложения
        vault.hashicorp.com/agent-pre-populate-only: "true"
    spec:
      serviceAccountName: nginx-vault
      containers:
        - name: nginx
          image: nginx:1.27
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: nginx-config
              mountPath: /etc/nginx/conf.d
              readOnly: true
            - name: nginx-html
              mountPath: /usr/share/nginx/html
              readOnly: true
      volumes:
        - name: nginx-config
          configMap:
            name: nginx-config
        - name: nginx-html
          configMap:
            name: nginx-html
```

### Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx-basic-auth
  namespace: web
spec:
  selector:
    app: nginx-basic-auth
  ports:
    - port: 80
      targetPort: 8080
```

---

## 6) Применение манифестов

```bash
kubectl apply -f namespace.yaml
kubectl apply -f serviceaccount.yaml
kubectl apply -f configmaps.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```

---

## 7) Проверка

Проверить, что Pod поднялся:

```bash
kubectl -n web get pods
```

Проверить, что Vault Agent отрендерил файл:

```bash
kubectl -n web exec deploy/nginx-basic-auth -- cat /vault/secrets/htpasswd
```

Проверить доступ:

```bash
kubectl -n web port-forward svc/nginx-basic-auth 8080:80
```

Без логина:

```bash
curl -i http://127.0.0.1:8080/
```

С логином:

```bash
curl -i -u demo:'S3cr3t-Passw0rd' http://127.0.0.1:8080/
```

---

## 8) Что важно в этом варианте

В этом примере `nginx` сам не ходит в Vault API. Это делает Vault Agent Injector/Agent по аннотациям Pod’а; он аутентифицируется в Vault через Kubernetes auth и рендерит секрет в файл. Это стандартный паттерн, который HashiCorp описывает для Kubernetes. ([HashiCorp Developer][8])

### Почему так лучше

* нет пароля к Vault в `env`
* нет Kubernetes Secret с паролем nginx
* можно ротировать `htpasswd` в Vault
* доступ ограничен policy на один путь

---

## 9) Частая ошибка

Не клади в Vault отдельно `username=demo` и `password=plain-text`, а потом не пытайся “собрать проверку” в чистом `nginx`. Для Basic Auth nginx ожидает именно файл `htpasswd`; удобнее и безопаснее хранить в Vault уже **готовую хэшированную строку** для этого файла. `auth_basic_user_file` работает именно с файлом паролей. ([Nginx][1])

---

## 10) Минимальный набор Vault API вызовов подряд

Если собрать только HTTP API, получится такой порядок:

```bash
# 1. enable kubernetes auth
curl -H "X-Vault-Token: $VAULT_TOKEN" \
  -X POST \
  -d '{"type":"kubernetes"}' \
  https://vault.example.com/v1/sys/auth/kubernetes

# 2. configure kubernetes auth
curl -H "X-Vault-Token: $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -X POST \
  -d "{
    \"token_reviewer_jwt\": \"$TOKEN_REVIEWER_JWT\",
    \"kubernetes_host\": \"https://$KUBERNETES_SERVICE_HOST:$KUBERNETES_SERVICE_PORT\",
    \"kubernetes_ca_cert\": \"$KUBERNETES_CA_CERT\"
  }" \
  https://vault.example.com/v1/auth/kubernetes/config

# 3. create policy
curl -H "X-Vault-Token: $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -X PUT \
  -d '{"policy":"path \"secret/data/nginx/basic-auth\" { capabilities = [\"read\"] }"}' \
  https://vault.example.com/v1/sys/policies/acl/nginx-basic-auth

# 4. create role
curl -H "X-Vault-Token: $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{
    "bound_service_account_names": "nginx-vault",
    "bound_service_account_namespaces": "web",
    "policies": "nginx-basic-auth",
    "ttl": "1h"
  }' \
  https://vault.example.com/v1/auth/kubernetes/role/nginx-basic-auth

# 5. put htpasswd secret to KV v2
curl -H "X-Vault-Token: $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{
    "data": {
      "htpasswd": "demo:$2y$05$....................................................."
    }
  }' \
  https://vault.example.com/v1/secret/data/nginx/basic-auth
```

---

Если хочешь, я могу следующим сообщением дать тебе **полностью готовый комплект файлов** под `kubectl apply -f`, включая `ClusterRoleBinding` для reviewer service account и пример настройки самого Vault в Kubernetes.

[1]: https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html?utm_source=chatgpt.com "Module ngx_http_auth_basic_module"
[2]: https://developer.hashicorp.com/vault/docs/commands/kv/put?utm_source=chatgpt.com "kv put - Command | Vault"
[3]: https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2?utm_source=chatgpt.com "KV - Secrets Engines - HTTP API | Vault"
[4]: https://developer.hashicorp.com/vault/api-docs?utm_source=chatgpt.com "HTTP API | Vault"
[5]: https://developer.hashicorp.com/vault/docs/auth/kubernetes?utm_source=chatgpt.com "Kubernetes - Auth Methods | Vault"
[6]: https://developer.hashicorp.com/vault/api-docs/auth/kubernetes?utm_source=chatgpt.com "Kubernetes - Auth Methods - HTTP API | Vault"
[7]: https://developer.hashicorp.com/vault/docs/deploy/kubernetes/injector/examples?utm_source=chatgpt.com "Vault Agent Injector examples"
[8]: https://developer.hashicorp.com/vault/docs/deploy/kubernetes/injector?utm_source=chatgpt.com "Vault Agent Injector"

