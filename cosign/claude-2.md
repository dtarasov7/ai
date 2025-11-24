# Notation в изолированной сети: Детальная процедура

Отличный выбор Notation для корпоративного окружения с PKI. Разберем полный процесс.

## Архитектура решения

```
┌────────────────────────────────────────────────────────────┐
│  Поставщик (внешняя сеть)                                  │
├────────────────────────────────────────────────────────────┤
│  1. Подписывает образ своим сертификатом                   │
│  2. Экспортирует образ + подпись как OCI layout            │
│  3. Передает: tar-архив + сертификат CA (один раз)         │
└────────────────────────────────────────────────────────────┘
                          │
                          │ Физическая передача
                          ↓
┌────────────────────────────────────────────────────────────┐
│  Входной контроль (DMZ / Staging)                          │
├────────────────────────────────────────────────────────────┤
│  1. Автоматическая загрузка в staging registry             │
│  2. Автоматическая верификация подписи                     │
│  3. Автоматическое сканирование уязвимостей                │
│  4. Генерация отчета для ручного review                    │
└────────────────────────────────────────────────────────────┘
                          │
                          ↓ (После одобрения)
┌────────────────────────────────────────────────────────────┐
│  Production Nexus Repository                               │
├────────────────────────────────────────────────────────────┤
│  - Только верифицированные образы                          │
│  - Подписи сохранены как OCI artifacts                     │
│  - Готовы к deployment                                     │
└────────────────────────────────────────────────────────────┘
```

## Часть 1: Подготовка у поставщика

### 1.1. Поставщик создает подписанный пакет

```bash
#!/bin/bash
# supplier-package.sh

set -e

IMAGE="supplier.io/myapp:v1.0"
OUTPUT_DIR="delivery-$(date +%Y%m%d-%H%M%S)"

echo "=== Создание delivery package для $IMAGE ==="

mkdir -p "$OUTPUT_DIR"

# 1. Подпись образа
echo "[1/5] Подпись образа..."
notation sign \
  --signature-format jws \
  --key supplier-signing.crt \
  "$IMAGE"

# 2. Экспорт образа + подписи через ORAS/Crane
# Важно: используем OCI layout для сохранения всех artifacts
echo "[2/5] Экспорт OCI layout..."
oras pull "$IMAGE" --output "$OUTPUT_DIR/oci-layout" --format oci-layout

# Альтернативно через crane:
# crane pull "$IMAGE" "$OUTPUT_DIR/oci-layout.tar"

# 3. Создание архива
echo "[3/5] Создание tar архива..."
tar czf "$OUTPUT_DIR.tar.gz" -C "$OUTPUT_DIR" .

# 4. Создание манифеста
echo "[4/5] Создание манифеста..."
cat > "$OUTPUT_DIR/manifest.json" <<EOF
{
  "image": "$IMAGE",
  "version": "v1.0",
  "digest": "$(crane digest $IMAGE)",
  "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "supplier": {
    "name": "Trusted Supplier Corp",
    "contact": "security@supplier.io",
    "certificate_cn": "CN=Supplier Signing Key"
  },
  "signature": {
    "format": "jws",
    "algorithm": "RS256",
    "cert_chain_included": true
  },
  "contents": [
    "oci-layout/",
    "manifest.json",
    "verification-guide.md"
  ]
}
EOF

# 5. Создание инструкции по верификации
cat > "$OUTPUT_DIR/verification-guide.md" <<'EOF'
# Инструкция по верификации образа

## 1. Распаковка пакета
```bash
tar xzf delivery-*.tar.gz
cd delivery-*/
```

## 2. Загрузка образа в локальный registry
```bash
# Через ORAS
oras push your-registry.local/supplier/myapp:v1.0 \
  --from-oci-layout oci-layout/

# Или через crane
crane push oci-layout.tar your-registry.local/supplier/myapp:v1.0
```

## 3. Верификация подписи
```bash
notation verify \
  --allow-referrers-api \
  your-registry.local/supplier/myapp:v1.0
```

## Требования
- Сертификат CA поставщика должен быть установлен в trust store
- Trust policy должна разрешать подписи от поставщика
EOF

# 6. Генерация checksums
echo "[5/5] Создание checksums..."
cd "$OUTPUT_DIR"
find . -type f -exec sha256sum {} \; | sort > SHA256SUMS
cd ..

# 7. Финальная упаковка
tar czf "$OUTPUT_DIR-complete.tar.gz" "$OUTPUT_DIR"

echo "✓ Пакет создан: $OUTPUT_DIR-complete.tar.gz"
echo "✓ Содержимое:"
tar tzf "$OUTPUT_DIR-complete.tar.gz" | head -20
```

### 1.2. Что передается (один раз при первой поставке)

```
supplier-ca-certificate.crt   # Root CA сертификат поставщика
supplier-signing.crt          # Signing сертификат (публичный)
trust-policy-template.json    # Рекомендуемая trust policy
```

## Часть 2: Настройка в изолированной сети

### 2.1. Установка сертификатов поставщика (один раз)

```bash
#!/bin/bash
# setup-supplier-trust.sh

SUPPLIER_NAME="trusted-supplier"
SUPPLIER_CA_CERT="supplier-ca-certificate.crt"

# 1. Добавление CA сертификата в Notation trust store
notation cert add \
  --type ca \
  --store "$SUPPLIER_NAME" \
  "$SUPPLIER_CA_CERT"

# Проверка установки
notation cert list

# Вывод:
# STORE TYPE    STORE NAME           CERTIFICATE
# ca            trusted-supplier     CN=Supplier Root CA
```

### 2.2. Создание Trust Policy

```bash
# /etc/notation/trustpolicy.json или ~/.config/notation/trustpolicy.json
cat > ~/.config/notation/trustpolicy.json <<'EOF'
{
  "version": "1.0",
  "trustPolicies": [
    {
      "name": "trusted-supplier-policy",
      "registryScopes": [
        "nexus.internal.company:8443/supplier/*"
      ],
      "signatureVerification": {
        "level": "strict",
        "override": {}
      },
      "trustStores": ["ca:trusted-supplier"],
      "trustedIdentities": [
        "x509.subject: CN=Supplier Signing Key, O=Trusted Supplier Corp, C=US"
      ]
    },
    {
      "name": "staging-verification",
      "registryScopes": [
        "staging-registry.internal:5000/*"
      ],
      "signatureVerification": {
        "level": "strict"
      },
      "trustStores": ["ca:trusted-supplier"],
      "trustedIdentities": [
        "x509.subject: CN=Supplier Signing Key, O=Trusted Supplier Corp, C=US"
      ]
    }
  ]
}
EOF

# Валидация trust policy
notation policy show
```

### 2.3. Настройка Nexus для OCI artifacts

```bash
# Nexus должен поддерживать OCI artifacts (Docker registry format v2)
# В Nexus Repository Manager 3:

# 1. Создать Docker (hosted) repository
#    Name: supplier-staging
#    HTTP port: 5001
#    Allow anonymous docker pull: No
#    Enable Docker V1 API: No (важно!)

# 2. Создать Docker (hosted) repository для production
#    Name: supplier-production  
#    HTTP port: 8443
#    Allow anonymous docker pull: No

# 3. Включить поддержку OCI artifacts
#    В nexus.properties добавить:
#    nexus.docker.oci.enabled=true
```

## Часть 3: Автоматизированная верификация

### 3.1. Скрипт автоматической обработки поступающих образов

```bash
#!/bin/bash
# auto-verify-supplier-image.sh

set -e

# Конфигурация
DELIVERY_PACKAGE="$1"
STAGING_REGISTRY="staging-registry.internal:5000"
PROD_REGISTRY="nexus.internal.company:8443"
REPORT_DIR="/var/log/image-verification"
SUPPLIER_NAME="trusted-supplier"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

if [ -z "$DELIVERY_PACKAGE" ]; then
    error "Usage: $0 <delivery-package.tar.gz>"
    exit 1
fi

# Создание рабочей директории
WORK_DIR=$(mktemp -d)
trap "rm -rf $WORK_DIR" EXIT

PACKAGE_NAME=$(basename "$DELIVERY_PACKAGE" .tar.gz)
REPORT_FILE="$REPORT_DIR/${PACKAGE_NAME}-$(date +%Y%m%d-%H%M%S).json"

mkdir -p "$REPORT_DIR"

log "=== Начало обработки: $DELIVERY_PACKAGE ==="
log "Рабочая директория: $WORK_DIR"

# ============================================================
# Этап 1: Распаковка и проверка целостности
# ============================================================
log "[1/7] Распаковка пакета..."
tar xzf "$DELIVERY_PACKAGE" -C "$WORK_DIR"

log "[1/7] Проверка checksums..."
cd "$WORK_DIR"/*/ || exit 1
PACKAGE_DIR=$(pwd)

if [ -f SHA256SUMS ]; then
    if sha256sum -c SHA256SUMS --quiet; then
        log "✓ Checksums verified"
        CHECKSUM_STATUS="passed"
    else
        error "✗ Checksum verification failed!"
        CHECKSUM_STATUS="failed"
        # Не выходим, продолжаем для полного отчета
    fi
else
    warn "SHA256SUMS not found, skipping checksum verification"
    CHECKSUM_STATUS="skipped"
fi

# ============================================================
# Этап 2: Загрузка в staging registry
# ============================================================
log "[2/7] Загрузка образа в staging registry..."

# Чтение манифеста
if [ ! -f manifest.json ]; then
    error "manifest.json not found in package"
    exit 1
fi

IMAGE_NAME=$(jq -r '.image' manifest.json)
IMAGE_VERSION=$(jq -r '.version' manifest.json)
EXPECTED_DIGEST=$(jq -r '.digest' manifest.json)

STAGING_IMAGE="$STAGING_REGISTRY/$SUPPLIER_NAME/$(basename $IMAGE_NAME)"

log "Образ: $IMAGE_NAME"
log "Версия: $IMAGE_VERSION"
log "Ожидаемый digest: $EXPECTED_DIGEST"

# Загрузка через ORAS (сохраняет все OCI artifacts включая подписи)
if [ -d "oci-layout" ]; then
    log "Загрузка OCI layout..."
    
    # Используем oras для push с сохранением всех artifacts
    oras copy \
        --from-oci-layout "oci-layout/:${IMAGE_VERSION}" \
        --to "$STAGING_IMAGE:${IMAGE_VERSION}"
    
    LOAD_STATUS="success"
    ACTUAL_DIGEST=$(crane digest "$STAGING_IMAGE:${IMAGE_VERSION}")
    
    log "Загружен digest: $ACTUAL_DIGEST"
    
    # Проверка соответствия digest
    if [ "$ACTUAL_DIGEST" != "$EXPECTED_DIGEST" ]; then
        error "✗ Digest mismatch!"
        error "  Expected: $EXPECTED_DIGEST"
        error "  Got:      $ACTUAL_DIGEST"
        DIGEST_MATCH="failed"
    else
        log "✓ Digest verified"
        DIGEST_MATCH="passed"
    fi
else
    error "oci-layout directory not found"
    LOAD_STATUS="failed"
    exit 1
fi

# ============================================================
# Этап 3: Верификация подписи Notation
# ============================================================
log "[3/7] Верификация подписи Notation..."

VERIFY_OUTPUT=$(mktemp)
VERIFY_STATUS="failed"

if notation verify \
    --allow-referrers-api \
    "$STAGING_IMAGE:${IMAGE_VERSION}" \
    2>&1 | tee "$VERIFY_OUTPUT"; then
    
    log "✓ Signature verification PASSED"
    VERIFY_STATUS="passed"
    
    # Извлечение информации о подписи
    SIGNATURE_INFO=$(notation inspect "$STAGING_IMAGE:${IMAGE_VERSION}" 2>/dev/null || echo "{}")
    
else
    error "✗ Signature verification FAILED"
    VERIFY_STATUS="failed"
    SIGNATURE_INFO="{}"
fi

# Извлечение деталей сертификата
CERT_SUBJECT=$(grep "subject:" "$VERIFY_OUTPUT" | cut -d: -f2- | xargs || echo "unknown")
CERT_ISSUER=$(grep "issuer:" "$VERIFY_OUTPUT" | cut -d: -f2- | xargs || echo "unknown")

log "Certificate Subject: $CERT_SUBJECT"
log "Certificate Issuer: $CERT_ISSUER"

# ============================================================
# Этап 4: Сканирование уязвимостей
# ============================================================
log "[4/7] Сканирование уязвимостей (Trivy)..."

SCAN_OUTPUT="$WORK_DIR/trivy-scan.json"
SCAN_STATUS="unknown"

if command -v trivy &> /dev/null; then
    trivy image \
        --format json \
        --output "$SCAN_OUTPUT" \
        --severity HIGH,CRITICAL \
        "$STAGING_IMAGE:${IMAGE_VERSION}"
    
    CRITICAL_COUNT=$(jq '[.Results[].Vulnerabilities[] | select(.Severity=="CRITICAL")] | length' "$SCAN_OUTPUT")
    HIGH_COUNT=$(jq '[.Results[].Vulnerabilities[] | select(.Severity=="HIGH")] | length' "$SCAN_OUTPUT")
    
    log "Найдено уязвимостей: CRITICAL=$CRITICAL_COUNT, HIGH=$HIGH_COUNT"
    
    if [ "$CRITICAL_COUNT" -eq 0 ] && [ "$HIGH_COUNT" -eq 0 ]; then
        SCAN_STATUS="passed"
        log "✓ No critical or high vulnerabilities found"
    elif [ "$CRITICAL_COUNT" -eq 0 ]; then
        SCAN_STATUS="warning"
        warn "Found $HIGH_COUNT high severity vulnerabilities"
    else
        SCAN_STATUS="failed"
        error "Found $CRITICAL_COUNT critical vulnerabilities"
    fi
else
    warn "Trivy not installed, skipping vulnerability scan"
    SCAN_STATUS="skipped"
    CRITICAL_COUNT=0
    HIGH_COUNT=0
fi

# ============================================================
# Этап 5: Проверка SBOM (если есть)
# ============================================================
log "[5/7] Проверка SBOM..."

SBOM_STATUS="not_found"
SBOM_DATA="{}"

# Попытка получить SBOM если он прикреплен к образу
if oras discover "$STAGING_IMAGE:${IMAGE_VERSION}" --artifact-type application/spdx+json 2>/dev/null | grep -q "application/spdx+json"; then
    log "SBOM найден, извлекаем..."
    
    SBOM_FILE="$WORK_DIR/sbom.json"
    oras pull "$STAGING_IMAGE:${IMAGE_VERSION}" \
        --artifact-type application/spdx+json \
        --output "$SBOM_FILE" || true
    
    if [ -f "$SBOM_FILE" ]; then
        SBOM_STATUS="found"
        SBOM_DATA=$(cat "$SBOM_FILE")
        log "✓ SBOM extracted"
    fi
else
    log "SBOM не найден (не критично)"
fi

# ============================================================
# Этап 6: Генерация отчета
# ============================================================
log "[6/7] Генерация отчета..."

cat > "$REPORT_FILE" <<EOF
{
  "verification_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "package": {
    "name": "$PACKAGE_NAME",
    "path": "$DELIVERY_PACKAGE",
    "checksum_verification": "$CHECKSUM_STATUS"
  },
  "image": {
    "original": "$IMAGE_NAME",
    "staging": "$STAGING_IMAGE:${IMAGE_VERSION}",
    "version": "$IMAGE_VERSION",
    "expected_digest": "$EXPECTED_DIGEST",
    "actual_digest": "$ACTUAL_DIGEST",
    "digest_match": "$DIGEST_MATCH"
  },
  "signature": {
    "verification_status": "$VERIFY_STATUS",
    "certificate_subject": "$CERT_SUBJECT",
    "certificate_issuer": "$CERT_ISSUER",
    "trust_policy": "trusted-supplier-policy"
  },
  "security_scan": {
    "status": "$SCAN_STATUS",
    "critical_vulnerabilities": $CRITICAL_COUNT,
    "high_vulnerabilities": $HIGH_COUNT,
    "scan_report": "$(basename $SCAN_OUTPUT)"
  },
  "sbom": {
    "status": "$SBOM_STATUS"
  },
  "overall_status": "$(
    if [ "$VERIFY_STATUS" = "passed" ] && [ "$DIGEST_MATCH" = "passed" ] && [ "$CHECKSUM_STATUS" != "failed" ]; then
        if [ "$SCAN_STATUS" = "failed" ]; then
            echo "requires_review"
        else
            echo "approved"
        fi
    else
        echo "rejected"
    fi
  )",
  "recommendation": "$(
    if [ "$VERIFY_STATUS" = "passed" ] && [ "$DIGEST_MATCH" = "passed" ]; then
        if [ "$CRITICAL_COUNT" -gt 0 ]; then
            echo "Manual review required due to critical vulnerabilities"
        elif [ "$HIGH_COUNT" -gt 5 ]; then
            echo "Manual review recommended due to multiple high vulnerabilities"
        else
            echo "Approved for production deployment"
        fi
    else
        echo "Rejected: Signature or digest verification failed"
    fi
  )"
}
EOF

log "Отчет сохранен: $REPORT_FILE"

# Красивый вывод отчета
log "=== Итоговый отчет ==="
jq '.' "$REPORT_FILE"

# ============================================================
# Этап 7: Решение о принятии
# ============================================================
log "[7/7] Принятие решения..."

OVERALL_STATUS=$(jq -r '.overall_status' "$REPORT_FILE")

case "$OVERALL_STATUS" in
    "approved")
        log "${GREEN}✓ ОБРАЗ ОДОБРЕН для автоматического продвижения${NC}"
        
        # Автоматическое продвижение в production
        log "Копирование в production registry..."
        
        PROD_IMAGE="$PROD_REGISTRY/$SUPPLIER_NAME/$(basename $IMAGE_NAME):${IMAGE_VERSION}"
        
        # Копируем образ со всеми подписями
        oras copy \
            "$STAGING_IMAGE:${IMAGE_VERSION}" \
            "$PROD_IMAGE"
        
        log "✓ Образ доступен в production: $PROD_IMAGE"
        
        # Добавление тега latest если это новейшая версия
        crane tag "$PROD_IMAGE" latest
        
        exit 0
        ;;
        
    "requires_review")
        warn "⚠ ТРЕБУЕТСЯ РУЧНОЙ REVIEW"
        warn "Причина: Обнаружены уязвимости или другие предупреждения"
        warn "Отчет: $REPORT_FILE"
        warn "Образ в staging: $STAGING_IMAGE:${IMAGE_VERSION}"
        warn ""
        warn "Для одобрения выполните:"
        warn "  ./approve-image.sh '$STAGING_IMAGE:${IMAGE_VERSION}'"
        
        exit 2
        ;;
        
    "rejected")
        error "✗ ОБРАЗ ОТКЛОНЕН"
        error "Причина: Не прошла верификация подписи или digest"
        error "Отчет: $REPORT_FILE"
        error "Образ НЕ будет перемещен в production"
        
        exit 1
        ;;
esac
```

### 3.2. Скрипт ручного одобрения (для requires_review)

```bash
#!/bin/bash
# approve-image.sh

set -e

STAGING_IMAGE="$1"
PROD_REGISTRY="nexus.internal.company:8443"
SUPPLIER_NAME="trusted-supplier"

if [ -z "$STAGING_IMAGE" ]; then
    echo "Usage: $0 <staging-image>"
    exit 1
fi

echo "=== Ручное одобрение образа ==="
echo "Образ: $STAGING_IMAGE"
echo ""

# Показываем последний отчет
LATEST_REPORT=$(ls -t /var/log/image-verification/*.json | head -1)
echo "Последний отчет:"
jq '{image, signature, security_scan, recommendation}' "$LATEST_REPORT"
echo ""

read -p "Одобрить образ для production? (yes/no): " APPROVAL

if [ "$APPROVAL" != "yes" ]; then
    echo "Отменено"
    exit 0
fi

# Запрос причины одобрения
read -p "Причина одобрения (комментарий): " APPROVAL_REASON

echo "Копирование в production..."

# Извлекаем имя и версию
IMAGE_BASE=$(echo "$STAGING_IMAGE" | cut -d'/' -f2- | cut -d':' -f1)
IMAGE_TAG=$(echo "$STAGING_IMAGE" | cut -d':' -f2)

PROD_IMAGE="$PROD_REGISTRY/$SUPPLIER_NAME/$IMAGE_BASE:$IMAGE_TAG"

# Копирование
oras copy "$STAGING_IMAGE" "$PROD_IMAGE"

# Логирование одобрения
APPROVAL_LOG="/var/log/image-verification/approvals.log"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)|$USER|$STAGING_IMAGE|$PROD_IMAGE|$APPROVAL_REASON" >> "$APPROVAL_LOG"

echo "✓ Образ одобрен и скопирован в production: $PROD_IMAGE"
```

### 3.3. Systemd service для автоматической обработки

```bash
# /etc/systemd/system/image-verifier@.service
[Unit]
Description=Automatic Image Verification for %I
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/auto-verify-supplier-image.sh /var/incoming/%I
User=image-verifier
Group=docker
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# /etc/systemd/system/image-verifier.path
[Unit]
Description=Watch for new supplier images

[Path]
PathChanged=/var/incoming
Unit=image-verifier@%f.service

[Install]
WantedBy=multi-user.target
```

Активация:
```bash
systemctl enable image-verifier.path
systemctl start image-verifier.path

# Теперь любой .tar.gz файл в /var/incoming автоматически обработается
```

## Часть 4: Dashboard для мониторинга

### 4.1. Web-интерфейс для просмотра статуса
