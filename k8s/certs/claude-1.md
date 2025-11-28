Оптимальная стратегия управления сертификатами для Kubernetes в изолированном корпоративном окружении 
должна учитывать специфику закрытой инфраструктуры и требования безопасности. Вот комплексный подход:

## 1. Архитектура PKI

### Иерархия сертификатов
```
Корпоративный Root CA
├── Intermediate CA для K8s
│   ├── Cluster CA (для компонентов кластера)
│   ├── ETCD CA
│   └── Front-proxy CA
└── Intermediate CA для приложений
```

### Разделение ответственности
- **Системные сертификаты**: для компонентов Kubernetes (API server, kubelet, etcd)
- **Прикладные сертификаты**: для приложений и сервисов
- **Ingress сертификаты**: для внешних точек входа

## 2. Инструменты и решения

### Cert-manager с внутренним CA
```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: internal-ca-issuer
spec:
  ca:
    secretName: internal-ca-keypair
```

### Vault PKI Engine
Для корпоративных окружений с HashiCorp Vault:
```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: vault-issuer
spec:
  vault:
    server: https://vault.corp.local
    path: pki/sign/kubernetes
    auth:
      kubernetes:
        role: cert-manager
        mountPath: /v1/auth/kubernetes
```

## 3. Стратегия создания сертификатов

### Автоматизация через cert-manager
```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: app-tls
spec:
  secretName: app-tls-secret
  duration: 8760h    # 1 год
  renewBefore: 720h  # обновить за 30 дней
  subject:
    organizationalUnits:
      - kubernetes
  commonName: app.namespace.svc.cluster.local
  dnsNames:
    - app.namespace.svc.cluster.local
    - app.namespace.svc
  issuerRef:
    name: internal-ca-issuer
    kind: ClusterIssuer
```

### Namespace-изолированные сертификаты
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cert-manager
  namespace: cert-manager
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cert-manager-controller
rules:
  - apiGroups: ["cert-manager.io"]
    resources: ["certificates", "certificaterequests"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
```

## 4. Стратегия обновления

### Автоматическое обновление
```yaml
# Настройка cert-manager для автообновления
spec:
  duration: 2160h    # 90 дней
  renewBefore: 360h  # обновить за 15 дней до истечения
  
  # Для критичных сервисов
  duration: 720h     # 30 дней
  renewBefore: 240h  # обновить за 10 дней
```

### Мониторинг истечения сертификатов
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-alerts
data:
  alerts.yaml: |
    groups:
    - name: certificates
      rules:
      - alert: CertificateExpiringSoon
        expr: certmanager_certificate_expiration_timestamp_seconds - time() < 7 * 86400
        annotations:
          summary: "Certificate {{ $labels.name }} expires in {{ $value | humanizeDuration }}"
```

## 5. Безопасность в изолированном окружении

### Хранение секретов
```yaml
# Использование Sealed Secrets
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: ca-keypair
spec:
  encryptedData:
    tls.crt: AgA5kR9Ow...
    tls.key: AgBXnBT8W...
```

### Ротация корневых сертификатов
```bash
# Скрипт для плановой ротации
#!/bin/bash
# 1. Создать новый CA
openssl req -new -x509 -days 3650 -keyout new-ca.key -out new-ca.crt

# 2. Подписать промежуточные CA новым корневым
# 3. Постепенная миграция через trust bundle
kubectl create configmap ca-bundle \
  --from-file=old-ca.crt \
  --from-file=new-ca.crt \
  -o yaml --dry-run=client | kubectl apply -f -
```

## 6. Best Practices

### Сроки жизни сертификатов
- **Root CA**: 10 лет
- **Intermediate CA**: 5 лет
- **Cluster компоненты**: 1 год
- **Приложения**: 90 дней
- **Краткоживущие токены**: 24 часа

### Аудит и compliance
```yaml
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  - level: RequestResponse
    omitStages:
      - RequestReceived
    resources:
      - group: "certificates.k8s.io"
        resources: ["certificatesigningrequests"]
    namespaces: ["cert-manager", "default"]
```

### Резервное копирование
```bash
# Backup критичных сертификатов
kubectl get secret -A -o json \
  -l certmanager.k8s.io/certificate=true \
  > certificates-backup-$(date +%Y%m%d).json

# Хранить в защищенном хранилище
encrypt-and-store.sh certificates-backup-*.json
```

## 7. Интеграция с корпоративными системами

### LDAP/AD интеграция
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: webhook-config
data:
  config.yaml: |
    ldap:
      host: ldap.corp.local
      bindDN: cn=k8s,ou=services,dc=corp,dc=local
      userSearch:
        baseDN: ou=users,dc=corp,dc=local
        filter: "(objectClass=user)"
        username: sAMAccountName
```

### Централизованное логирование
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluent-bit-config
data:
  fluent-bit.conf: |
    [OUTPUT]
        Name  forward
        Match cert-manager.*
        Host  siem.corp.local
        Port  24224
        tls   on
        tls.verify on
```

Эта стратегия обеспечивает надежное, безопасное и автоматизированное управление сертификатами в изолированной корпоративной среде с минимальным ручным вмешательством и соответствием требованиям безопасности.
