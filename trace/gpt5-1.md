Ниже — готовые сниппеты для NGINX (W3C Trace Context). Они закрывают три сценария:
- прозрачный проброс traceparent/tracestate с логированием;
- добавление своего span-id на прокси;
- создание нового trace-id, если от фронта ничего не пришло.

Примечания
- Используется переменная $request_id для генерации идентификаторов. Она доступна в стандартных сборках NGINX/NGINX Plus при включённом http_request_id_module. В http-блоке добавьте директиву request_id; Если у вас нет модуля — замените $request_id на генерацию через Lua/Perl/Ingress/LB.
- В примерах парсим и проверяем заголовок traceparent: 00-<trace-id>-<parent-span-id>-<flags>.

Общие хелперы (поместите в http {})
```
http {
    # Включить генерацию $request_id (32 hex == 128 бит)
    request_id;

    # Разбор входящего traceparent на части
    map $http_traceparent $tp_valid {
        ~*^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$ 1;
        default 0;
    }
    map $http_traceparent $w3c_trace_id {
        ~*^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$ $1;
        default "";
    }
    map $http_traceparent $w3c_parent_span_id {
        ~*^[0-9a-f]{2}-[0-9a-f]{32}-([0-9a-f]{16})-[0-9a-f]{2}$ $1;
        default "";
    }
    map $http_traceparent $w3c_flags {
        ~*^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-([0-9a-f]{2})$ $1;
        default "01";   # по умолчанию считаем "sampled"
    }

    # Свой span-id на прокси: 16 hex (64 бита) из начала $request_id
    map $request_id $nginx_span_id {
        ~^([0-9a-f]{16}) $1;
        default 0000000000000000; # на всякий случай
    }

    # Сборки готовых traceparent под разные режимы
    # 1) Прозрачный форвард: если валиден — отдаём как есть, иначе пусто
    map $tp_valid $tp_forward {
        1 $http_traceparent;
        0 "";
    }

    # 2) «Добавить свой span»: сохранить trace-id/flags, заменить parent на $nginx_span_id
    map $tp_valid $tp_with_nginx_span {
        1 "00-$w3c_trace_id-$nginx_span_id-$w3c_flags";
        0 "";
    }

    # 3) Если traceparent отсутствует/невалиден — синтезировать новый корневой
    map $tp_valid $tp_synth {
        0 "00-$request_id-$nginx_span_id-01";
        1 "";
    }

    # Удобно иметь единый «итоговый» traceparent: либо с нашим span, либо синтетический
    map $tp_valid $tp_out_final {
        1 "00-$w3c_trace_id-$nginx_span_id-$w3c_flags"; # есть вход — добавили свой span
        0 "00-$request_id-$nginx_span_id-01";           # входа нет — создали новый trace
    }

    # Лог-формат с полями трейсинга
    log_format trace_json escape=json
      '{ "time":"$time_iso8601", "request_id":"$request_id",'
      '  "trace_id":"$w3c_trace_id", "parent_span_id":"$w3c_parent_span_id",'
      '  "nginx_span_id":"$nginx_span_id", "flags":"$w3c_flags", "tp_valid":$tp_valid,'
      '  "method":"$request_method", "uri":"$uri", "status":$status,'
      '  "rt":$request_time, "urt":"$upstream_response_time", "upstream":"$upstream_addr" }';

    # Пример upstream'а
    upstream backend {
        server 127.0.0.1:8080;
    }

    # Далее — три режима в server/location
    ...
}
```

1) Прозрачный проброс + логирование
- Ничего не меняем в заголовках, только пробрасываем, логируем trace_id/parent_span_id.
```
server {
    listen 80;
    access_log /var/log/nginx/access.log trace_json;

    location / {
        proxy_pass http://backend;

        # Прозрачно пробрасываем W3C
        proxy_set_header traceparent $tp_forward;   # если $tp_forward пуст — заголовок не пойдёт
        proxy_set_header tracestate  $http_tracestate;

        # (опционально) проброс X-Request-ID для совместимости
        add_header X-Request-ID $request_id;
        proxy_set_header X-Request-ID $request_id;
    }
}
```

2) Добавить свой span-id на прокси
- NGINX выступает как «прокси-клиент»: сохраняем trace-id и flags, но в исходящий к upstream ставим свой parent-span-id.
- Это даёт «client span» на прокси; для полноценного server+client спана нужен агент/модуль OTel, но для цепочки заголовков этого достаточно.
```
server {
    listen 80;
    access_log /var/log/nginx/access.log trace_json;

    location / {
        proxy_pass http://backend;

        # Если пришёл валидный traceparent — заменяем parent на $nginx_span_id.
        # Если нет — ничего не выставляем (этот сценарий закрыт в пункте 3).
        proxy_set_header traceparent $tp_with_nginx_span;
        proxy_set_header tracestate  $http_tracestate;

        add_header X-Request-ID $request_id;
        proxy_set_header X-Request-ID $request_id;
    }
}
```

3) Создать новый trace-id, если фронт не создал
- Если traceparent отсутствует/неверный — генерируем новый trace-id (берём 32 hex из $request_id) и свой span-id; иначе — как в п.2 (добавляем свой span).
```
server {
    listen 80;
    access_log /var/log/nginx/access.log trace_json;

    location / {
        proxy_pass http://backend;

        # Универсально: либо «наш span поверх входящего», либо «синтетический trace»
        proxy_set_header traceparent $tp_out_final;
        proxy_set_header tracestate  $http_tracestate;

        add_header X-Request-ID $request_id;
        proxy_set_header X-Request-ID $request_id;
    }
}
```

Как проверить (быстро)
- Прозрачный режим:
  curl -H 'traceparent: 00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01' http://host/
  — upstream должен увидеть тот же traceparent; в логах trace_id=aaaaaaaa..., parent_span_id=bbbb....

- «Добавить свой span»:
  тот же запрос, но upstream должен получить:
  traceparent: 00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-<nginx_span_id>-01
  — <nginx_span_id> совпадёт с полем nginx_span_id в логах.

- «Создать новый trace»:
  curl http://host/
  — upstream получит traceparent: 00-<request_id>-<nginx_span_id>-01
  — в логах trace_id заполнится значением $request_id, parent_span_id будет пуст.

Опционально
- Если параллельно нужно поддерживать B3, добавьте прокси-заголовки x-b3-* и/или конвертацию в коллекторе. В чистом NGINX без Lua проще пробрасывать то, что пришло, или генерировать только W3C.
- Для полноценного трейсинга на самом NGINX (server/client spans, экспорты в OTLP) рассмотрите модуль NGINX OpenTelemetry (или агент перед/после NGINX). Тогда не придётся вручную собирать traceparent.

Если подскажете вашу версию NGINX (OSS/Plus) и есть ли Lua/Perl, могу дать эквивалент с криптографической генерацией ID и/или конвертацией B3↔W3C.
