# 🔒 Чеклист безопасности PlantUML Viewer

## Выполненные улучшения безопасности

### ✅ 1. Локализация зависимостей
- **Проблема**: Загрузка pako.js с CDN открывает возможность supply chain атак
- **Решение**: Локальное хранение всех библиотек
- **Файлы**: `/libs/pako.min.js`

### ✅ 2. Локальный PlantUML сервер
- **Проблема**: Отправка диаграмм на публичный сервер может привести к утечке данных
- **Решение**: Использование локального PlantUML сервера
- **Конфигурация**: `http://localhost:8080/png/`

### ✅ 3. Content Security Policy (CSP)
- **Добавлен**: Строгий CSP заголовок в HTML
- **Защита**: Предотвращает загрузку внешних скриптов и XSS атаки

### ✅ 4. XSS защита
- **Проблема**: Использование `innerHTML` с непроверенными данными
- **Решение**: Использование `textContent` и создание элементов через DOM API

### ✅ 5. Path Traversal защита
- **Усилена**: Проверка на `..` и `.` в сегментах пути
- **Добавлено**: Валидация расширений файлов

### ✅ 6. Ограничения
- Максимальный размер файла: 1MB
- Таймаут загрузки: 10 секунд
- Same-origin policy для всех запросов

---

## 🚀 Пошаговая установка

### Шаг 1: Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка необходимых пакетов
sudo apt install -y wget curl openjdk-17-jre nginx
```

### Шаг 2: Загрузка зависимостей

```bash
# Скачивание и запуск скрипта установки
wget https://your-server.com/setup-local-modules.sh
chmod +x setup-local-modules.sh
sudo bash setup-local-modules.sh
```

### Шаг 3: Проверка целостности файлов

```bash
# Проверка pako.min.js
sha256sum /var/www/html/libs/pako.min.js

# Сохраните полученный хеш для периодической проверки
echo "YOUR_HASH_HERE" > /var/www/html/libs/pako.min.js.sha256

# Автоматическая проверка целостности (добавьте в cron)
cat > /usr/local/bin/check-integrity.sh << 'EOF'
#!/bin/bash
cd /var/www/html/libs
sha256sum -c pako.min.js.sha256 || {
    echo "ALERT: File integrity check failed!" | mail -s "Security Alert" admin@yourdomain.com
}
EOF

chmod +x /usr/local/bin/check-integrity.sh
```

### Шаг 4: Запуск локального PlantUML сервера

```bash
# Запуск через systemd
sudo systemctl start plantuml
sudo systemctl enable plantuml

# Проверка статуса
sudo systemctl status plantuml

# Или запуск вручную для тестирования
cd /var/www/html/plantuml
java -jar plantuml.jar -picoweb:8080
```

### Шаг 5: Настройка Nginx (опционально)

```bash
# Создание конфигурации для обратного прокси
sudo tee /etc/nginx/sites-available/plantuml << 'EOF'
server {
    listen 80;
    server_name plantuml.yourdomain.com;

    # Ограничение размера загружаемых файлов
    client_max_body_size 1M;

    # Основное приложение
    location / {
        root /var/www/html;
        index plantuml-viewer-secure.html;
        
        # Защита от clickjacking
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
    }

    # Прокси для PlantUML сервера
    location /plantuml/ {
        proxy_pass http://localhost:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Статические библиотеки
    location /libs/ {
        root /var/www/html;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# Активация конфигурации
sudo ln -s /etc/nginx/sites-available/plantuml /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 🔍 Периодические проверки безопасности

### Ежедневные задачи (автоматизировать через cron)

```bash
# Проверка целостности файлов
0 2 * * * /usr/local/bin/check-integrity.sh

# Проверка обновлений PlantUML (раз в неделю)
0 3 * * 0 /usr/local/bin/check-plantuml-updates.sh
```

### Создание скрипта проверки обновлений

```bash
cat > /usr/local/bin/check-plantuml-updates.sh << 'EOF'
#!/bin/bash

CURRENT_VERSION=$(java -jar /var/www/html/plantuml/plantuml.jar -version 2>&1 | grep -oP 'PlantUML version \K[0-9.]+')
LATEST_VERSION=$(curl -s https://api.github.com/repos/plantuml/plantuml/releases/latest | grep -oP '"tag_name": "v\K[0-9.]+')

if [ "$CURRENT_VERSION" != "$LATEST_VERSION" ]; then
    echo "New PlantUML version available: $LATEST_VERSION (current: $CURRENT_VERSION)"
    # Отправка уведомления
fi
EOF

chmod +x /usr/local/bin/check-plantuml-updates.sh
```

---

## 🛡️ Дополнительные меры безопасности

### 1. Firewall настройка

```bash
# Разрешить только локальный доступ к PlantUML серверу
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8080/tcp  # PlantUML доступен только локально
sudo ufw enable
```

### 2. Ограничение доступа к файлам

```bash
# Запретить выполнение в директории uploads
sudo tee /var/www/html/.htaccess << 'EOF'
<FilesMatch "\.(plant|plantuml|puml|uml)$">
    Order Allow,Deny
    Allow from all
</FilesMatch>
<FilesMatch "\.">
    Order Deny,Allow
    Deny from all
</FilesMatch>
EOF
```

### 3. Логирование и мониторинг

```bash
# Настройка логирования доступа к PlantUML
sudo mkdir -p /var/log/plantuml
sudo chown www-data:www-data /var/log/plantuml

# Добавление в systemd service
# В секцию [Service]:
# StandardOutput=append:/var/log/plantuml/output.log
# StandardError=append:/var/log/plantuml/error.log
```

### 4. Регулярное обновление зависимостей

```bash
# Создание скрипта обновления (выполнять вручную после проверки)
cat > /usr/local/bin/update-dependencies.sh << 'EOF'
#!/bin/bash
set -e

echo "Backup current files..."
sudo cp /var/www/html/libs/pako.min.js /var/www/html/libs/pako.min.js.backup

echo "Downloading new version..."
sudo wget -O /var/www/html/libs/pako.min.js \
    https://cdnjs.cloudflare.com/ajax/libs/pako/2.1.0/pako.min.js

echo "Calculating new hash..."
sha256sum /var/www/html/libs/pako.min.js

echo "Please verify the hash manually before proceeding!"
echo "Press Enter to continue or Ctrl+C to abort..."
read

echo "Update completed. Test the application!"
EOF

chmod +x /usr/local/bin/update-dependencies.sh
```

---

## 📋 Чеклист после установки

- [ ] Локальный PlantUML сервер запущен и работает
- [ ] Все библиотеки загружены локально
- [ ] Проверены SHA256 хеши файлов
- [ ] Настроен firewall
- [ ] Настроен Nginx с правильными заголовками безопасности
- [ ] Созданы скрипты для проверки целостности
- [ ] Настроен мониторинг и логирование
- [ ] Протестирован весь функционал
- [ ] Документация обновлена

---

## 🔄 План обновлений

### Ежемесячно:
1. Проверка обновлений PlantUML
2. Проверка обновлений pako.js
3. Анализ логов безопасности

### Ежеквартально:
1. Полный аудит безопасности
2. Обновление всех зависимостей
3. Тестирование резервного копирования

---

## 📞 Контакты для сообщений об уязвимостях

- Email: security@yourdomain.com
- Процесс: Responsible Disclosure Policy
- Время ответа: 48 часов

---

## 📚 Дополнительные ресурсы

- [PlantUML Security Guide](https://plantuml.com/security)
- [OWASP Security Guidelines](https://owasp.org/)
- [Content Security Policy Reference](https://content-security-policy.com/)

---

**Версия документа**: 1.0  
**Последнее обновление**: 2024-12-09  
**Автор**: Security Team