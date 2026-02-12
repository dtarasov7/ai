Теперь у меня достаточно информации для составления конфигурации. Вот полная конфигурация:

## Конфигурация Angie PRO (L4 балансировщик)

```nginx
# /etc/angie/angie.conf

stream {
    # Upstream с тремя nginx-серверами
    upstream nginx_backends {
        # Зона разделяемой памяти для хранения состояния и работы health check
        zone nginx_backends 256k;
        
        # Балансировка по наименьшему числу соединений
        least_conn;
        
        # Три upstream сервера
        server nginx1.example.com:443 max_fails=2 fail_timeout=30s;
        server nginx2.example.com:443 max_fails=2 fail_timeout=30s;
        server nginx3.example.com:443 max_fails=2 fail_timeout=30s;
    }
    
    server {
        listen 443;
        
        # Зона для сбора метрик
        status_zone nginx_lb;
        
        proxy_pass nginx_backends;
        
        # Включаем PROXY protocol для передачи IP клиента на nginx
        proxy_protocol on;
        
        # Таймауты
        proxy_connect_timeout 5s;
        proxy_timeout 300s;
        
        # Активная проверка здоровья (PRO функция)
        # Проверка TCP-соединения на тот же порт 443
        upstream_probe backend_health 
            interval=5s 
            fails=3 
            passes=2 
            timeout=3s;
    }
}

# HTTP блок для API мониторинга (опционально)
http {
    server {
        listen 8080;
        
        location /status/ {
            api /status/;
        }
        
        location /api/ {
            api /;
        }
    }
}
```

## Конфигурация Nginx OSS (L7 прокси)

```nginx
# /etc/nginx/nginx.conf

http {
    # Формат логов с реальным IP клиента
    log_format main '$proxy_protocol_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" '
                    '"$http_x_forwarded_for"';

    # Настройка доверенных источников PROXY protocol
    set_real_ip_from 10.0.0.0/8;        # Сеть балансировщика Angie
    set_real_ip_from 192.168.0.0/16;    # Или другие доверенные сети
    real_ip_header proxy_protocol;
    
    upstream app_backend {
        server app.example.com:443;
        keepalive 32;
    }

    server {
        # Слушаем с поддержкой PROXY protocol
        listen 443 ssl proxy_protocol;
        
        server_name example.com;
        
        ssl_certificate     /etc/nginx/ssl/server.crt;
        ssl_certificate_key /etc/nginx/ssl/server.key;
        ssl_protocols       TLSv1.2 TLSv1.3;
        
        access_log /var/log/nginx/access.log main;
        
        location / {
            proxy_pass https://app_backend;
            
            # X-Forwarded-For с IP клиента (из PROXY protocol) + IP nginx
            # $proxy_add_x_forwarded_for добавит $remote_addr к существующему заголовку
            # После real_ip_header, $remote_addr = IP клиента из PROXY protocol
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            
            # Дополнительные заголовки
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # SSL к backend
            proxy_ssl_verify off;  # или on с настройкой CA
            
            proxy_http_version 1.1;
            proxy_set_header Connection "";
        }
    }
}
```

## Ключевые моменты конфигурации:

### Angie PRO:

1. **proxy_protocol on** — включает PROXY protocol для соединений к проксируемому серверу, передавая IP клиента.

2. **upstream_probe** — определяет активную проверку здоровья для пиров в upstream группах. Angie PRO регулярно проверяет каждый пир согласно настроенным параметрам.

3. Для использования проверок upstream должен иметь зону разделяемой памяти (zone).

4. Директива upstream_probe в stream модуле проверяет здоровье серверов путём периодического создания тестовых соединений.

### Nginx OSS:

5. Модуль RealIP используется для изменения адреса клиента на тот, что передан в заголовке PROXY protocol. PROXY protocol должен быть предварительно включен параметром proxy_protocol в директиве listen.

6. **$proxy_add_x_forwarded_for** — эта переменная содержит значение `$http_x_forwarded_for` + `$remote_addr`. После применения `real_ip_header proxy_protocol`, переменная `$remote_addr` будет содержать реальный IP клиента. Таким образом в заголовке X-Forwarded-For будет: `<IP клиента>, <IP nginx>`.

### Итоговая цепочка IP:
```
Клиент (1.2.3.4) → Angie PRO [PROXY protocol] → Nginx ($remote_addr=1.2.3.4) → App
                                                      ↓
                                          X-Forwarded-For: 1.2.3.4, <nginx_ip>
```
