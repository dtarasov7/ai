Для реализации этой схемы необходимо учесть специфику работы протокола PROXY на обоих концах (отправка на Angie, прием на Nginx) и правильно сформировать цепочку заголовков.

Тонкий момент вашей задачи — **Health Check на порт, ожидающий PROXY-протокол**. Если Angie просто постучится по TCP (SYN/ACK) на порт 443 бэкенда, а бэкенд ждет заголовок PROXY перед SSL рукопожатием, проверка может зависнуть или завершиться ошибкой в логах бэкенда.
В **Angie** (как и в Nginx Plus) это решается добавлением параметра `proxy_protocol` в директиву проверки здоровья.

Ниже приведены конфигурации для Angie (L4) и Nginx (L7).

---

### 1. Конфигурация Angie PRO (L4 Балансировщик)

Файл: `/etc/angie/angie.conf` (или в `stream.conf.d/`)

Angie работает на уровне TCP (`stream`). Он принимает соединение, добавляет PROXY-заголовок и пробрасывает дальше.

```nginx
stream {
    upstream nginx_layer_l7 {
        # Зона памяти обязательна для health_check
        zone nginx_layer_l7 64k;

        server 10.0.0.10:443;
        server 10.0.0.11:443;
        server 10.0.0.12:443;
    }

    server {
        listen 443; # Слушаем TCP
        
        # Пробрасываем трафик на группу серверов
        proxy_pass nginx_layer_l7;

        # Включаем отправку PROXY protocol (v2 - бинарный, предпочтительно)
        # Это передаст реальный IP клиента в Nginx L7
        proxy_protocol on; 

        # Настройки тайм-аутов соединения
        proxy_connect_timeout 5s;
        proxy_timeout 10m;

        # АКТИВНАЯ ПРОВЕРКА ДОСТУПНОСТИ (Health Check)
        # proxy_protocol - ключевой параметр!
        # Он заставляет Angie отправлять PROXY-заголовок (со своим IP) во время проверки.
        # Без этого Nginx L7 разорвет соединение с ошибкой, так как ждет заголовок.
        health_check interval=5s passes=2 fails=3 proxy_protocol;
    }
}
```

---

### 2. Конфигурация Upstream Nginx OSS (L7 Прокси)

Файл: `/etc/nginx/conf.d/default.conf`

Здесь мы принимаем PROXY протокол, расшифровываем SSL, подменяем IP клиента на реальный (полученный от Angie) и формируем сложный заголовок `X-Forwarded-For` для App.

```nginx
http {
    # --- Блок RealIP ---
    # Доверяем IP-адресу Angie (укажите здесь IP вашего Angie сервера)
    set_real_ip_from 192.168.100.5;  # <-- IP Angie
    # Указываем, что реальный IP нужно брать из PROXY протокола
    real_ip_header proxy_protocol; 

    upstream app_backend {
        server 10.0.1.50:443;
    }

    server {
        # listen 443 ssl proxy_protocol обязателен, чтобы принять соединение от Angie
        listen 443 ssl proxy_protocol;
        
        server_name example.com;

        # SSL сертификаты (так как здесь происходит SSL termination)
        ssl_certificate     /etc/nginx/ssl/server.crt;
        ssl_certificate_key /etc/nginx/ssl/server.key;

        location / {
            # Проксируем запрос в App (по HTTPS)
            proxy_pass https://app_backend;
            
            # Включаем SSL SNI, если App этого требует
            proxy_ssl_server_name on;

            # --- Формирование заголовков ---
            
            # Передаем Host
            proxy_set_header Host $host;

            # ЗАДАЧА: Передать IP Клиента + IP Nginx в X-Forwarded-For
            
            # $remote_addr — это IP клиента (благодаря модулю RealIP и proxy_protocol)
            # $server_addr — это IP этого сервера Nginx
            
            # Вариант 1 (Ручное формирование строки):
            # В App придет: "1.2.3.4, 10.0.0.10"
            proxy_set_header X-Forwarded-For "$remote_addr, $server_addr";

            # Вариант 2 (Стандартный):
            # $proxy_add_x_forwarded_for содержит IP клиента. 
            # Стандарт поведения прокси — добавлять СЕБЯ в список не принято в XFF (обычно добавляется клиент),
            # но если App требует строго список узлов, используйте Вариант 1.
            # Если использовать proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; 
            # то App увидит только IP клиента, так как Angie (L4) не добавлял HTTP заголовков.
        }
    }
}
```

### Разбор механики работы

1.  **Клиент (IP: `C`)** подключается к **Angie (IP: `A`)** на порт 443.
2.  **Angie** выбирает **Nginx (IP: `N`)**, устанавливает TCP соединение и первым делом шлет бинарный заголовок: `PROXY TCP4 C A ...`.
3.  **Nginx** получает соединение. Благодаря `listen ... proxy_protocol`, он считывает этот заголовок.
4.  Благодаря `set_real_ip_from A` и `real_ip_header proxy_protocol`, Nginx меняет переменную `$remote_addr` с `A` на `C`.
5.  **Health Check**: Angie раз в 5 секунд открывает соединение к Nginx. Благодаря флагу `health_check ... proxy_protocol`, Angie шлет `PROXY TCP4 A N ...`. Nginx видит валидный заголовок и принимает соединение (или отдает SSL handshake), проверка проходит успешно (статус UP).
6.  **Отправка в App**:
    *   Nginx выполняет `proxy_set_header X-Forwarded-For "$remote_addr, $server_addr";`.
    *   Переменная `$remote_addr` равна `C`.
    *   Переменная `$server_addr` равна `N`.
    *   В App улетает заголовок: `X-Forwarded-For: C, N`.
