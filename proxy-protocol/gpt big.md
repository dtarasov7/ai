- Вопрос -------------------------------
Клиент (dst port 443; Tls) → Angie PRO (балансировщик L4) (dst port 443; Tls) → Nginx oss (прокси L7)dst port 443; Tls) → app (порт 443)
Покажи конфигурацию Angie для использования его в как балансировщика L4 ( порт 443) на три upsteam сервера nginx с активной проверкой доступности upstream. 

Учти, что upstream сервер (nginx) настроен на прием информации об IP клиента ( протокол PROXY) и Angie тоже должен использовать протокол Proxy. 
--------------------------------


Ниже пример Angie PRO в роли L4 TCP-балансировщика на 443 (TLS passthrough), с 3 upstream nginx:443, с активной проверкой доступности и PROXY protocol к upstream (чтобы nginx видел реальный IP клиента).

Ключевая логика:

клиент → Angie: обычный TCP/TLS (без PROXY protocol)

Angie → nginx: TCP + префикс PROXY protocol (proxy_protocol on;), затем уже TLS-handshake клиента как есть (passthrough)

Пример /etc/angie/angie.conf (или include в conf.d/stream-443.conf)
# Важно: нужен stream-контекст (L4)
stream {

    # (необязательно, но удобно) лог с реальным адресом клиента
    log_format stream_main '$remote_addr:$remote_port -> $upstream_addr '
                           'status=$status bytes_out=$bytes_sent bytes_in=$bytes_received '
                           'session=$session_time';

    access_log /var/log/angie/stream-443.log stream_main;

    # Upstream группа из 3 nginx (каждый слушает 443 и ожидает PROXY protocol)
    upstream nginx_tls_443 {
        # zone рекомендуется/часто нужна для разделяемого состояния upstream (в т.ч. для probe/health)
        zone nginx_tls_443 1m;

        server 10.0.0.11:443;
        server 10.0.0.12:443;
        server 10.0.0.13:443;
    }

    server {
        listen 443;  # клиент подключается напрямую по TLS, поэтому proxy_protocol тут НЕ включаем

        proxy_pass nginx_tls_443;

        # ВКЛЮЧАЕМ PROXY protocol на соединении Angie -> upstream nginx
        proxy_protocol on;
        proxy_protocol_version 2;  # можно 1, но v2 удобнее (TLV и т.п.)

        # Поведение при недоступности upstream (на уровне TCP connect)
        proxy_next_upstream on;
        proxy_next_upstream_tries 3;
        proxy_next_upstream_timeout 3s;

        proxy_connect_timeout 1s;
        proxy_timeout 1h;

        # ---------- Active health checks (PRO) ----------
        # Таймаут "простой" probe-соединения (если оно держится)
        upstream_probe_timeout 5s;

        # Активная проверка upstream: TCP connect к 443.
        # max_response=0 => не ждём ответ (для TLS passthrough это обычно то, что нужно)
        upstream_probe nginx_tls_443_probe
            port=443
            interval=5s
            fails=3
            passes=2
            essential
            max_response=0
            mode=always;
    }
}

Что важно учесть на стороне upstream nginx

На каждом nginx-upstream должен быть listener примерно такого вида (упрощённо), чтобы он принимал PROXY protocol:

server {
    listen 443 ssl proxy_protocol;
    real_ip_header proxy_protocol;
    set_real_ip_from 10.0.0.0/24;  # адреса/подсеть Angie
    ...
}

Почему именно так

proxy_protocol on; в stream-server включает отправку PROXY protocol к proxied server.

upstream_probe ... (PRO) — это активные проверки upstream в stream; параметры fails/passes/interval/mode/max_response задают поведение probe.

max_response=0 отключает ожидание ответа (т.е. проверка фактически “connect-only”), что подходит для TCP/TLS passthrough.

upstream ... zone ...; — стандартный способ описать группу upstream в stream (и хранить состояние в shared memory).

Если хочешь, могу дать вариант, где health-check проверяет не просто TCP connect, а, например, TLS-handshake (через send= с подготовленным payload) — но для большинства кейсов “connect-only” на 443 достаточно, чтобы выкидывать реально недоступные ноды.


-- Вопрос ------------------------------
Усложним схему.
Клиент (dst port 443; Tls) → Angie PRO 1 (балансировщик L4) (dst port 443; Tls)→ 3 x Angie PRO 2 (балансировщик L4) (dst port 443; Tls) → 2 x Nginx oss (прокси L7)dst port 443; Tls) → 4 x app (порт 443)

Покажи конфиг для angie 1, для которого upstream - это также L4 балансировщики.
--------------------------------


Ниже пример конфига для Angie PRO 1 (первый уровень), где upstream — это 3 узла Angie PRO 2, и при этом Angie1 передаёт реальный IP клиента дальше через PROXY protocol.

Angie PRO 1 — L4 TCP LB на 443 → 3×Angie PRO 2 (TLS passthrough + PROXY protocol)
# /etc/angie/angie.conf (или отдельный include в conf.d/stream-443.conf)

stream {

    log_format stream_main '$remote_addr:$remote_port -> $upstream_addr '
                           'status=$status bytes_out=$bytes_sent bytes_in=$bytes_received '
                           'session=$session_time';
    access_log /var/log/angie/stream-443-lb1.log stream_main;

    upstream angie2_tls_443 {
        zone angie2_tls_443 1m;

        # 3 x Angie PRO 2 (каждый слушает 443 и УМЕЕТ принимать PROXY protocol)
        server 10.0.1.11:443;
        server 10.0.1.12:443;
        server 10.0.1.13:443;
    }

    server {
        listen 443;     # клиент приходит обычным TLS TCP (без proxy_protocol на входе)

        # Балансируем TCP 443 на Angie2
        proxy_pass angie2_tls_443;

        # ВАЖНО: отправляем PROXY protocol на Angie2, чтобы он знал реальный IP клиента
        proxy_protocol on;
        proxy_protocol_version 2;

        # failover по TCP connect
        proxy_next_upstream on;
        proxy_next_upstream_tries 3;
        proxy_next_upstream_timeout 3s;

        proxy_connect_timeout 1s;
        proxy_timeout 1h;

        # ---- Active health checks до Angie2 (PRO) ----
        # для TLS passthrough обычно достаточно "connect-only" на 443
        upstream_probe_timeout 5s;

        upstream_probe angie2_probe
            port=443
            interval=5s
            fails=3
            passes=2
            essential
            max_response=0
            mode=always;
    }
}

Что обязательно должно быть на Angie PRO 2 (чтобы схема работала)

Раз ты хочешь прокинуть IP клиента до nginx L7 дальше по цепочке, Angie2 должен:

Принимать PROXY protocol от Angie1 на входе (иначе первая строка PROXY “сломает” TLS-handshake).
То есть на Angie2 в stream server должно быть примерно так:

stream {
  server {
    listen 443 proxy_protocol;   # <-- принимает PROXY protocol от Angie1
    # ... proxy_pass дальше на nginx oss ...
  }
}


И дальше, при проксировании на nginx oss, Angie2 тоже должен включить proxy_protocol on;, чтобы nginx видел IP клиента (как ты делал в исходной схеме).

Если хочешь, могу сразу набросать минимальные “сквозные” конфиги Angie2 и nginx oss для этой многоуровневой цепочки, чтобы было видно, где именно включаются listen ... proxy_protocol и где proxy_protocol on;.

-- Вопрос  ------------------------------

Насколько я понял из документации angie конструкция
 upstream_probe angie2_probe
            port=443
            interval=5s
            fails=3
            passes=2
            essential
            max_response=0
            mode=always;
Проверяет доступность посылая  запрос http GET
Но ведь angie2 - это  L4 балансировщик ...
Может ли angire просто проверять возможность установления TCP соединения с upstream ?

--------------------------------


Да — может.

Ты правильно заметил, что в примере документации используется send=data:GET / ... (то есть кто-то может настроить probe как HTTP-GET), но это не означает, что upstream_probe по умолчанию шлёт HTTP.

В stream-модуле upstream_probe — это активная проверка для stream_upstream, где:

по умолчанию используется TCP (UDP — только если указан параметр udp)

параметр send= — это произвольные данные, которые опционально отправляются в probe; GET в документации — просто пример

если указать max_response=0, то ожидание ответа отключается

То есть для L4-балансировщика (Angie2 как upstream) ты можешь сделать чистый TCP connect-check: соединение установилось → probe успешен; не установилось → probe провален.

Пример “TCP connect only” probe для Angie1 → Angie2:443
stream {
  upstream angie2_tls_443 {
    zone angie2_tls_443 1m;
    server 10.0.1.11:443;
    server 10.0.1.12:443;
    server 10.0.1.13:443;
  }

  server {
    listen 443;
    proxy_pass angie2_tls_443;

    upstream_probe_timeout 5s;

    upstream_probe angie2_tcp_probe
      port=443
      interval=5s
      fails=3
      passes=2
      essential
      max_response=0
      mode=always;
      # ВАЖНО: нет send= ... => ничего “HTTP-шного” не шлём
  }
}


Если тебе нужно не просто “порт открыт”, а именно “TLS-терминация на конце жива” — тогда одной проверкой connect это не гарантировать; но для контроля доступности L4-узлов (Angie2) connect-check обычно как раз то, что нужно.
