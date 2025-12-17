#!/bin/bash

# Скрипт для загрузки внешних зависимостей на локальный сервер
# Использование: sudo bash setup-local-modules.sh

set -e

echo "=== Установка локальных модулей для PlantUML Viewer ==="

# Определяем директорию для статических файлов
WEB_ROOT="/var/www/html"
LIBS_DIR="$WEB_ROOT/libs"
PLANTUML_DIR="$WEB_ROOT/plantuml"

# Создаем необходимые директории
echo "Создание директорий..."
mkdir -p "$LIBS_DIR"
mkdir -p "$PLANTUML_DIR"

# Загрузка pako.js
echo "Загрузка pako.min.js..."
PAKO_VERSION="2.1.0"
PAKO_URL="https://cdnjs.cloudflare.com/ajax/libs/pako/${PAKO_VERSION}/pako.min.js"
wget -O "$LIBS_DIR/pako.min.js" "$PAKO_URL"

# Проверка целостности (опционально, можно добавить известный хеш)
echo "Проверка загруженного файла pako.min.js..."
if [ -f "$LIBS_DIR/pako.min.js" ]; then
    SIZE=$(stat -f%z "$LIBS_DIR/pako.min.js" 2>/dev/null || stat -c%s "$LIBS_DIR/pako.min.js")
    echo "✓ pako.min.js загружен (размер: $SIZE байт)"
    
    # Вычисление SHA256 хеша для проверки
    if command -v sha256sum &> /dev/null; then
        SHA256=$(sha256sum "$LIBS_DIR/pako.min.js" | awk '{print $1}')
        echo "  SHA256: $SHA256"
        echo "  Сохраните этот хеш для будущих проверок целостности"
    fi
else
    echo "✗ Ошибка загрузки pako.min.js"
    exit 1
fi

# Загрузка PlantUML JAR (для локального сервера)
echo ""
echo "Загрузка PlantUML JAR для локального рендеринга..."
PLANTUML_VERSION="1.2024.7"
PLANTUML_URL="https://github.com/plantuml/plantuml/releases/download/v${PLANTUML_VERSION}/plantuml-${PLANTUML_VERSION}.jar"

wget -O "$PLANTUML_DIR/plantuml.jar" "$PLANTUML_URL" || {
    echo "Предупреждение: Не удалось загрузить PlantUML JAR"
    echo "Вы можете продолжить использовать внешний сервер или загрузить вручную"
}

if [ -f "$PLANTUML_DIR/plantuml.jar" ]; then
    echo "✓ plantuml.jar загружен"
fi

# Установка прав доступа
echo ""
echo "Настройка прав доступа..."
chown -R www-data:www-data "$LIBS_DIR" 2>/dev/null || chown -R nginx:nginx "$LIBS_DIR" 2>/dev/null || true
chmod -R 755 "$LIBS_DIR"

if [ -f "$PLANTUML_DIR/plantuml.jar" ]; then
    chown -R www-data:www-data "$PLANTUML_DIR" 2>/dev/null || chown -R nginx:nginx "$PLANTUML_DIR" 2>/dev/null || true
    chmod -R 755 "$PLANTUML_DIR"
fi

# Создание скрипта для локального PlantUML сервера (опционально)
echo ""
echo "Создание скрипта локального PlantUML сервера..."
cat > "$PLANTUML_DIR/start-server.sh" << 'EOF'
#!/bin/bash
# Простой локальный PlantUML сервер на Python

PLANTUML_JAR="./plantuml.jar"
PORT=8080

if [ ! -f "$PLANTUML_JAR" ]; then
    echo "Ошибка: plantuml.jar не найден"
    exit 1
fi

echo "Запуск PlantUML сервера на порту $PORT..."
java -jar "$PLANTUML_JAR" -picoweb:$PORT
EOF

chmod +x "$PLANTUML_DIR/start-server.sh"

# Создание systemd service для PlantUML (опционально)
cat > /etc/systemd/system/plantuml.service << EOF
[Unit]
Description=PlantUML Local Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=$PLANTUML_DIR
ExecStart=/usr/bin/java -jar $PLANTUML_DIR/plantuml.jar -picoweb:8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "=== Установка завершена ==="
echo ""
echo "Файлы установлены:"
echo "  - $LIBS_DIR/pako.min.js"
echo "  - $PLANTUML_DIR/plantuml.jar (если загружен)"
echo ""
echo "Для запуска локального PlantUML сервера:"
echo "  1. Убедитесь что установлена Java: java -version"
echo "  2. Запустите: sudo systemctl start plantuml"
echo "  3. Автозапуск: sudo systemctl enable plantuml"
echo ""
echo "Или запустите вручную:"
echo "  cd $PLANTUML_DIR && ./start-server.sh"
echo ""
echo "Не забудьте обновить HTML файл для использования локальных путей!"
