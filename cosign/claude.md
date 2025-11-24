# Проверка подписанных образов в изолированной сети

Отличный вопрос! Это классический сценарий **air-gapped** окружения. Разберем детально, как работать с подписями в такой ситуации.

## Проблема: Подпись хранится отдельно от tar-архива

### Что происходит при обычной работе:

```bash
# Поставщик подписывает образ
cosign sign --key supplier.key supplier.io/app:v1.0

# Подпись сохраняется в registry как отдельный OCI artifact:
supplier.io/app:v1.0                    # Сам образ
supplier.io/app:sha256-abc123.sig       # Подпись (отдельный манифест)
```

### Что вы получаете в tar-файле:

```bash
# Поставщик экспортирует образ
docker save supplier.io/app:v1.0 -o app.tar

# В app.tar НЕТ подписи!
# Подпись живет отдельно в registry
```

## Решение 1: Bundle — самодостаточная подпись

Cosign поддерживает **bundle** — JSON-файл, содержащий всю информацию для оффлайн-верификации.

### У поставщика (с доступом к интернету):

```bash
# 1. Подписываем образ с созданием bundle
cosign sign --key supplier.key \
  --bundle signature-bundle.json \
  supplier.io/app:v1.0

# 2. Экспортируем образ
docker save supplier.io/app:v1.0 -o app.tar

# 3. Передаем ВАМ оба файла:
#    - app.tar (образ)
#    - signature-bundle.json (подпись + метаданные)
```

### Структура bundle:

```json
{
  "SignedEntryTimestamp": "MEUCIQ...",
  "Payload": {
    "body": "eyJhcGlWZXJzaW9uIjoiMC4wLjEiLCJr...",
    "integratedTime": 1698249600,
    "logIndex": 12345678,
    "logID": "c0d23d6ad406973f9..."
  },
  "base64Signature": "MEQCIH8Q7qYNe...",
  "cert": "-----BEGIN CERTIFICATE-----\nMIIC..."
}
```

### У вас (в изолированной сети):

```bash
# 1. Загружаем образ в локальный registry (Nexus)
docker load -i app.tar
docker tag supplier.io/app:v1.0 nexus.local:8443/supplier/app:v1.0
docker push nexus.local:8443/supplier/app:v1.0

# 2. Верифицируем с bundle (оффлайн!)
cosign verify --key supplier.pub \
  --bundle signature-bundle.json \
  --insecure-ignore-tlog \
  nexus.local:8443/supplier/app:v1.0
```

**Важно:** `--insecure-ignore-tlog` отключает проверку Rekor (transparency log), т.к. нет доступа к интернету.

## Решение 2: Attach signature к образу перед экспортом

Более элегантный способ — **прикрепить подпись к образу** перед созданием tar.

### У поставщика:

```bash
# 1. Подписываем образ (подпись уходит в registry)
cosign sign --key supplier.key supplier.io/app:v1.0

# 2. Получаем digest образа
IMAGE_DIGEST=$(docker inspect supplier.io/app:v1.0 \
  --format='{{index .RepoDigests 0}}')
# Результат: supplier.io/app@sha256:abc123...

# 3. Получаем имя signature artifact
SIGNATURE_REF=$(cosign triangulate $IMAGE_DIGEST)
# Результат: supplier.io/app:sha256-abc123.sig

# 4. Экспортируем ОБА артефакта
docker save $IMAGE_DIGEST -o app-image.tar
docker save $SIGNATURE_REF -o app-signature.tar

# 5. Можно объединить в один архив
tar czf app-complete.tar.gz app-image.tar app-signature.tar supplier.pub
```

### Структура передаваемого пакета:

```
app-complete.tar.gz
├── app-image.tar          # Сам образ
├── app-signature.tar      # OCI artifact с подписью
├── supplier.pub           # Публичный ключ (для удобства)
└── manifest.json          # Опционально: метаданные
```

### У вас (в изолированной сети):

```bash
# 1. Распаковываем
tar xzf app-complete.tar.gz

# 2. Загружаем образ в локальный Nexus
docker load -i app-image.tar
# Loaded: supplier.io/app@sha256:abc123...

# 3. Загружаем подпись
docker load -i app-signature.tar
# Loaded: supplier.io/app:sha256-abc123.sig

# 4. Тегируем и пушим в Nexus оба артефакта
NEXUS_REGISTRY="nexus.local:8443"

# Образ
docker tag supplier.io/app@sha256:abc123... \
  $NEXUS_REGISTRY/supplier/app:v1.0
docker push $NEXUS_REGISTRY/supplier/app:v1.0

# Подпись
docker tag supplier.io/app:sha256-abc123.sig \
  $NEXUS_REGISTRY/supplier/app:sha256-abc123.sig
docker push $NEXUS_REGISTRY/supplier/app:sha256-abc123.sig

# 5. Верифицируем через Nexus
cosign verify --key supplier.pub \
  --insecure-ignore-tlog \
  $NEXUS_REGISTRY/supplier/app:v1.0
```

## Решение 3: Crane для работы с OCI artifacts

Cosign основан на **crane** — инструменте для манипуляций с OCI artifacts.

### У поставщика:

```bash
# Установка crane
go install github.com/google/go-containerregistry/cmd/crane@latest

# 1. Подписываем образ
cosign sign --key supplier.key supplier.io/app:v1.0

# 2. Экспортируем образ + все связанные артефакты
crane pull supplier.io/app:v1.0 app-v1.0.tar

# Это создаст tar с полным OCI layout, включая подписи!
```

### Структура OCI layout tar:

```
app-v1.0.tar
├── blobs/
│   ├── sha256/abc123...  # Layers образа
│   ├── sha256/def456...  # Config
│   └── sha256/ghi789...  # Signature manifest
├── index.json            # OCI index
└── oci-layout           # Спецификация формата
```

### У вас:

```bash
# 1. Загружаем в Nexus
crane push app-v1.0.tar nexus.local:8443/supplier/app:v1.0

# 2. Верифицируем
cosign verify --key supplier.pub \
  --insecure-ignore-tlog \
  nexus.local:8443/supplier/app:v1.0
```

## Решение 4: Ручная процедура проверки

Если автоматизация невозможна, можно создать процедуру ручной проверки.

### Процедура для службы безопасности:

```bash
#!/bin/bash
# check-supplier-image.sh

set -e

IMAGE_TAR=$1
BUNDLE_JSON=$2
SUPPLIER_PUB=$3
NEXUS_REGISTRY="nexus.local:8443"

echo "=== Проверка образа от поставщика ==="

# 1. Загружаем образ локально
echo "[1/5] Загрузка образа..."
IMAGE_ID=$(docker load -i "$IMAGE_TAR" | grep -oP 'Loaded image: \K.*')
echo "Загружен: $IMAGE_ID"

# 2. Получаем digest
echo "[2/5] Вычисление digest..."
DIGEST=$(docker inspect "$IMAGE_ID" --format='{{.Id}}')
echo "Digest: $DIGEST"

# 3. Верифицируем подпись через bundle
echo "[3/5] Проверка подписи..."
docker tag "$IMAGE_ID" temp-verify:latest

if cosign verify --key "$SUPPLIER_PUB" \
   --bundle "$BUNDLE_JSON" \
   --insecure-ignore-tlog \
   temp-verify:latest; then
    echo "✓ Подпись валидна"
else
    echo "✗ Подпись невалидна!"
    docker rmi temp-verify:latest
    exit 1
fi

# 4. Сканирование уязвимостей (опционально)
echo "[4/5] Сканирование уязвимостей..."
trivy image --severity HIGH,CRITICAL temp-verify:latest

# 5. Загрузка в Nexus
echo "[5/5] Загрузка в Nexus..."
read -p "Загрузить в Nexus? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    NEXUS_IMAGE="$NEXUS_REGISTRY/approved/$(basename $IMAGE_ID)"
    docker tag temp-verify:latest "$NEXUS_IMAGE"
    docker push "$NEXUS_IMAGE"
    echo "✓ Загружено: $NEXUS_IMAGE"
fi

docker rmi temp-verify:latest
echo "=== Проверка завершена ==="
```

### Использование:

```bash
chmod +x check-supplier-image.sh

./check-supplier-image.sh \
  supplier-app-v1.0.tar \
  signature-bundle.json \
  supplier.pub
```

## Решение 5: Cosign-образ с заранее подготовленными данными

### У поставщика — подготовка полного пакета:

```bash
# Скрипт у поставщика
#!/bin/bash

APP_IMAGE="supplier.io/app:v1.0"
OUTPUT_DIR="delivery-package"

mkdir -p "$OUTPUT_DIR"

# 1. Подписываем с bundle
cosign sign --key supplier.key \
  --bundle "$OUTPUT_DIR/signature.bundle" \
  "$APP_IMAGE"

# 2. Экспортируем образ
docker save "$APP_IMAGE" -o "$OUTPUT_DIR/image.tar"

# 3. Копируем публичный ключ
cp supplier.pub "$OUTPUT_DIR/"

# 4. Создаем манифест
cat > "$OUTPUT_DIR/manifest.json" <<EOF
{
  "image": "$APP_IMAGE",
  "digest": "$(docker inspect $APP_IMAGE --format='{{.Id}}')",
  "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "supplier": "Trusted Supplier Inc.",
  "version": "1.0",
  "signature_algorithm": "ECDSA-P256-SHA256"
}
EOF

# 5. Создаем README с инструкциями
cat > "$OUTPUT_DIR/README.md" <<'EOF'
# Инструкция по проверке и загрузке

## 1. Проверка целостности пакета
sha256sum -c checksums.txt

## 2. Загрузка образа
docker load -i image.tar

## 3. Верификация подписи
cosign verify --key supplier.pub \
  --bundle signature.bundle \
  --insecure-ignore-tlog \
  <IMAGE_NAME>

## 4. Загрузка в Nexus
docker tag <IMAGE_NAME> nexus.local:8443/approved/<IMAGE_NAME>
docker push nexus.local:8443/approved/<IMAGE_NAME>
EOF

# 6. Создаем checksums
cd "$OUTPUT_DIR"
sha256sum * > checksums.txt
cd ..

# 7. Архивируем
tar czf "app-v1.0-signed.tar.gz" "$OUTPUT_DIR"

echo "Пакет готов: app-v1.0-signed.tar.gz"
```

### У вас — процедура приемки:

```bash
# 1. Распаковка
tar xzf app-v1.0-signed.tar.gz
cd delivery-package

# 2. Проверка целостности пакета
sha256sum -c checksums.txt

# 3. Следование инструкциям в README.md
cat README.md

# 4. Автоматизированная проверка
docker load -i image.tar
IMAGE_NAME=$(docker images --format "{{.Repository}}:{{.Tag}}" | head -1)

cosign verify --key supplier.pub \
  --bundle signature.bundle \
  --insecure-ignore-tlog \
  "$IMAGE_NAME"
```

## Важные особенности для air-gapped окружения

### 1. Настройка Nexus для OCI artifacts

Nexus должен поддерживать OCI artifacts (не только Docker images):

```yaml
# Nexus Docker Registry configuration
# Включить поддержку OCI artifacts
apiVersion: v1
repositories:
  docker-hosted:
    name: docker-internal
    type: docker-hosted
    docker:
      v1Enabled: false
      forceBasicAuth: true
      httpPort: 8443
      httpsPort: null
    storage:
      blobStoreName: default
      strictContentTypeValidation: true
      writePolicy: ALLOW
```

### 2. Конфигурация Cosign для работы без интернета

```bash
# Создайте конфиг для Cosign
mkdir -p ~/.cosign
cat > ~/.cosign/config.yaml <<EOF
# Отключаем все внешние вызовы
rekor-url: ""
fulcio-url: ""
tsa-url: ""

# Локальные настройки
registry-verification:
  insecure-registries:
    - "nexus.local:8443"
  allowed-registries:
    - "nexus.local:8443"
EOF

# Экспорт переменных
export COSIGN_REPOSITORY="nexus.local:8443"
export COSIGN_EXPERIMENTAL=0  # Отключить keyless
```

### 3. Верификация без Rekor

```bash
# Всегда используйте --insecure-ignore-tlog
cosign verify --key supplier.pub \
  --insecure-ignore-tlog \
  nexus.local:8443/supplier/app:v1.0

# Или через переменную окружения
export COSIGN_EXPERIMENTAL=0
cosign verify --key supplier.pub nexus.local:8443/supplier/app:v1.0
```

## Рекомендуемый workflow для вашего сценария

```
┌─────────────────────────────────────────────────────────────┐
│  Поставщик (с интернетом)                                   │
├─────────────────────────────────────────────────────────────┤
│  1. docker build -t supplier.io/app:v1.0 .                  │
│  2. docker push supplier.io/app:v1.0                        │
│  3. cosign sign --key supplier.key \                        │
│       --bundle signature.bundle \                           │
│       supplier.io/app:v1.0                                  │
│  4. docker save supplier.io/app:v1.0 -o image.tar          │
│  5. Создание delivery-package:                              │
│     ├── image.tar                                           │
│     ├── signature.bundle                                    │
│     ├── supplier.pub (опционально, уже передан)            │
│     ├── manifest.json                                       │
│     └── README.md                                           │
│  6. tar czf app-v1.0-delivery.tar.gz delivery-package/     │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ Физическая передача
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Ваша изолированная сеть                                    │
├─────────────────────────────────────────────────────────────┤
│  1. tar xzf app-v1.0-delivery.tar.gz                        │
│  2. sha256sum -c checksums.txt  # Проверка целостности     │
│  3. docker load -i image.tar                                │
│  4. cosign verify --key supplier.pub \                      │
│       --bundle signature.bundle \                           │
│       --insecure-ignore-tlog \                              │
│       <loaded-image>                                        │
│  5. trivy image <loaded-image>  # Сканирование             │
│  6. Ручная проверка (если требуется)                       │
│  7. docker tag <loaded-image> \                             │
│       nexus.local:8443/approved/app:v1.0                   │
│  8. docker push nexus.local:8443/approved/app:v1.0         │
└─────────────────────────────────────────────────────────────┘
```

## Альтернатива: Notary v2 (Notation)

Если Cosign создает проблемы, рассмотрите **Notation** — альтернативный инструмент подписи:

```bash
# У поставщика
notation sign --key supplier.key supplier.io/app:v1.0
notation export --signature supplier.io/app:v1.0 -o signature.json

# У вас
notation import signature.json
notation verify --cert supplier.crt nexus.local:8443/app:v1.0
```

Notation лучше работает с традиционными X.509 сертификатами и может быть удобнее в корпоративной PKI.

## Вывод

**Рекомендация для вашего случая:** Используйте **bundle** (Решение 1) — это самый простой и надежный способ для air-gapped окружения.

**Процесс:**
1. Поставщик передает: `image.tar` + `signature.bundle` + `supplier.pub` (один раз)
2. Вы проверяете bundle оффлайн: `cosign verify --key supplier.pub --bundle signature.bundle --insecure-ignore-tlog`
3. После проверки загружаете в Nexus

Bundle содержит всю необходимую информацию для верификации без доступа к интернету.
