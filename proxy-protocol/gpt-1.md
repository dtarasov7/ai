Ниже — рабочий пример **Angie в режиме L4 (stream) на 443/tcp** с балансировкой на 3 upstream-сервера и **активной проверкой доступности (upstream_probe)**. Также учтено, что **upstream nginx ждёт PROXY protocol**, чтобы видеть реальный IP клиента.

> Важно: **`upstream_probe` — это PRO‑функциональность Angie** (в документации помечена как `PRO`). Если у вас не Angie PRO, активные проверки именно таким способом будут недоступны — в конце дам вариант с пассивными проверками. 

---

## 1) Конфигурация Angie (L4 :443 → 3 upstream) + active health check + PROXY protocol к upstream

```nginx
# /etc/angie/angie.conf  (пример)

worker_processes auto;

events {
    worker_connections  8192;
}

stream {
    # (необязательно) лог, полезно для отладки L4
    log_format stream_main
        '$remote_addr:$remote_port -> $server_addr:$server_port '
        'upstream=$upstream_addr status=$status '
        'bytes_in=$bytes_received bytes_out=$bytes_sent session=$session_time';

    access_log /var/log/angie/stream_443.log stream_main;

    # --- Upstream группа (реальный HTTPS/TLS трафик идёт на 443) ---
    upstream web_tls_443 {
        # ОБЯЗАТЕЛЬНО для upstream_probe: нужна shared memory zone 
        zone web_tls_443 1m;

        # Для L4/длинных TLS-сессий часто уместен least_conn
        least_conn; 

        # 3 nginx upstream-а (имена/IP замените на свои)
        server 10.0.10.11:443 max_fails=2 fail_timeout=5s;
        server 10.0.10.12:443 max_fails=2 fail_timeout=5s;
        server 10.0.10.13:443 max_fails=2 fail_timeout=5s;
    }

    # --- Логика "успешности" active health check ---
    # upstream_probe кладёт ответ в $upstream_probe_response 
    map $upstream_probe_response $probe_ok {
        ~200     "1";
        default  "";
    }

    # --- L4 listener на 443 ---
    server {
        listen 0.0.0.0:443;

        # Балансируем TCP (TLS passthrough) на upstream группу:
        proxy_pass web_tls_443;

        # КРИТИЧНО: отправляем PROXY protocol к upstream nginx,
        # чтобы он получил реальный IP/port клиента 
        proxy_protocol on; 
        # (опционально) proxy_protocol_version 2;  # если хотите PROXY v2 

        # Таймауты / фейловер на следующий upstream при невозможности коннекта 
        proxy_connect_timeout 1s;
        proxy_timeout         1h;

        proxy_next_upstream on;             # пробовать следующий upstream, если коннект не установился 
        proxy_next_upstream_tries 3;        # не более 3 попыток 
        proxy_next_upstream_timeout 2s;     # ограничение по времени на эти попытки 

        # ---------------------------
        # ACTIVE health check (upstream_probe)
        # ---------------------------
        upstream_probe_timeout 2s;  # сколько держать idle-соединение, созданное для probes 

        # Практичный подход для TLS passthrough:
        # проверять НЕ 443 (где TLS), а отдельный health-port на каждом upstream (например 8080),
        # на котором nginx отдаёт простой HTTP 200.
        upstream_probe web_health
            port=8080
            interval=5s
            test=$probe_ok
            essential          # не слать клиентский трафик на upstream, пока probe не пройден 
            fails=3
            passes=2
            max_response=4k
            mode=always
            "send=data:GET /healthz HTTP/1.0\r\nHost: localhost\r\n\r\n";
    }
}
```

### Почему probe лучше делать на отдельном порту, а не на 443?
Потому что на 443 у вас **TLS passthrough** (Angie не терминирует TLS), а `upstream_probe` в stream-шлюзе по сути работает как **TCP/UDP probe с опцией “send/read/test”**. Отправить “GET /” в чистом виде на TLS‑порт обычно бессмысленно (это не TLS‑handshake). Поэтому самый простой и надёжный вариант — **поднять на upstream nginx отдельный plain HTTP health endpoint** (например `:8080/healthz`) и проверять его. Сам `upstream_probe` прямо поддерживает альтернативный порт через `port=...`. 

---

## 2) Минимальная подсказка для upstream nginx (чтобы принять PROXY protocol и увидеть IP клиента)

Вы просили конфиг Angie, но чтобы вся схема “завелась”, на **upstream nginx** на 443 обычно нужно:

```nginx
server {
    listen 443 ssl proxy_protocol;   # принять PROXY до TLS 

    # доверяем PROXY только от Angie (укажите IP/подсеть балансировщика)
    set_real_ip_from 10.0.0.5;       # пример
    real_ip_header proxy_protocol;    # заменить $remote_addr на адрес из PROXY 

    # ...
}
```

NGINX официально описывает, что для приёма PROXY нужно добавить `proxy_protocol` в `listen`, и что для подмены `$remote_addr` на реальный клиентский IP используется `real_ip_header proxy_protocol`. 

---

## 3) Если у вас НЕ Angie PRO (нет upstream_probe)
Тогда “активной” проверки средствами Angie не будет, но можно:
- оставить **пассивные проверки** через `max_fails`/`fail_timeout` в upstream (Angie/NGINX исключают сервер при серии неудачных попыток соединения), 
- плюс внешний health-check (Prometheus/Consul/скрипт), который дергает API/переключает `down` и делает reload.

Пассивная схема — это не “пинг каждые N секунд”, а реакция на реальные ошибки при подключениях клиентов.

---

Если захотите, можно усилить решение без TLS-терминации:
- делать health check ICMP (`ping`) в `upstream_probe` (если Angie собран с нужным флагом; в доках указана совместимость/ограничения), 
- или проверять именно TLS (но это уже требует probe, который отправляет валидный TLS ClientHello — обычно сложнее, чем отдельный health-port).
