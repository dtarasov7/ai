# Стратегия управления сертификатами для Deckhouse в изолированной среде

## 1. Гибридная архитектура PKI

### Разделение зон ответственности

```
Корпоративная PKI (вне кластера, ручной режим)
├── Сертификаты для внешних Ingress
├── Сертификаты для интеграции с корп. системами
└── Trust anchors для внешних сервисов

Внутрикластерная PKI (автоматизированная)
├── Self-signed Root CA (для Deckhouse)
├── Internal Intermediate CA
│   ├── Сертификаты для внутренних сервисов
│   ├── Service mesh сертификаты
│   └── Webhook сертификаты
└── Временные сертификаты для pod-to-pod
```

## 2. Стратегия для корпоративных сертификатов (ручной режим)

### Процесс получения корпоративных сертификатов

```bash
#!/bin/bash
# prepare-corp-cert-request.sh

DOMAIN="app.corp.local"
NAMESPACE="production"

# 1. Генерация приватного ключа
openssl genrsa -out ${DOMAIN}.key 4096

# 2. Создание CSR с корректными параметрами
cat > ${DOMAIN}.conf <<EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
C = RU
ST = Moscow
L = Moscow
O = Corporation
OU = IT Department
CN = ${DOMAIN}

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${DOMAIN}
DNS.2 = *.${DOMAIN}
EOF

openssl req -new -key ${DOMAIN}.key \
  -out ${DOMAIN}.csr \
  -config ${DOMAIN}.conf

echo "CSR создан: ${DOMAIN}.csr"
echo "Отправьте CSR в корпоративную службу PKI для подписания"
```

### Импорт корпоративных сертификатов в кластер

```bash
#!/bin/bash
# import-corp-cert.sh

DOMAIN="app.corp.local"
NAMESPACE="production"
CERT_FILE="${DOMAIN}.crt"
KEY_FILE="${DOMAIN}.key"
CA_BUNDLE="corp-ca-bundle.crt"

# Создание секрета с корпоративным сертификатом
kubectl create secret tls ${DOMAIN}-tls \
  --cert=${CERT_FILE} \
  --key=${KEY_FILE} \
  --namespace=${NAMESPACE} \
  --dry-run=client -o yaml | \
  kubectl label -f - --dry-run=client -o yaml \
    cert-type=corporate \
    expiry-date="$(openssl x509 -in ${CERT_FILE} -noout -enddate | cut -d= -f2)" \
    manual-renewal=true | \
  kubectl apply -f -

# Создание ConfigMap с CA bundle для валидации
kubectl create configmap corp-ca-bundle \
  --from-file=ca.crt=${CA_BUNDLE} \
  --namespace=${NAMESPACE} \
  -o yaml --dry-run=client | kubectl apply -f -
```

### Мониторинг истечения корпоративных сертификатов

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: corp-cert-monitor
  namespace: d8-monitoring
data:
  check-corp-certs.sh: |
    #!/bin/bash
    # Скрипт для проверки сроков действия корпоративных сертификатов
    
    WARN_DAYS=60
    CRITICAL_DAYS=30
    
    for secret in $(kubectl get secrets -A -l cert-type=corporate -o name); do
      namespace=$(echo $secret | cut -d/ -f1)
      name=$(echo $secret | cut -d/ -f2)
      
      cert=$(kubectl get secret -n $namespace $name -o jsonpath='{.data.tls\.crt}' | base64 -d)
      expiry=$(echo "$cert" | openssl x509 -noout -enddate | cut -d= -f2)
      expiry_epoch=$(date -d "$expiry" +%s)
      now_epoch=$(date +%s)
      days_left=$(( ($expiry_epoch - $now_epoch) / 86400 ))
      
      if [ $days_left -lt $CRITICAL_DAYS ]; then
        echo "CRITICAL: Certificate $namespace/$name expires in $days_left days"
        # Отправка уведомления в корпоративную систему мониторинга
      elif [ $days_left -lt $WARN_DAYS ]; then
        echo "WARNING: Certificate $namespace/$name expires in $days_left days"
      fi
    done
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: corp-cert-monitor
  namespace: d8-monitoring
spec:
  schedule: "0 9 * * *"  # Ежедневно в 9:00
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: monitor
            image: registry.deckhouse.io/deckhouse/ce/tools:latest
            command: ["/bin/bash", "/scripts/check-corp-certs.sh"]
            volumeMounts:
            - name: script
              mountPath: /scripts
          volumes:
          - name: script
            configMap:
              name: corp-cert-monitor
              defaultMode: 0755
          restartPolicy: OnFailure
```

## 3. Автоматизированная стратегия для внутренних сертификатов

### Инициализация внутренней PKI

```yaml
# Создание самоподписанного корневого CA для внутреннего использования
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-issuer
spec:
  selfSigned: {}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: internal-root-ca
  namespace: d8-cert-manager
spec:
  isCA: true
  commonName: deckhouse-internal-root-ca
  secretName: internal-root-ca-secret
  duration: 87600h    # 10 лет
  renewBefore: 8760h  # обновить за 1 год
  subject:
    organizations:
      - deckhouse-internal
  issuerRef:
    name: selfsigned-issuer
    kind: ClusterIssuer
---
# Intermediate CA для выпуска сертификатов
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: internal-ca-issuer
spec:
  ca:
    secretName: internal-root-ca-secret
```

### Автоматический выпуск для внутренних сервисов

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: internal-service-tls
  namespace: default
spec:
  secretName: internal-service-tls-secret
  duration: 720h      # 30 дней для внутренних сервисов
  renewBefore: 168h   # обновить за 7 дней
  subject:
    organizations:
      - internal
  dnsNames:
    - service.default.svc.cluster.local
    - service.default.svc
    - service
  issuerRef:
    name: internal-ca-issuer
    kind: ClusterIssuer
```

## 4. Процедуры обновления сертификатов

### Автоматизация запроса на обновление корпоративных сертификатов

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cert-renewal-automation
  namespace: d8-system
data:
  prepare-renewal-requests.sh: |
    #!/bin/bash
    # Генерация CSR для сертификатов, требующих обновления
    
    RENEWAL_THRESHOLD_DAYS=45
    OUTPUT_DIR="/renewal-requests"
    
    mkdir -p ${OUTPUT_DIR}
    
    for secret in $(kubectl get secrets -A -l cert-type=corporate -o json | \
      jq -r '.items[] | select(.metadata.labels["manual-renewal"] == "true") | 
      "\(.metadata.namespace)/\(.metadata.name)"'); do
      
      namespace=$(echo $secret | cut -d/ -f1)
      name=$(echo $secret | cut -d/ -f2)
      
      # Проверка срока действия
      cert=$(kubectl get secret -n $namespace $name -o jsonpath='{.data.tls\.crt}' | base64 -d)
      days_left=$(( ($(date -d "$(echo "$cert" | openssl x509 -noout -enddate | cut -d= -f2)" +%s) - $(date +%s)) / 86400 ))
      
      if [ $days_left -lt $RENEWAL_THRESHOLD_DAYS ]; then
        # Извлечение информации из существующего сертификата
        cn=$(echo "$cert" | openssl x509 -noout -subject | sed 's/.*CN = //')
        
        # Генерация нового ключа и CSR
        openssl genrsa -out ${OUTPUT_DIR}/${name}.key 4096
        openssl req -new -key ${OUTPUT_DIR}/${name}.key \
          -out ${OUTPUT_DIR}/${name}.csr \
          -subj "/C=RU/O=Corporation/CN=${cn}"
        
        echo "CSR создан для $namespace/$name: ${OUTPUT_DIR}/${name}.csr"
        
        # Создание инструкции для администратора
        cat > ${OUTPUT_DIR}/${name}.README <<EOF
    Сертификат: $namespace/$name
    CN: ${cn}
    Истекает через: ${days_left} дней
    
    Действия:
    1. Отправьте файл ${name}.csr в корпоративную PKI
    2. После получения подписанного сертификата выполните:
       ./update-corp-cert.sh $namespace $name ${name}.crt ${name}.key
    EOF
      fi
    done
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cert-renewal-prep
  namespace: d8-system
spec:
  schedule: "0 10 * * MON"  # Каждый понедельник
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: renewal-prep
            image: registry.deckhouse.io/deckhouse/ce/tools:latest
            command: ["/bin/bash", "/scripts/prepare-renewal-requests.sh"]
            volumeMounts:
            - name: scripts
              mountPath: /scripts
            - name: output
              mountPath: /renewal-requests
          volumes:
          - name: scripts
            configMap:
              name: cert-renewal-automation
          - name: output
            persistentVolumeClaim:
              claimName: cert-renewal-requests
          restartPolicy: OnFailure
```

### Скрипт обновления корпоративных сертификатов

```bash
#!/bin/bash
# update-corp-cert.sh

NAMESPACE=$1
SECRET_NAME=$2
NEW_CERT=$3
NEW_KEY=$4

if [ $# -ne 4 ]; then
    echo "Usage: $0 <namespace> <secret-name> <cert-file> <key-file>"
    exit 1
fi

# Проверка валидности сертификата
openssl x509 -in ${NEW_CERT} -noout || exit 1

# Проверка соответствия ключа и сертификата
CERT_MODULUS=$(openssl x509 -in ${NEW_CERT} -noout -modulus | md5sum)
KEY_MODULUS=$(openssl rsa -in ${NEW_KEY} -noout -modulus | md5sum)

if [ "$CERT_MODULUS" != "$KEY_MODULUS" ]; then
    echo "ERROR: Certificate and key do not match!"
    exit 1
fi

# Создание резервной копии
kubectl get secret -n ${NAMESPACE} ${SECRET_NAME} -o yaml > \
  backup-${SECRET_NAME}-$(date +%Y%m%d-%H%M%S).yaml

# Обновление сертификата с сохранением меток
EXPIRY_DATE=$(openssl x509 -in ${NEW_CERT} -noout -enddate | cut -d= -f2)

kubectl create secret tls ${SECRET_NAME}-new \
  --cert=${NEW_CERT} \
  --key=${NEW_KEY} \
  --namespace=${NAMESPACE} \
  --dry-run=client -o yaml | \
  kubectl label -f - --dry-run=client -o yaml \
    cert-type=corporate \
    expiry-date="${EXPIRY_DATE}" \
    manual-renewal=true \
    updated-at="$(date -Iseconds)" | \
  kubectl apply -f -

# Постепенное переключение
kubectl patch secret ${SECRET_NAME} -n ${NAMESPACE} \
  --type='json' -p='[{"op": "replace", "path": "/data", "value": '$(kubectl get secret ${SECRET_NAME}-new -n ${NAMESPACE} -o json | jq .data)'}]'

# Удаление временного секрета
kubectl delete secret ${SECRET_NAME}-new -n ${NAMESPACE}

echo "Certificate ${NAMESPACE}/${SECRET_NAME} successfully updated"
echo "Expiry date: ${EXPIRY_DATE}"

# Перезапуск подов, использующих сертификат
kubectl get pods -n ${NAMESPACE} -o json | \
  jq -r '.items[] | select(.spec.volumes[]?.secret?.secretName == "'${SECRET_NAME}'") | .metadata.name' | \
  xargs -r kubectl delete pod -n ${NAMESPACE}
```

## 5. Интеграция с Deckhouse

### Настройка для разных типов сертификатов

```yaml
# Для внешних ingress с корпоративными сертификатами
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: external-app
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    # Не использовать cert-manager для этого ingress
    cert-manager.io/cluster-issuer: "none"
spec:
  tls:
  - hosts:
    - app.corp.local
    secretName: app.corp.local-tls  # Корпоративный сертификат
  rules:
  - host: app.corp.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: app
            port:
              number: 80
---
# Для внутренних сервисов с автоматическими сертификатами
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: internal-service
  namespace: default
  annotations:
    cert-manager.io/cluster-issuer: "internal-ca-issuer"
spec:
  tls:
  - hosts:
    - service.cluster.local
    secretName: service-internal-tls  # Автоматический сертификат
  rules:
  - host: service.cluster.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: service
            port:
              number: 8080
```

### Глобальная конфигурация Deckhouse

```yaml
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: global
spec:
  version: 1
  settings:
    modules:
      https:
        mode: CertManager
        certManager:
          # Для внутренних сервисов Deckhouse
          clusterIssuerName: internal-ca-issuer
---
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: cert-manager
spec:
  version: 1
  enabled: true
  settings:
    # Дополнительные CA для trust store
    additionalCACerts:
    - name: corporate-root-ca
      data: |
        -----BEGIN CERTIFICATE-----
        <Корпоративный Root CA>
        -----END CERTIFICATE-----
```

## 6. Операционные процедуры

### Чек-лист для администратора

```markdown
# Ежемесячные задачи
- [ ] Проверить отчет мониторинга сертификатов
- [ ] Подготовить CSR для сертификатов с истекающим сроком
- [ ] Отправить CSR в корпоративную PKI службу

# Квартальные задачи
- [ ] Аудит всех корпоративных сертификатов в кластере
- [ ] Обновление документации по процедурам
- [ ] Тестирование процедуры аварийного восстановления

# При получении новых корпоративных сертификатов
- [ ] Валидация сертификата и ключа
- [ ] Создание резервной копии старого сертификата
- [ ] Импорт нового сертификата в кластер
- [ ] Проверка работоспособности сервисов
- [ ] Документирование изменений
```

### Dashboard для мониторинга

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cert-dashboard
  namespace: d8-monitoring
data:
  dashboard.html: |
    <!DOCTYPE html>
    <html>
    <head><title>Certificate Status</title></head>
    <body>
    <h1>Статус сертификатов</h1>
    <h2>Корпоративные сертификаты (ручное обновление)</h2>
    <table border="1">
      <tr>
        <th>Namespace</th>
        <th>Secret</th>
        <th>CN</th>
        <th>Истекает</th>
        <th>Дней осталось</th>
        <th>Статус</th>
      </tr>
      <!-- Заполняется скриптом -->
    </table>
    
    <h2>Внутренние сертификаты (автоматическое обновление)</h2>
    <table border="1">
      <tr>
        <th>Namespace</th>
        <th>Certificate</th>
        <th>Issuer</th>
        <th>Ready</th>
        <th>Renewal</th>
      </tr>
      <!-- Заполняется из cert-manager metrics -->
    </table>
    </body>
    </html>
```

## 7. Best Practices

### Рекомендации по срокам действия

| Тип сертификата | Срок действия | Обновление за | Обоснование |
|-----------------|---------------|---------------|-------------|
| Корпоративные внешние | 1-2 года | 60 дней | Ручной процесс требует времени |
| Внутренние сервисы | 30-90 дней | 7-15 дней | Автоматизировано |
| Service mesh | 24 часа | 1 час | Минимизация рисков |
| Webhook/admission | 1 год | 30 дней | Стабильность |

### Разделение ответственности

```yaml
# Метки для классификации сертификатов
metadata:
  labels:
    cert-type: "corporate|internal|temporary"
    renewal-type: "manual|automatic"
    criticality: "high|medium|low"
    owner-team: "platform|security|application"
```

Эта стратегия минимизирует ручную работу с корпоративными сертификатами, используя их только для критически важных точек входа, и максимально автоматизирует управление внутренними сертификатами через встроенные механизмы Deckhouse.
