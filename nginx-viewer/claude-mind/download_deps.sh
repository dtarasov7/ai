#!/bin/bash

# Скрипт для загрузки JavaScript зависимостей на локальный сервер
# Использование: ./download-dependencies.sh

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Загрузка JavaScript зависимостей для Markmap Viewer ===${NC}\n"

# Создаем структуру директорий
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/libs"

echo -e "${YELLOW}Создание директорий...${NC}"
mkdir -p "${LIB_DIR}/d3"
mkdir -p "${LIB_DIR}/markmap-view"
mkdir -p "${LIB_DIR}/markmap-lib"

# Функция для загрузки файла с проверкой
download_file() {
    local url=$1
    local output=$2
    local description=$3
    
    echo -e "${YELLOW}Загрузка ${description}...${NC}"
    
    if command -v wget &> /dev/null; then
        wget -q --show-progress -O "${output}" "${url}"
    elif command -v curl &> /dev/null; then
        curl -L --progress-bar -o "${output}" "${url}"
    else
        echo -e "${RED}Ошибка: wget или curl не найдены${NC}"
        exit 1
    fi
    
    if [ $? -eq 0 ] && [ -f "${output}" ] && [ -s "${output}" ]; then
        echo -e "${GREEN}✓ ${description} загружен${NC}"
    else
        echo -e "${RED}✗ Ошибка загрузки ${description}${NC}"
        exit 1
    fi
}

# Функция для вычисления SRI hash
calculate_sri() {
    local file=$1
    if command -v openssl &> /dev/null; then
        local hash=$(openssl dgst -sha384 -binary "${file}" | openssl base64 -A)
        echo "sha384-${hash}"
    else
        echo -e "${YELLOW}⚠ openssl не найден, пропускаем генерацию SRI${NC}"
        echo ""
    fi
}

# Загрузка D3.js v7.8.5
echo -e "\n${GREEN}1. D3.js v7.8.5${NC}"
D3_URL="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"
D3_FILE="${LIB_DIR}/d3/d3.min.js"
download_file "${D3_URL}" "${D3_FILE}" "D3.js"
D3_SRI=$(calculate_sri "${D3_FILE}")

# Загрузка Markmap View v0.15.4
echo -e "\n${GREEN}2. Markmap View v0.15.4${NC}"
MARKMAP_VIEW_URL="https://cdn.jsdelivr.net/npm/markmap-view@0.15.4/dist/browser/index.js"
MARKMAP_VIEW_FILE="${LIB_DIR}/markmap-view/index.js"
download_file "${MARKMAP_VIEW_URL}" "${MARKMAP_VIEW_FILE}" "Markmap View"
MARKMAP_VIEW_SRI=$(calculate_sri "${MARKMAP_VIEW_FILE}")

# Загрузка Markmap Lib v0.15.4
echo -e "\n${GREEN}3. Markmap Lib v0.15.4${NC}"
MARKMAP_LIB_URL="https://cdn.jsdelivr.net/npm/markmap-lib@0.15.4/dist/browser/index.js"
MARKMAP_LIB_FILE="${LIB_DIR}/markmap-lib/index.js"
download_file "${MARKMAP_LIB_URL}" "${MARKMAP_LIB_FILE}" "Markmap Lib"
MARKMAP_LIB_SRI=$(calculate_sri "${MARKMAP_LIB_FILE}")

# Проверка размеров файлов
echo -e "\n${GREEN}=== Проверка загруженных файлов ===${NC}"
echo "D3.js:        $(du -h "${D3_FILE}" | cut -f1)"
echo "Markmap View: $(du -h "${MARKMAP_VIEW_FILE}" | cut -f1)"
echo "Markmap Lib:  $(du -h "${MARKMAP_LIB_FILE}" | cut -f1)"

# Создание файла с SRI хешами
SRI_FILE="${SCRIPT_DIR}/sri-hashes.txt"
echo -e "\n${GREEN}=== Генерация SRI хешей ===${NC}"
cat > "${SRI_FILE}" << EOF
# Subresource Integrity (SRI) хеши для проверки целостности
# Сгенерировано: $(date)

D3.js v7.8.5:
Path: libs/d3/d3.min.js
SRI: ${D3_SRI}

Markmap View v0.15.4:
Path: libs/markmap-view/index.js
SRI: ${MARKMAP_VIEW_SRI}

Markmap Lib v0.15.4:
Path: libs/markmap-lib/index.js
SRI: ${MARKMAP_LIB_SRI}
EOF

echo -e "${GREEN}✓ SRI хеши сохранены в ${SRI_FILE}${NC}"

# Создание README
README_FILE="${LIB_DIR}/README.md"
cat > "${README_FILE}" << EOF
# JavaScript Libraries for Markmap Viewer

## Downloaded Libraries

### D3.js v7.8.5
- **Source**: https://d3js.org/
- **License**: ISC
- **File**: d3/d3.min.js
- **Downloaded**: $(date)

### Markmap View v0.15.4
- **Source**: https://markmap.js.org/
- **License**: MIT
- **File**: markmap-view/index.js
- **Downloaded**: $(date)

### Markmap Lib v0.15.4
- **Source**: https://markmap.js.org/
- **License**: MIT
- **File**: markmap-lib/index.js
- **Downloaded**: $(date)

## Security

SRI hashes are stored in ../sri-hashes.txt for integrity verification.

## Updates

To update libraries, run the download-dependencies.sh script again.
Check for new versions at:
- D3.js: https://github.com/d3/d3/releases
- Markmap: https://github.com/markmap/markmap/releases
EOF

echo -e "\n${GREEN}=== Завершено успешно! ===${NC}"
echo -e "${YELLOW}Структура директорий:${NC}"
tree -L 2 "${LIB_DIR}" 2>/dev/null || find "${LIB_DIR}" -type f

echo -e "\n${YELLOW}Следующие шаги:${NC}"
echo "1. Обновите HTML файл для использования локальных библиотек"
echo "2. Настройте веб-сервер для обслуживания директории libs/"
echo "3. Добавьте Content Security Policy заголовки"
echo "4. Периодически проверяйте обновления библиотек"

echo -e "\n${GREEN}Примеры конфигурации веб-сервера:${NC}"
echo -e "${YELLOW}Nginx:${NC}"
echo "location /libs/ {"
echo "    alias /path/to/libs/;"
echo "    expires 1y;"
echo "    add_header Cache-Control \"public, immutable\";"
echo "}"

echo -e "\n${YELLOW}Apache:${NC}"
echo "Alias /libs /path/to/libs"
echo "<Directory /path/to/libs>"
echo "    Require all granted"
echo "    ExpiresActive On"
echo "    ExpiresDefault \"access plus 1 year\""
echo "</Directory>"
