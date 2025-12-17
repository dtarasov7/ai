# Инструкция по безопасной настройке Markdown Viewer

## Часть 1: Загрузка библиотек на локальный диск

### Шаг 1: Создание структуры каталогов

```bash
# Переходим в директорию вашего проекта
cd /path/to/your/project

# Создаём структуру директорий
mkdir -p assets/{js,css}
mkdir -p markdown

# Устанавливаем правильные права доступа
chmod 755 assets assets/js assets/css markdown
```

### Шаг 2: Загрузка библиотек

```bash
# Переходим в директорию JS
cd assets/js

# Загружаем marked.js (версия 9.1.6)
wget https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js \
     -O marked.min.js

# Загружаем DOMPurify (последняя версия)
wget https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.6/purify.min.js \
     -O purify.min.js

# Переходим в директорию CSS
cd ../css

# Загружаем GitHub Markdown CSS
wget https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.0/github-markdown.min.css \
     -O github-markdown.min.css

# Возвращаемся в корень проекта
cd ../..
```

### Шаг 3: Проверка целостности файлов

```bash
# Проверяем, что файлы загружены
ls -lh assets/js/
ls -lh assets/css/

# Проверяем размеры файлов (ориентировочно)
# marked.min.js: ~50-60KB
# purify.min.js: ~40-50KB
# github-markdown.min.css: ~40-50KB

# Вычисляем SHA256 хэши для документирования
sha256sum assets/js/marked.min.js
sha256sum assets/js/purify.min.js
sha256sum assets/css/github-markdown.min.css

# Сохраняем хэши в файл
sha256sum assets/js/*.js assets/css/*.css > checksums.txt
```

### Шаг 4: Установка правильных прав доступа

```bash
# Файлы должны быть только для чтения
chmod 644 assets/js/*.js
chmod 644 assets/css/*.css

# Если веб-сервер работает под специальным пользователем (например, www-data)
sudo chown -R www-data:www-data assets/
sudo chown -R www-data:www-data markdown/
```

### Шаг 5: Настройка веб-сервера (Nginx)

```bash
# Редактируем конфигурацию Nginx
sudo nano /etc/nginx/sites-available/your-site

# Добавляем заголовки безопасности:
```

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    root /path/to/your/project;
    index markdown-viewer.html;
    
    # Заголовки безопасности
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Content Security Policy
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self';" always;
    
    # Кэширование статических ресурсов
    location ~* \.(js|css)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Разрешаем доступ только к markdown файлам
    location ~ \.md$ {
        add_header Content-Type "text/markdown; charset=utf-8";
    }
    
    # Запрещаем доступ к скрытым файлам
    location ~ /\. {
        deny all;
    }
}
```

```bash
# Проверяем конфигурацию
sudo nginx -t

# Перезагружаем Nginx
sudo systemctl reload nginx
```

### Шаг 6: Настройка веб-сервера (Apache)

```bash
# Редактируем .htaccess или конфигурацию Apache
sudo nano /path/to/your/project/.htaccess
```

```apache
# Заголовки безопасности
Header always set X-Frame-Options "SAMEORIGIN"
Header always set X-Content-Type-Options "nosniff"
Header always set X-XSS-Protection "1; mode=block"
Header always set Referrer-Policy "strict-origin-when-cross-origin"
Header always set Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self';"

# Кэширование
<FilesMatch "\.(js|css)$">
    Header set Cache-Control "max-age=31536000, public, immutable"
</FilesMatch>

# Разрешаем только нужные файлы
<FilesMatch "\.(html|md|js|css)$">
    Order allow,deny
    Allow from all
</FilesMatch>

# Запрещаем доступ к скрытым файлам
<FilesMatch "^\.">
    Order allow,deny
    Deny from all
</FilesMatch>
```

### Шаг 7: Создание тестового markdown файла

```bash
# Создаём тестовый файл
cat > markdown/test.md << 'EOF'
# Тест безопасности

Это тестовый markdown файл.

## Проверка XSS защиты

Следующие элементы должны быть **заблокированы**:

<script>alert('XSS')</script>
<img src=x onerror="alert('XSS')">

## Обычный контент

- Список 1
- Список 2
- Список 3

**Жирный текст** и *курсив*.

```javascript
console.log('Код должен отображаться безопасно');
```
EOF

# Устанавливаем права
chmod 644 markdown/test.md
```

### Шаг 8: Автоматическая проверка целостности (опционально)

```bash
# Создаём скрипт проверки
cat > check_integrity.sh << 'EOF'
#!/bin/bash

echo "Проверка целостности библиотек..."

if sha256sum -c checksums.txt --quiet; then
    echo "✓ Все файлы в порядке"
    exit 0
else
    echo "✗ ВНИМАНИЕ: Обнаружены изменения в файлах!"
    echo "Возможна компрометация. Проверьте файлы вручную."
    exit 1
fi
EOF

chmod +x check_integrity.sh

# Добавляем в cron для периодической проверки
(crontab -l 2>/dev/null; echo "0 2 * * * /path/to/your/project/check_integrity.sh | mail -s 'Integrity Check' admin@example.com") | crontab -
```

### Шаг 9: Тестирование

```bash
# Проверяем, что всё работает
curl http://localhost/markdown-viewer.html?file=markdown/test.md

# Или открываем в браузере
# http://your-domain.com/markdown-viewer.html?file=markdown/test.md
```

## Часть 2: Проверка безопасности

### Тесты XSS защиты

Создайте файл `markdown/xss-test.md`:

```bash
cat > markdown/xss-test.md << 'EOF'
# XSS Test

<script>alert('This should be blocked')</script>
<img src=x onerror="alert('This should be blocked')">
<iframe src="javascript:alert('This should be blocked')"></iframe>

[Click me](javascript:alert('This should be blocked'))
EOF
```

Откройте этот файл через viewer - никакие alert() не должны сработать.

### Тест Path Traversal

```bash
# Эти запросы должны быть заблокированы:
curl "http://localhost/markdown-viewer.html?file=../../etc/passwd"
curl "http://localhost/markdown-viewer.html?file=../../../etc/shadow"
curl "http://localhost/markdown-viewer.html?file=%2e%2e%2f%2e%2e%2fetc%2fpasswd"
```

## Часть 3: Мониторинг и логирование

### Настройка логирования подозрительных запросов

```bash
# Создаём скрипт анализа логов
cat > analyze_logs.sh << 'EOF'
#!/bin/bash

LOG_FILE="/var/log/nginx/access.log"  # или путь к логам Apache
ALERT_EMAIL="security@example.com"

# Ищем подозрительные паттерны
suspicious=$(grep -E "(\.\.|%2e%2e|etc/passwd|etc/shadow)" "$LOG_FILE" | tail -20)

if [ ! -z "$suspicious" ]; then
    echo "Обнаружены подозрительные запросы:" | mail -s "Security Alert" "$ALERT_EMAIL"
    echo "$suspicious" | mail -s "Security Alert Details" "$ALERT_EMAIL"
fi
EOF

chmod +x analyze_logs.sh

# Добавляем в cron
(crontab -l 2>/dev/null; echo "*/15 * * * * /path/to/your/project/analyze_logs.sh") | crontab -
```

## Резюме команд одной строкой

```bash
# Быстрая установка (всё в одной команде)
cd /path/to/your/project && \
mkdir -p assets/{js,css} markdown && \
cd assets/js && \
wget -q https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js -O marked.min.js && \
wget -q https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.6/purify.min.js -O purify.min.js && \
cd ../css && \
wget -q https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.0/github-markdown.min.css -O github-markdown.min.css && \
cd ../.. && \
chmod -R 644 assets/js/*.js assets/css/*.css && \
chmod 755 assets assets/js assets/css markdown && \
echo "✓ Установка завершена успешно!"
```