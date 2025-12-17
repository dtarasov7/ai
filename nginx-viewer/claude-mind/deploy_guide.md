# 🔒 Руководство по безопасному развертыванию Markmap Viewer

## Оглавление
1. [Подготовка сервера](#1-подготовка-сервера)
2. [Загрузка зависимостей](#2-загрузка-зависимостей)
3. [Настройка веб-сервера](#3-настройка-веб-сервера)
4. [Проверка безопасности](#4-проверка-безопасности)
5. [Мониторинг и обновления](#5-мониторинг-и-обновления)

---

## 1. Подготовка сервера

### 1.1 Установка необходимых пакетов

```bash
# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Устанавливаем необходимые утилиты
sudo apt install -y nginx wget curl openssl tree

# Проверяем версии
nginx -v
openssl version
```

### 1.2 Создание структуры директорий

```bash
# Создаем директорию проекта
sudo mkdir -p /var/www/markmap-viewer
cd /var/www/markmap-viewer

# Создаем поддиректории
sudo mkdir -p libs/{d3,markmap-view,markmap-lib}
sudo mkdir -p data

# Устанавливаем права
sudo chown -R www-data:www-data /var/www/markmap-viewer
sudo chmod -R 755 /var/www/markmap-viewer
```

---

## 2. Загрузка зависимостей

### 2.1 Сохранение скрипта загрузки

```bash
# Переходим в директорию проекта
cd /var/www/markmap-viewer

# Создаем скрипт загрузки
sudo nano download-dependencies.sh

# Вставляем содержимое скрипта download-dependencies.sh
# (см. артефакт download_deps)

# Делаем скрипт исполняемым
sudo chmod +x download-dependencies.sh
```

### 2.2 Загрузка библиотек

```bash
# Запускаем скрипт
sudo ./download-dependencies.sh

# Проверяем загруженные файлы
ls -lh libs/*/

# Должно быть примерно:
# libs/d3/d3.min.js (~500KB)
# libs/markmap-view/index.js (~100KB)
# libs/markmap-lib/index.js (~200KB)
```

### 2.3 Обновление SRI хешей в HTML

```bash
# Просматриваем сгенерированные хеши
cat sri-hashes.txt

# Копируем SRI хеши и обновляем markmap-viewer-secure.html
# Замените пустые атрибуты integrity="..." на актуальные значения
```

**Пример обновления в HTML:**
```html
<script src="libs/d3/d3.min.js" 
        integrity="sha384-ABC123..." 
        crossorigin="anonymous"></script>
```

---

## 3. Настройка веб-сервера

### 3.1 Настройка Nginx

```bash
# Создаем конфигурацию
sudo nano /etc/nginx/sites-available/markmap-viewer

# Вставляем содержимое из nginx-security.conf
# Не забудьте изменить:
# - server_name на ваш домен
# - пути к SSL сертификатам (если используете HTTPS)
```

### 3.2 Активация конфигурации

```bash
# Создаем символическую ссылку
sudo ln -s /etc/nginx/sites-available/markmap-viewer /etc/nginx/sites-enabled/

# Проверяем конфигурацию
sudo nginx -t

# Если OK, перезагружаем Nginx
sudo systemctl reload nginx

# Проверяем статус
sudo systemctl status nginx
```

### 3.3 Настройка файрвола (UFW)

```bash
# Разрешаем HTTP и HTTPS
sudo ufw allow 'Nginx Full'

# Проверяем статус
sudo ufw status
```

### 3.4 Настройка SSL (рекомендуется)

```bash
# Устанавливаем Certbot
sudo apt install -y certbot python3-certbot-nginx

# Получаем SSL сертификат
sudo certbot --nginx -d your-domain.com

# Certbot автоматически настроит редирект с HTTP на HTTPS
# и добавит задачу в cron для автоматического обновления

# Проверяем автообновление
sudo certbot renew --dry-run
```

---

## 4. Проверка безопасности

### 4.1 Тестирование заголовков безопасности

```bash
# Проверяем заголовки ответа
curl -I https://your-domain.com

# Должны быть:
# X-Frame-Options: DENY
# X-Content-Type-Options: nosniff
# X-XSS-Protection: 1; mode=block
# Content-Security-Policy: ...
# Strict-Transport-Security: ... (если HTTPS)
```

### 4.2 Онлайн проверки

Используйте следующие сервисы:

1. **Security Headers**: https://securityheaders.com
   - Проверяет наличие и корректность заголовков безопасности
   
2. **SSL Labs**: https://www.ssllabs.com/ssltest/
   - Оценивает SSL/TLS конфигурацию (цель: A или A+)
   
3. **Observatory**: https://observatory.mozilla.org
   - Комплексная проверка безопасности веб-сайта

### 4.3 Проверка целостности библиотек

```bash
# Создаем скрипт проверки
cat > /var/www/markmap-viewer/verify-integrity.sh << 'EOF'
#!/bin/bash

echo "=== Проверка целостности библиотек ==="

check_hash() {
    local file=$1
    local expected_hash=$2
    local actual_hash=$(openssl dgst -sha384 -binary "$file" | openssl base64 -A)
    
    if [ "sha384-$actual_hash" = "$expected_hash" ]; then
        echo "✓ $file - OK"
    else
        echo "✗ $file - FAILED"
        echo "  Expected: $expected_hash"
        echo "  Actual: sha384-$actual_hash"
        return 1
    fi
}

# Загружаем хеши из файла
while IFS= read -r line; do
    if [[ $line == Path:* ]]; then
        path=$(echo "$line" | cut -d' ' -f2)
    elif [[ $line == SRI:* ]]; then
        sri=$(echo "$line" | cut -d' ' -f2)
        check_hash "$path" "$sri"
    fi
done < sri-hashes.txt

echo "=== Проверка завершена ==="
EOF

chmod +x /var/www/markmap-viewer/verify-integrity.sh

# Запускаем проверку
./verify-integrity.sh
```

### 4.4 Проверка защиты от атак

```bash
# Тест Path Traversal
curl "https://your-domain.com/?file=../../../etc/passwd"
# Должен вернуть ошибку безопасности

# Тест XSS в параметре file
curl "https://your-domain.com/?file=<script>alert('xss')</script>.mm"
# Должен быть санитизирован

# Тест загрузки большого файла
# Создаем файл > 5MB
dd if=/dev/zero of=large.mm bs=1M count=6

# Пытаемся загрузить
curl "https://your-domain.com/?file=large.mm"
# Должен вернуть ошибку размера
```

---

## 5. Мониторинг и обновления

### 5.1 Настройка логирования

```bash
# Просмотр логов в реальном времени
sudo tail -f /var/log/nginx/markmap-access.log
sudo tail -f /var/log/nginx/markmap-error.log

# Анализ логов
sudo grep "error" /var/log/nginx/markmap-error.log | tail -20
```

### 5.2 Настройка fail2ban (опционально)

```bash
# Устанавливаем fail2ban
sudo apt install -y fail2ban

# Создаем конфигурацию для защиты от брутфорса
sudo nano /etc/fail2ban/jail.local

# Добавляем:
cat >> /etc/fail2ban/jail.local << 'EOF'
[nginx-markmap]
enabled = true
port = http,https
filter = nginx-markmap
logpath = /var/log/nginx/markmap-access.log
maxretry = 10
bantime = 3600
findtime = 600
EOF

# Создаем фильтр
sudo nano /etc/fail2ban/filter.d/nginx-markmap.conf

cat >> /etc/fail2ban/filter.d/nginx-markmap.conf << 'EOF'
[Definition]
failregex = ^<HOST> .* "(GET|POST) .* HTTP.*" (404|403|500) .*$
ignoreregex =
EOF

# Перезапускаем fail2ban
sudo systemctl restart fail2ban
sudo fail2ban-client status nginx-markmap
```

### 5.3 Автоматическая проверка обновлений

```bash
# Создаем скрипт проверки обновлений
cat > /var/www/markmap-viewer/check-updates.sh << 'EOF'
#!/bin/bash

echo "=== Проверка обновлений библиотек ==="

# D3.js
echo "Текущая версия D3.js: 7.8.5"
latest_d3=$(curl -s https://api.github.com/repos/d3/d3/releases/latest | grep tag_name | cut -d'"' -f4)
echo "Последняя версия: $latest_d3"

# Markmap
echo "Текущая версия Markmap: 0.15.4"
latest_markmap=$(curl -s https://api.github.com/repos/markmap/markmap/releases/latest | grep tag_name | cut -d'"' -f4)
echo "Последняя версия: $latest_markmap"

echo ""
echo "Для обновления запустите: ./download-dependencies.sh"
EOF

chmod +x /var/www/markmap-viewer/check-updates.sh

# Добавляем в cron для еженедельной проверки
(crontab -l 2>/dev/null; echo "0 9 * * 1 /var/www/markmap-viewer/check-updates.sh | mail -s 'Markmap Updates' admin@your-domain.com") | crontab -
```

### 5.4 Резервное копирование

```bash
# Создаем скрипт бэкапа
cat > /var/www/markmap-viewer/backup.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="/var/backups/markmap-viewer"
DATE=$(date +%Y%m%d_%H%M%S)
SOURCE="/var/www/markmap-viewer"

mkdir -p "$BACKUP_DIR"

# Создаем архив
tar -czf "$BACKUP_DIR/markmap-backup-$DATE.tar.gz" \
    -C "$(dirname $SOURCE)" \
    "$(basename $SOURCE)"

# Удаляем бэкапы старше 30 дней
find "$BACKUP_DIR" -name "markmap-backup-*.tar.gz" -mtime +30 -delete

echo "Backup created: markmap-backup-$DATE.tar.gz"
EOF

chmod +x /var/www/markmap-viewer/backup.sh

# Добавляем в cron для ежедневного бэкапа
(crontab -l 2>/dev/null; echo "0 2 * * * /var/www/markmap-viewer/backup.sh") | crontab -
```

---

## 📋 Чек-лист развертывания

- [ ] Установлены все необходимые пакеты
- [ ] Созданы директории с правильными правами
- [ ] Загружены все JavaScript библиотеки локально
- [ ] Обновлены SRI хеши в HTML файле
- [ ] Настроен и протестирован Nginx
- [ ] Настроен SSL сертификат (HTTPS)
- [ ] Проверены заголовки безопасности
- [ ] Протестирована защита от атак
- [ ] Настроено логирование
- [ ] Настроен мониторинг (опционально)
- [ ] Настроено автоматическое резервное копирование

---

## 🔐 Рекомендации по безопасности

1. **Регулярно обновляйте библиотеки** (проверяйте раз в месяц)
2. **Мониторьте CVE** для используемых библиотек
3. **Используйте только HTTPS** в продакшене
4. **Ограничьте доступ к .mm файлам** (по IP или авторизацией)
5. **Регулярно проверяйте логи** на подозрительную активность
6. **Делайте резервные копии** перед обновлениями
7. **Тестируйте обновления** на staging окружении

---

## 🆘 Устранение неполадок

### Библиотеки не загружаются

```bash
# Проверяем права доступа
ls -la /var/www/markmap-viewer/libs/

# Должно быть: drwxr-xr-x www-data www-data

# Исправляем права
sudo chown -R www-data:www-data /var/www/markmap-viewer/libs/
sudo chmod -R 755 /var/www/markmap-viewer/libs/
```

### Ошибка "libraries not loaded"

```bash
# Проверяем загрузку в браузере (F12 -> Network)
# Смотрим HTTP статусы для libs/*.js

# Проверяем конфигурацию Nginx
sudo nginx -t

# Проверяем пути в HTML
grep "src=\"libs/" /var/www/markmap-viewer/markmap-viewer-secure.html
```

### SSL сертификат не работает

```bash
# Проверяем статус Certbot
sudo certbot certificates

# Принудительное обновление
sudo certbot renew --force-renewal

# Проверяем конфигурацию SSL в Nginx
sudo nginx -t
```

---

## 📚 Дополнительные ресурсы

- **OWASP Security Headers**: https://owasp.org/www-project-secure-headers/
- **Content Security Policy**: https://content-security-policy.com/
- **Nginx Security**: https://nginx.org/en/docs/http/ngx_http_ssl_module.html
- **Let's Encrypt**: https://letsencrypt.org/docs/