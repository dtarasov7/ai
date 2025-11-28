Оптимальная стратегия управления сертификатами для Deckhouse в изолированном корпоративном окружении 
без возможности выпуска корпоративных сертификатов через API:

## 1. Архитектура PKI для изолированного Deckhouse

### Иерархия сертификатов

В стандартном наборе Deckhouse включены ClusterIssuer для выпуска сертификатов 
от Let's Encrypt или самоподписанных сертификатов. 
В изолированном окружении без API потребуется своя иерархия:

```
Корпоративный Root CA (офлайн, вне кластера)
├── Intermediate CA для Deckhouse (импортированный)
│   ├── Ingress сертификаты
│   ├── Внутренние сервисы
│   └── Компоненты платформы
└── Резервный Intermediate CA
```

### Стратегия размещения CA

В закрытом окружении, когда у машин нет доступа в Интернет, установка Deckhouse почти не отличается от установки на bare metal.

## 2. Создание и управление корпоративными CA

### Импорт корпоративного Intermediate CA

Поскольку выпуск через API невозможен, необходимо вручную создать и импортировать сертификаты:

```yaml
# 1. Создание секрета с корпоративным Intermediate CA
apiVersion: v1
kind: Secret
metadata:
  name: corp-intermediate-ca
  namespace: d8-cert-manager
type: kubernetes.io/tls
data:
  tls.crt: <base64_encoded_intermediate_cert_chain>
  tls.key: <base64_encoded_intermediate_key>
```

### Настройка ClusterIssuer

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: corp-ca-issuer
spec:
  ca:
    secretName: corp-intermediate-ca
```

## 3. Стратегия выпуска сертификатов

### Самоподписанные сертификаты для внутренних сервисов

Стандартный набор включает ClusterIssuer, который выпускает самоподписанные сертификаты:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-issuer
spec:
  selfSigned: {}
---
# Bootstrap CA для внутреннего использования
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: internal-ca
  namespace: d8-cert-manager
spec:
  isCA: true
  commonName: deckhouse-internal-ca
  secretName: internal-ca-secret
  duration: 87600h    # 10 лет
  renewBefore: 8760h  # за 1 год
  issuerRef:
    name: selfsigned-issuer
    kind: ClusterIssuer
---
# ClusterIssuer для внутренних сертификатов
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: internal-ca-issuer
spec:
  ca:
    secretName: internal-ca-secret
```

### Сертификаты для приложений

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: app-tls
  namespace: production
spec:
  secretName: app-tls-secret
  duration: 8760h     # 1 год
  renewBefore: 720h   # обновить за 30 дней
  dnsNames:
    - app.production.svc.cluster.local
    - app.production.svc
  issuerRef:
    name: corp-ca-issuer
    kind: ClusterIssuer
```

## 4. Стратегия обновления сертификатов

### Автоматическое обновление

Модуль cert-manager в Deckhouse поддерживает автоматическое обновление сертификатов и их переиздание:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: service-cert
spec:
  # Критичные параметры для автообновления
  duration: 2160h     # 90 дней
  renewBefore: 360h   # за 15 дней до истечения
  
  # Для высокой доступности
  revisionHistoryLimit: 3  # хранить 3 последние версии
```

### Мониторинг сроков действия

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cert-expiry-alerts
  namespace: d8-monitoring
data:
  alerts.yaml: |
    groups:
    - name: certificates
      interval: 30s
      rules:
      - alert: CertificateExpiring
        expr: certmanager_certificate_expiration_timestamp_seconds - time() < 14 * 86400
        for: 1h
        annotations:
          summary: "Certificate {{ $labels.name }} expires soon"
          description: "Certificate expires in {{ $value | humanizeDuration }}"
```

## 5. Ручная ротация корпоративных CA

### Процедура обновления Intermediate CA

```bash
#!/bin/bash
# Генерация CSR для нового Intermediate CA
openssl req -new -key intermediate-new.key \
  -out intermediate-new.csr \
  -config intermediate.conf

# После подписания корпоративным Root CA (вне кластера)
# Создание bundle с цепочкой сертификатов
cat intermediate-new.crt corporate-root.crt > intermediate-chain.pem

# Кодирование для Kubernetes
CERT_CHAIN=$(cat intermediate-chain.pem | base64 -w0)
KEY=$(cat intermediate-new.key | base64 -w0)

# Создание нового секрета
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: corp-intermediate-ca-new
  namespace: d8-cert-manager
type: kubernetes.io/tls
data:
  tls.crt: ${CERT_CHAIN}
  tls.key: ${KEY}
EOF
```

### Плавная миграция на новый CA

```yaml
# 1. Создание нового ClusterIssuer
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: corp-ca-issuer-new
spec:
  ca:
    secretName: corp-intermediate-ca-new
---
# 2. Постепенное обновление сертификатов
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: app-tls
  annotations:
    cert-manager.io/revision-history-limit: "5"
spec:
  issuerRef:
    name: corp-ca-issuer-new  # переключение на новый issuer
    kind: ClusterIssuer
```

## 6. Интеграция с компонентами Deckhouse

### Настройка глобальных параметров

Для выпуска сертификатов для всех компонентов Deckhouse, укажите имя ClusterIssuer в глобальном параметре ClusterIssuerName:

```yaml
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: global
spec:
  settings:
    modules:
      https:
        certManager:
          clusterIssuerName: corp-ca-issuer
        mode: CertManager
        publicDomainTemplate: '%s.corp.local'
```

### Настройка для изолированного окружения

При использовании самоподписанных сертификатов необходимо указать корневой CA сертификат для валидации HTTPS сертификата реестра:

```yaml
apiVersion: deckhouse.io/v1
kind: InitConfiguration
deckhouse:
  registryCA: |
    -----BEGIN CERTIFICATE-----
    <Корпоративный Root CA сертификат>
    -----END CERTIFICATE-----
```

## 7. Резервное копирование и восстановление

### Автоматическое резервирование

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cert-backup
  namespace: d8-cert-manager
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: registry.deckhouse.io/deckhouse/ce/tools:v1.0.0
            command:
            - /bin/sh
            - -c
            - |
              kubectl get secret -n d8-cert-manager \
                -l cert-manager.io/certificate=true \
                -o yaml > /backup/certs-$(date +%Y%m%d).yaml
              
              # Шифрование и отправка в корпоративное хранилище
              gpg --encrypt --recipient backup@corp.local \
                /backup/certs-$(date +%Y%m%d).yaml
          restartPolicy: OnFailure
```

## 8. Best Practices для изолированного окружения

### Сроки действия сертификатов
- **Корпоративный Root CA**: 10-20 лет (хранится офлайн)
- **Intermediate CA**: 5 лет
- **Сервисные сертификаты**: 1 год
- **Ingress сертификаты**: 90 дней

### Контрольный список безопасности
1. Хранить Root CA офлайн, вне кластера
2. Использовать отдельные Intermediate CA для разных целей
3. Регулярно ротировать сертификаты приложений
4. Мониторить сроки действия всех сертификатов
5. Вести аудит всех операций с сертификатами
6. Хранить резервные копии в зашифрованном виде

### Процедура аварийного восстановления
```bash
# В случае компрометации Intermediate CA
1. Отозвать скомпрометированный CA в корпоративной PKI
2. Создать новый Intermediate CA офлайн
3. Импортировать новый CA в кластер
4. Переиздать все активные сертификаты
5. Обновить trust store во всех приложениях
```

Эта стратегия обеспечивает надежное управление сертификатами в Deckhouse при полной изоляции от внешних сервисов и невозможности автоматического выпуска корпоративных сертификатов через API.
