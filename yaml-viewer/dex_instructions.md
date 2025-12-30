## Все работы проводим с первого мастера под рутом

### Генерация сертификатов

Создаем корневой сертификат

```bash
openssl genrsa -out ca.key 4096
openssl req -x509 -sha256 -new -key ca.key -days 10000 -out ca.crt
```

Во второй команде отвечаем на вопросы
> Можно просто все оставить по дефолту

```bash
Country Name (2 letter code) [XX]:
State or Province Name (full name) []:
Locality Name (eg, city) []:
Organization Name (eg, company) []:
Organizational Unit Name (eg, section) []:
Common Name (e.g. server FQDN or YOUR name) []:
Email Address []:
```

Создаем запрос на сертификат для Dex

```bash
openssl genrsa -out dex.key 4096
openssl req -new -key dex.key -out dex.csr
```

Во второй команде отвечаем на вопросы.
Главное ответить на вопрос Common Name (eg, YOUR name) []:

> Остальное можно оставить по дефолту

Тут нужно вписать имя хоста, для которого генерим сертификат.
Это будет

```bash
auth.k8s.m<Ваш номер лонина>.slurm.io
```

И подписываем запрос корневым сертификатом
```bash
openssl x509 -sha256 -req -in dex.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out dex.crt -days 5000
```

После этого создаем секрет для ингресса с полученным сертификатом

```bash
kubectl create secret tls dex-tls --key dex.key --cert dex.crt --namespace kube-system
```

Повторяем для Gangway

Создаем запрос на сертификат

```bash
openssl genrsa -out gangway.key 4096
openssl req -new -key gangway.key -out gangway.csr
```

Во второй команде отвечаем на вопросы.
Главное ответить на вопрос Common Name (eg, YOUR name) []:

> Остальное можно оставить по дефолту

Тут нужно вписать имя хоста, для которого генерим сертификат.
Это будет

```bash
kubectl.k8s.m<Ваш номер лонина>.slurm.io
```

И подписываем запрос корневым сертификатом
```bash
openssl x509 -sha256 -req -in gangway.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out gangway.crt -days 5000
```

После этого создаем секрет для ингресса с полученным сертификатом

```bash
kubectl create secret tls gangway-tls --key gangway.key --cert gangway.crt --namespace kube-system
```

Далее создаем секрет с корневым сертификатом для Gangway
```bash
kubectl create secret generic ca --from-file ca.crt --namespace kube-system
```

И складываем этот же сертификат в /etc/ssl/certs/ca.crt на всех трех мастерах


### Запуск Dex и Gangway

Переходим в директорию с практикой

```bash
cd slurm/practice/2.auth/dex
```

И правим файл dex-configmap.yaml.
В нем нужно поправить <Ваш номер лонина>

```yaml
  config.yaml: |
    issuer: https://auth.k8s.m<Ваш номер лонина>.slurm.io/           # <--- тут
    web:
      http: 0.0.0.0:5556
    staticClients:
    - id: oidc-auth-client
      redirectURIs:
      - 'https://kubectl.k8s.m<Ваш номер логина>.slurm.io/callback'  # <--- и тут
      name: 'oidc-auth-client'
```

Затем нам нужно поправить файл dex-ingress.yaml
Также <Ваш номер логина>

```yaml
  rules:
  - host: auth.k8s.m<Ваш номер логина>.slurm.io  # <--- тут
    http:
      paths:
      - backend:
          serviceName: dex
          servicePort: 5556
  tls:
  - hosts:
    - auth.k8s.m<Ваш номер логина>.slurm.io      # <--- и тут
    secretName: dex-tls
```

Далее правим gangway-configmap.yaml

```yaml
data:
  gangway.yaml: |
    clusterName: "Slurm.io"
    apiServerURL: "https://api.k8s.m<Ваш номер лонина>.slurm.io:6443"                   # <--- тут
    authorizeURL: "https://auth.k8s.m<Ваш номер лонина>.slurm.io/auth"         # <--- тут
    tokenURL: "https://auth.k8s.m<Ваш номер лонина>.slurm.io/token"            # <--- тут
    clientID: "oidc-auth-client"
    clientSecret: xxxxxxxxxxxxxx
    trustedCAPath: "/opt/ca.crt"
    redirectURL: "https://kubectl.k8s.m<Ваш номер лонина>.slurm.io/callback"   # <--- и тут
    scopes: ["openid", "profile", "email", "offline_access", "groups"]
    usernameClaim: "email"
    emailClaim: "email"
```

И последнее правим gangway-ingress.yaml

```yaml
  rules:
  - host: kubectl.k8s.m<Ваш номер логина>.slurm.io     # <--- тут
    http:
      paths:
      - backend:
          serviceName: gangway-svc
          servicePort: http
  tls:
  - secretName: gangway-tls
    hosts:
    - kubectl.k8s.m<Ваш номер логина>.slurm.io         # <--- и тут
```

Создаем секрет для Gangway

```bash
kubectl -n kube-system create secret generic gangway-key --from-literal=sesssionkey=$(openssl rand -base64 32)
```

И применяем все манифесты

```bash
kubectl apply -f . -n kube-system
```

Проверяем что все поды запустились

```bash
kubectl get po -n kube-system
```

Обновляем конфигурацию kube-api

```bash
kubectl edit configmap --namespace=kube-system kubeadm-config
```

И добавляем
> Не забывая менять <Ваш номер логина>

```yaml
apiServer:
  extraArgs:
    authorization-mode: Node,RBAC
# вот отсюда
    oidc-ca-file: /etc/ssl/certs/ca.crt
    oidc-client-id: oidc-auth-client
    oidc-groups-claim: groups
    oidc-issuer-url: https://auth.k8s.m<Ваш номер логина>.slurm.io/
    oidc-username-claim: email
```

Далее на каждом из трех мастеров выполняем

```bash
kubeadm upgrade apply v1.14.1 -y
```

Проверяем как все работает.

Открываем в браузере kubectl.k8s.m<Ваш номер логина>.slurm.io
Авторизуемся, получаем инструкции для настройки доступа к кластеру.

> Единственное ограничение - так как у нас все сертификаты самоподписанные,
> то в получившемся ~/.kube/confg нужно убрать сертификат сервера и вместо него вписать 
> insecure-skip-tls-verify: true
