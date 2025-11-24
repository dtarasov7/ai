Если вы хотите логировать информацию о трассировке (tracing) в Nginx, но не знаете заранее, какой заголовок используется (например, `traceparent` для W3C Trace Context, `X-B3-TraceId` для B3 и т.д.), можно настроить логирование всех возможных заголовков трассировки одновременно. Это позволит захватить данные независимо от используемого формата.

Вот пример конфигурации Nginx:

```nginx
# Определяем кастомный лог-формат, включающий потенциально используемые заголовки трассировки
log_format tracing '$remote_addr - $remote_user [$time_local] '
                   '"$request" $status $body_bytes_sent '
                   '"$http_referer" "$http_user_agent" '
                   'traceparent="$http_traceparent" '
                   'x_b3_traceid="$http_x_b3_traceid" '
                   'x_b3_spanid="$http_x_b3_spanid" '
                   'x_request_id="$http_x_request_id" '
                   'ot_traceid="$http_ot_traceid" '
                   'uber_trace_id="$http_uber_trace_id"';

# Применяем этот формат к нужному серверу или location
server {
    listen 80;
    server_name example.com;

    access_log /var/log/nginx/access.log tracing;

    location / {
        # ваша основная конфигурация
        proxy_pass http://backend;
    }
}
```

### Пояснение:
- **`$http_<заголовок>`** — в Nginx переменные вида `$http_*` содержат значения HTTP-заголовков, приведённых к нижнему регистру и с заменой дефисов на подчёркивания.
- Мы включаем заголовки от разных стандартов:
  - **W3C Trace Context**: `traceparent`
  - **Zipkin/B3**: `X-B3-TraceId`, `X-B3-SpanId`
  - **OpenTracing (старые реализации)**: `X-Request-Id`, `Ot-Traceid`
  - **Jaeger**: `Uber-Trace-Id`

Если какой-то заголовок не передан, в логе будет просто пустое значение (например, `x_b3_traceid=""`).

### Дополнительно:
Если вы используете **OpenTelemetry Collector** или подобные инструменты, часто используется именно `traceparent` (W3C). Но для совместимости со старыми системами разумно логировать все возможные варианты.

Если нужно **проксировать** эти заголовки дальше (а не только логировать), убедитесь, что они не удаляются — по умолчанию Nginx не удаляет заголовки, но если вы используете `proxy_set_header`, может потребоваться явно их передавать:

```nginx
location / {
    proxy_pass http://backend;
    proxy_set_header Traceparent $http_traceparent;
    proxy_set_header X-B3-TraceId $http_x_b3_traceid;
    proxy_set_header X-B3-SpanId $http_x_b3_spanid;
    # и т.д.
}
```

Но для **только логирования** это не обязательно.

Такой подход покрывает большинство популярных форматов трассировочных заголовков.
