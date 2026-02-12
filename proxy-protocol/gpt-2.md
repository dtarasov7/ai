Ниже — вариант, который **реально работает “в рамках ограничений”**:

- **Клиент → Angie PRO (L4, TLS passthrough, порт 443) → 3× Nginx OSS (L7, TLS termination, порт 443) → app:443**
- **Активный health-check на upstream Nginx тоже по 443**, *без отдельного порта*.
- Upstream Nginx **ожидает PROXY protocol** от Angie.
- На Nginx формируем **`X-Forwarded-For: <ip_клиента>, <ip_nginx>`** (без IP Angie).

Ключевой трюк: **делаем отдельный внутренний `stream server` в Angie только для проб**, где включаем **`proxy_ssl on;`** — так probe проверяет не просто “TCP порт открыт”, а что **TLS-рукопожатие с Nginx на 443 действительно проходит**. Это возможно, потому что `upstream_probe` в stream учитывает настройки проксирования в том же `server` (включая `proxy_ssl`, `proxy_protocol` и т.п.). 

---

## 1) Angie PRO: L4 балансировщик на 443 + active probes на 443 (TLS handshake) + PROXY protocol к upstream

```nginx
# /etc/angie/angie.conf (фрагмент)

worker_processes auto;

events { worker_connections 8192; }

stream {
    # --- Upstream группа из 3 nginx L7 прокси на 443 ---
    upstream nginx_l7_443 {
        # обязательно для upstream_probe: shared memory zone
        zone nginx_l7_443 1m;

        # любая стратегия на вкус
        least_conn;

        server 10.0.10.11:443 max_fails=2 fail_timeout=5s;
        server 10.0.10.12:443 max_fails=2 fail_timeout=5s;
        server 10.0.10.13:443 max_fails=2 fail_timeout=5s;
    }

    # -------------------------------------------------------
    # A) “Боевой” L4 listener: принимает клиентский TLS и
    #    прозрачно проксирует на Nginx (TLS passthrough)
    # -------------------------------------------------------
    server {
        listen 0.0.0.0:443 reuseport;

        proxy_pass nginx_l7_443;

        # Nginx upstream ожидает PROXY protocol (до TLS handshake)
        proxy_protocol on;                      # отправлять PROXY к upstream 
        proxy_protocol_version 2;               # опционально, если хотите v2

        proxy_connect_timeout 1s;
        proxy_timeout 1h;

        proxy_next_upstream on;
        proxy_next_upstream_tries 3;
        proxy_next_upstream_timeout 2s;
    }

    # -------------------------------------------------------
    # B) Внутренний server только для health-probe.
    #    ВАЖНО: здесь включаем proxy_ssl on, чтобы probe делал TLS
    #    рукопожатие с Nginx:443 (а не просто TCP connect).
    # -------------------------------------------------------
    server {
        listen 127.0.0.1:9443;   # наружу не публикуем, клиентов тут нет

        proxy_pass nginx_l7_443;

        # upstream Nginx ждёт PROXY protocol
        proxy_protocol on; 

        # Включаем TLS к upstream именно для проверки здоровья (handshake)
        proxy_ssl on; 

        # Если на Nginx несколько server{} по SNI — лучше указать имя:
        proxy_ssl_server_name on; 
        proxy_ssl_name "your-public-name.example.com";  # любой server_name, который есть на nginx

        # Проверку сертификата можно:
        #  - включить и указать CA (более правильно),
        #  - или отключить (проще, но слабее).
        proxy_ssl_verify off; 
        # proxy_ssl_verify on;
        # proxy_ssl_trusted_certificate /etc/ssl/certs/ca-bundle.crt;

        # Если Nginx требует mTLS от клиента на 443 — добавьте:
        # proxy_ssl_certificate     /etc/angie/tls/probe-client.crt;
        # proxy_ssl_certificate_key /etc/angie/tls/probe-client.key; 

        # --- ACTIVE health checks (PRO) ---
        # upstream_probe в stream умеет “создавать тестовые соединения”
        # (и опционально что-то отправлять), нужен zone у upstream. 
        upstream_probe_timeout 2s; 

        upstream_probe nginx_tls_handshake
            interval=5s
            test=1                 # “пройдено”, если соединение (и TLS в этом server) успешны
            essential              # не слать клиентский трафик на upstream, пока probe не пройдён 
            persistent             # переживать reload без “холодного старта” (если было healthy) 
            fails=3
            passes=2
            max_response=0         # не ждём payload-ответ; нам важен сам факт успешного соединения/TLS 
            mode=always;
    }
}
```

### Почему это соответствует вашему кейсу “нет отдельного healthcheck-порта”?
- Probes идут **на тот же порт 443**, что и рабочий трафик.
- Мы **не пытаемся делать HTTP-запрос** (это сложно/неестественно для L4 без терминации), а проверяем “сервер реально жив и умеет TLS на 443”.
- Поскольку probe-сервер в Angie включает `proxy_ssl on;`, успешность probe фактически становится “TLS handshake успешен”. Директива `proxy_ssl` именно для этого и предназначена — включить TLS при соединениях к proxied server. 

---

## 2) Nginx OSS (upstream): принять PROXY protocol на 443 и собрать X-Forwarded-For = “client, nginx”

### 2.1. Принять PROXY protocol и получить IP клиента
На upstream Nginx (L7, TLS termination) нужно слушать так:

```nginx
server {
    listen 443 ssl proxy_protocol;

    # доверяем PROXY protocol только от Angie (его IP/подсеть)
    set_real_ip_from 10.0.0.0/24;
    real_ip_header proxy_protocol;

    # ...
}
```

`proxy_protocol` в `listen` включает приём заголовка PROXY protocol, а `real_ip_header proxy_protocol` заставляет realip-модуль подменять адрес клиента на адрес из PROXY. 

---

### 2.2. Сделать X-Forwarded-For: “IP клиента, IP nginx”
Важно: переменная **`$proxy_add_x_forwarded_for` не “заполняется настройками”**, она вычисляется Nginx-ом как:  
- либо `X-Forwarded-For` из запроса + `,$remote_addr`,  
- либо просто `$remote_addr`, если заголовка не было. 

Если вы включили `real_ip_header proxy_protocol`, то `$remote_addr` становится **IP клиента**. 

Тогда самый прямой способ получить **“клиент, nginx”**:

```nginx
location / {
    proxy_pass https://app_upstream;

    # 1) стандартная часть: добавляем IP клиента (remote_addr после realip)
    # 2) + вручную добавляем IP самого nginx
    proxy_set_header X-Forwarded-For "$proxy_add_x_forwarded_for, $server_addr";

    # (полезно отдельно)
    proxy_set_header X-Real-IP $remote_addr;

    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header Host $host;

    # если app тоже на TLS и важен SNI:
    proxy_ssl_server_name on;
}
```

Почему это работает именно так:
- `$proxy_add_x_forwarded_for` добавляет `$remote_addr` (у вас это будет IP клиента после realip). 
- затем вы вручную приписываете **`$server_addr`** (IP nginx, на который пришёл запрос) как “второй прокси” в цепочке.

#### Важное замечание про безопасность (чтобы клиент не подсовывал свой XFF)
Если вы не хотите доверять входящему `X-Forwarded-For` от клиента вообще (обычно это правильно), можно **не использовать** `$proxy_add_x_forwarded_for`, а собрать цепочку сами из PROXY-protocol IP:

```nginx
proxy_set_header X-Forwarded-For "$proxy_protocol_addr, $server_addr";
```

NGINX документирует, что `$proxy_protocol_addr` содержит исходный IP клиента из PROXY protocol. 

---

## 3) Что в итоге проверяет health-check (и что нет)
С конфигом выше Angie probe будет проверять:

- upstream Nginx **принимает TCP соединение на 443**;
- upstream Nginx **корректно проходит TLS handshake** (потому что в probe-server включён `proxy_ssl on`). 

Но он **не проверяет**, что конкретный HTTP URL на Nginx возвращает 200, потому что Angie на L4 не делает полноценный HTTPS-запрос без терминации.

Если когда-нибудь понадобится именно “HTTPS GET /healthz == 200” без отдельного порта — это уже либо:
- healthcheck на стороне Nginx/app (включая отдельный endpoint), либо
- отдельный L7 балансировщик/терминация TLS на уровне проверяющего.

---
