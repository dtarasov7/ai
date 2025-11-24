Конечно! Ниже приведён **Bash-скрипт для рекурсивного экспорта всех секретов из KV v2 в HashiCorp Vault с использованием только `curl` и `jq`** (без CLI-утилиты `vault`).

---

### ✅ Требования:
- Установлены: `curl`, `jq`
- Переменные окружения:
  - `VAULT_ADDR` — адрес Vault (например, `https://vault.example.com:8200`)
  - `VAULT_TOKEN` — валидный токен с правами `list` и `read` на указанный путь

---

### 📜 Скрипт: `vault_export_kv2_curl.sh`

```bash
#!/bin/bash

set -euo pipefail

# === Проверка переменных окружения ===
if [[ -z "${VAULT_ADDR:-}" ]]; then
    echo "Ошибка: не установлена переменная окружения VAULT_ADDR"
    exit 1
fi

if [[ -z "${VAULT_TOKEN:-}" ]]; then
    echo "Ошибка: не установлен VAULT_TOKEN"
    exit 1
fi

# === Настройки ===
VAULT_PATH_PREFIX="${1:-}"
OUTPUT_DIR="${2:-./vault_export}"

if [[ -z "$VAULT_PATH_PREFIX" ]]; then
    echo "Использование: $0 <vault_path> [output_dir]"
    echo "Пример: $0 secret/myapp ./my_secrets"
    exit 1
fi

# Убираем начальный и конечный слэш у пути
VAULT_PATH_PREFIX="${VAULT_PATH_PREFIX#/}"
VAULT_PATH_PREFIX="${VAULT_PATH_PREFIX%/}"

mkdir -p "$OUTPUT_DIR"

# === Вспомогательные функции ===

# Выполняет LIST-запрос к KV v2 (на самом деле — к metadata)
vault_list() {
    local path="$1"
    # В KV v2 list выполняется по /metadata/
    local url="${VAULT_ADDR}/v1/${path}/"
    curl -sS \
        --header "X-Vault-Token: ${VAULT_TOKEN}" \
        --header "Accept: application/json" \
        "$url"
}

# Выполняет READ-запрос к KV v2 (данные находятся в /data/)
vault_read() {
    local path="$1"
    local url="${VAULT_ADDR}/v1/${path}"
    curl -sS \
        --header "X-Vault-Token: ${VAULT_TOKEN}" \
        --header "Accept: application/json" \
        "$url"
}

# === Рекурсивная функция обхода ===
walk_path() {
    local rel_path="$1"  # относительный путь внутри секретного движка, например: myapp/config

    # Полный путь для запроса к metadata (для list)
    local metadata_path="secret/metadata/${rel_path}"

    echo "📁 Проверка пути: $rel_path"

    # Попытка выполнить LIST (запрос к metadata)
    local list_resp
    list_resp=$(vault_list "$metadata_path" 2>/dev/null) || {
        # LIST не удался — возможно, это лист (секрет), а не директория
        # Проверим, существует ли секрет по этому пути
        local data_path="secret/data/${rel_path}"
        local read_resp
        if read_resp=$(vault_read "$data_path" 2>/dev/null); then
            if echo "$read_resp" | jq -e '.data.data' >/dev/null 2>&1; then
                echo "📥 Экспорт секрета: $rel_path"
                echo "$read_resp" | jq -r '.data.data' > "$OUTPUT_DIR/${rel_path//\//_}.json"
                return 0
            fi
        fi
        # Если и read не сработал — ошибка или пустой путь
        echo "⚠️  Путь не найден или недоступен: $rel_path"
        return 1
    }

    # Проверяем, есть ли ключи в ответе
    if ! echo "$list_resp" | jq -e '.data.keys // empty' >/dev/null; then
        # Нет ключей — возможно, это секрет без подключей, но list сработал?
        # В KV v2 такое маловероятно, но на всякий случай пробуем прочитать как секрет
        local data_path="secret/data/${rel_path}"
        local read_resp
        if read_resp=$(vault_read "$data_path" 2>/dev/null); then
            if echo "$read_resp" | jq -e '.data.data' >/dev/null 2>&1; then
                echo "📥 Экспорт секрета (после list): $rel_path"
                echo "$read_resp" | jq -r '.data.data' > "$OUTPUT_DIR/${rel_path//\//_}.json"
                return 0
            fi
        fi
        echo "⚠️  Пустой или недоступный путь: $rel_path"
        return 1
    fi

    # Получаем список подключей
    echo "$list_resp" | jq -r '.data.keys[]' | while IFS= read -r key; do
        [[ -z "$key" ]] && continue
        # Убираем завершающий слэш, если есть (для "директорий")
        key="${key%/}"
        walk_path "${rel_path}/${key}"
    done
}

# === Запуск ===
echo "Начинаю экспорт из Vault KV v2"
echo "Базовый путь: secret/ (KV v2)"
echo "Подпуть: $VAULT_PATH_PREFIX"
echo "Выход: $OUTPUT_DIR"

walk_path "$VAULT_PATH_PREFIX"

echo "✅ Экспорт завершён. Файлы сохранены в: $OUTPUT_DIR"
```

---

### ▶️ Как использовать:

1. Установите переменные окружения:
   ```bash
   export VAULT_ADDR=https://your-vault-domain:8200
   export VAULT_TOKEN=s.your.token.here
   ```

2. Сохраните скрипт как `vault_export_kv2_curl.sh`, сделайте исполняемым:
   ```bash
   chmod +x vault_export_kv2_curl.sh
   ```

3. Запустите:
   ```bash
   ./vault_export_kv2_curl.sh myapp/config ./secrets
   ```

> ⚠️ Обратите внимание: в отличие от `vault kv get secret/myapp`, при использовании API напрямую:
> - **List** делается по: `.../v1/secret/metadata/myapp/`
> - **Read** делается по: `.../v1/secret/data/myapp`

Скрипт автоматически добавляет `secret/metadata/` и `secret/data/` — вы указываете только **относительную часть пути** после `secret/`.

---

### 💡 Пример:

Если в Vault есть:
```
secret/myapp/db
secret/myapp/api/keys
```

Вы запускаете:
```bash
./vault_export_kv2_curl.sh myapp ./out
```

Результат:
```
out/myapp_db.json
out/myapp_api_keys.json
```

---

### 🔒 Безопасность:
- Токен передаётся в заголовке `X-Vault-Token` — убедитесь, что соединение идёт по HTTPS.
- Не сохраняйте токен в скриптах или логах.

---

Если ваш секретный движок называется не `secret`, а, например, `kv-prod`, просто замените в скрипте все вхождения `secret/` на `kv-prod/` (или параметризуйте — дайте знать, если нужно).

Готов помочь адаптировать под ваш случай!
