Отличная задача! Давайте разберём полную конфигурацию для этой схемы.

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│ Клиент (203.0.113.42:54321)                                     │
│   ↓ (TLS, dst:443)                                              │
│ [TLS ClientHello → HTTPS запрос]                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Angie PRO (L4 балансировщик)                                    │
│   ├─ Принимает: обычное TLS-соединение                          │
│   ├─ Балансирует на 3 сервера Nginx                             │
│   ├─ Отправляет: заголовок PROXY + TLS данные                   │
│   └─ Активный healthcheck на порт 443                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Nginx OSS (L7 прокси)                                           │
│   ├─ Принимает: заголовок PROXY                                 │
│   ├─ Извлекает: реальный IP клиента (203.0.113.42)              │
│   ├─ Обрабатывает: HTTPS запрос                                 │
│   ├─ Добавляет: X-Forwarded-For с клиентским IP                 │
│   └─ Отправляет: на app с заголовком X-Forwarded-For            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ App (порт 443)                                                  │
│   └─ Видит: X-Forwarded-For: 203.0.113.42                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Конфигурация Angie PRO (L4 балансировщик)

```nginx
# /etc/angie/angie.conf

# Глобальные настройки
worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 4096;
    use epoll;
    multi_accept on;
}

# Блок для L4 балансировки (TCP/SSL)
stream {
    
    # Определение пула серверов с активным хелсчеком
    upstream backend_nginx {
        # Метод балансировки (по умолчанию round-robin)
        least_conn;  # или hash $remote_addr consistent;
        
        # Серверы с отправкой заголовка PROXY
        server 192.168.1.10:443 max_fails=3 fail_timeout=30s send-proxy-v2;
        server 192.168.1.11:443 max_fails=3 fail_timeout=30s send-proxy-v2;
        server 192.168.1.12:443 max_fails=3 fail_timeout=30s send-proxy-v2;
        
        # Активный хелсчек на тот же порт 443 (без отдельного порта)
        zone backend_nginx_zone 64k;
        
        # Метод хелсчека для TLS-серверов
        health_check interval=5s timeout=3s passes=2 fails=3 match=ssl_handshake;
    }
    
    # Шаблон для проверки успешного SSL handshake
    match ssl_handshake {
        # Проверяем, что сервер принимает соединение и отвечает на TLS
        send "160301";  # TLS ClientHello (начало)
        expect ~ "160303";  # TLS ServerHello (успешное рукопожатие)
    }
    
    # Сервер для приема клиентских соединений
    server {
        listen 443;
        listen [::]:443;
        
        # Проксируем на пул серверов
        proxy_pass backend_nginx;
        
        # Таймауты
        proxy_timeout 60s;
        proxy_connect_timeout 10s;
        
        # Логирование
        access_log /var/log/angie/stream_access.log combined;
        error_log /var/log/angie/stream_error.log warn;
        
        # Размер буфера для заголовка PROXY
        proxy_protocol_timeout 5s;
        
        # Включение режима проксирования с сохранением оригинальных данных
        proxy_buffer_size 16k;
        proxy_buffering on;
    }
}

# Опционально: метрики для мониторинга
stream {
    server {
        listen 8080;
        
        # Экспорт метрик для мониторинга (Prometheus, Grafana)
        status_zone stream_backend;
        
        location /status {
            status;
            status_format json;
            allow 127.0.0.1;
            allow 192.168.0.0/16;
            deny all;
        }
    }
}
```

---

## Конфигурация Nginx OSS (L7 прокси)

```nginx
# /etc/nginx/nginx.conf

user www-data;
worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 4096;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    log_format main '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" '
                    '"$http_x_forwarded_for" "$proxy_protocol_addr"';
    
    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;
    
    # Включаем поддержку больших заголовков (для TLS)
    large_client_header_buffers 4 16k;
    
    # Таймауты
    keepalive_timeout 65;
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    # Буферы прокси
    proxy_buffer_size 16k;
    proxy_buffers 4 32k;
    proxy_busy_buffers_size 64k;
    
    # Кэширование соединений к бэкенду
    upstream backend_app {
        least_conn;
        server 10.0.0.100:443 max_fails=3 fail_timeout=30s;
        server 10.0.0.101:443 max_fails=3 fail_timeout=30s;
        server 10.0.0.102:443 max_fails=3 fail_timeout=30s;
        
        # Keepalive для уменьшения оверхеда
        keepalive 32;
    }
    
    server {
        # Принимаем соединения с заголовком PROXY от Angie
        listen 443 ssl proxy_protocol;
        listen [::]:443 ssl proxy_protocol;
        
        # SSL сертификаты
        ssl_certificate /etc/nginx/ssl/example.com.crt;
        ssl_certificate_key /etc/nginx/ssl/example.com.key;
        
        # SSL настройки
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;
        
        # Доверяем только Angie PRO
        set_real_ip_from 192.168.1.0/24;  # Сеть Angie
        real_ip_header proxy_protocol;
        real_ip_recursive on;
        
        # Извлекаем реальный IP клиента из переменной
        # $proxy_protocol_addr содержит клиентский IP из заголовка PROXY
        # $remote_addr теперь содержит реальный клиентский IP
        
        server_name example.com;
        
        location / {
            # Проксируем на приложение
            proxy_pass https://backend_app;
            
            # Заголовки для бэкенда
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            
            # Ключевой заголовок: содержит цепочку прокси
            # Формат: клиент,прокси1,прокси2,...
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            
            # Дополнительные заголовки
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-Host $host;
            proxy_set_header X-Forwarded-Port $server_port;
            
            # Включаем поддержку keepalive к бэкенду
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            
            # Передаем оригинальный клиентский порт
            proxy_set_header X-Real-Port $remote_port;
            
            # Логирование с информацией о клиенте
            access_log /var/log/nginx/app_access.log main;
        }
        
        # Healthcheck endpoint для Angie (если нужен)
        location /health {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }
    }
}
```

---

## Как работает передача информации о клиенте

### Шаг 1: Клиент → Angie PRO

**Клиент отправляет:**
```
[ClientHello TLS] → [HTTPS: GET / HTTP/1.1]
```

**Angie видит:**
- `Клиент: 203.0.113.42:54321`
- `Сервер: 192.0.2.10:443` (сам себя)

---

### Шаг 2: Angie PRO → Nginx

**Angie отправляет на Nginx:**
```
┌─────────────────────────────────────────────────────────────────┐
│ Заголовок PROXY v2 (бинарный, 28+ байт)                         │
│   - Версия: v2                                                     │
│   - Адрес: 203.0.113.42 (клиент)                                  │
│   - Порт: 54321                                                    │
│   - Локальный адрес: 192.0.2.10                                    │
│   - Локальный порт: 443                                            │
├─────────────────────────────────────────────────────────────────┤
│ [ClientHello TLS] → [HTTPS: GET / HTTP/1.1]                      │
│ (оригинальные данные клиента без изменений)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

### Шаг 3: Nginx извлекает информацию

**Nginx читает заголовок PROXY и устанавливает:**
```nginx
$proxy_protocol_addr = "203.0.113.42"  # IP из заголовка PROXY
$remote_addr = "203.0.113.42"           # После set_real_ip_from
$remote_port = "54321"                  # Порт клиента
```

---

### Шаг 4: Nginx → App (передача X-Forwarded-For)

**Nginx формирует заголовок `X-Forwarded-For`:**

```nginx
# Если клиент напрямую подключился к Nginx:
# $proxy_add_x_forwarded_for = "203.0.113.42"

# Если был предыдущий прокси (например, другой прокси перед Angie):
# $proxy_add_x_forwarded_for = "203.0.113.42, 198.51.100.20"

# Nginx добавляет свой адрес:
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
# Результат: "203.0.113.42"
```

**Отправка в app:**
```
GET / HTTP/1.1
Host: example.com
X-Forwarded-For: 203.0.113.42
X-Real-IP: 203.0.113.42
X-Forwarded-Proto: https
...
```

---

## Healthcheck без отдельного порта

### Вариант 1: Проверка на уровне TCP (надёжно для TLS)

```nginx
stream {
    upstream backend_nginx {
        server 192.168.1.10:443 send-proxy-v2;
        server 192.168.1.11:443 send-proxy-v2;
        server 192.168.1.12:443 send-proxy-v2;
        
        health_check interval=5s timeout=3s passes=2 fails=3;
        # Проверяет только успешное соединение на порт 443
    }
}
```

### Вариант 2: Проверка с отправкой данных (более надёжно)

```nginx
stream {
    upstream backend_nginx {
        server 192.168.1.10:443 send-proxy-v2;
        server 192.168.1.11:443 send-proxy-v2;
        server 192.168.1.12:443 send-proxy-v2;
        
        health_check interval=5s timeout=3s passes=2 fails=3 match=tls_check;
    }
    
    match tls_check {
        # Отправляем начало TLS ClientHello
        send "\x16\x03\x01\x00\x00";
        # Ожидаем начало ответа (любые данные = сервер жив)
        expect ~ "\x16|\x15|\x14|\x17";
    }
}
```

### Вариант 3: Использование HTTP healthcheck через отдельный локейшн

Если можно добавить `/health` на Nginx:

```nginx
# На Nginx добавляем:
location /health {
    access_log off;
    return 200 "ok";
}

# В Angie:
http {
    upstream backend_nginx_http {
        server 192.168.1.10:443;
        server 192.168.1.11:443;
        server 192.168.1.12:443;
        
        health_check uri=/health interval=5s timeout=3s;
    }
}
```

---

## Проверка конфигурации

### 1. Проверка синтаксиса Angie:
```bash
sudo angie -t
```

### 2. Проверка синтаксиса Nginx:
```bash
sudo nginx -t
```

### 3. Тест соединения:
```bash
# С клиента
curl -v https://example.com/

# Проверка заголовка в app:
# X-Forwarded-For должен содержать: 203.0.113.42
```

### 4. Проверка логов:

**Angie логи:**
```log
2026/02/08 12:34:56 [info] stream upstream: "backend_nginx"
2026/02/08 12:34:56 [info] health check for peer 192.168.1.10:443 succeeded
```

**Nginx логи:**
```log
203.0.113.42 - - [08/Feb/2026:12:34:56 +0000] "GET / HTTP/1.1" 200 1234 "-" "curl/7.68.0" "203.0.113.42" "203.0.113.42"
```

---

## Итоговая схема передачи данных

```
Клиент (203.0.113.42:54321)
    ↓ (TLS, без заголовка)
Angie PRO
    ├─ Видит: клиент = 203.0.113.42:54321
    ├─ Отправляет: [PROXY v2 заголовок] + [TLS данные]
    └─ Балансирует на 1 из 3 Nginx
    ↓
Nginx (192.168.1.10:443)
    ├─ Читает заголовок PROXY
    ├─ Устанавливает: $remote_addr = 203.0.113.42
    ├─ Формирует: X-Forwarded-For: 203.0.113.42
    └─ Отправляет на app
    ↓
App
    └─ Видит: X-Forwarded-For: 203.0.113.42
```

---

## Ключевые моменты

| Компонент | Настройка | Результат |
|-----------|-----------|-----------|
| **Angie** | `send-proxy-v2` | Добавляет заголовок с клиентским IP |
| **Nginx** | `proxy_protocol` + `set_real_ip_from` | Извлекает реальный клиентский IP |
| **Nginx** | `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` | Передает клиентский IP в app |
| **Angie** | `health_check` с `match` | Проверяет доступность без отдельного порта |

**Результат:** Приложение получает корректный клиентский IP через заголовок `X-Forwarded-For`, а вся цепочка прокси работает с активным мониторингом доступности серверов.
