Вот пример конфигурации NGINX для логирования информации о трассировке (distributed tracing) в access log. Поскольку формат трассировки неизвестен (W3C Trace Context, B3 от Zipkin или другой, например, от Jaeger/OpenTelemetry), я предлагаю универсальный подход: настроить кастомный формат лога, который захватывает распространённые HTTP-заголовки, используемые в различных системах трассировки. Это позволит логировать релевантные данные независимо от конкретного формата.

NGINX по умолчанию не имеет встроенной поддержки для генерации или распространения tracing-данных (для этого нужны дополнительные модули, такие как `nginx-opentracing` или интеграция с OpenTelemetry). Однако он может легко логировать входящие заголовки в журнал доступа. Если tracing уже передаётся в запросах (например, от клиента или upstream-сервера), NGINX их запишет.

### Шаги по настройке
1. **Убедитесь, что NGINX установлен и работает**. Если нет, следуйте инструкциям с официального сайта (nginx.org) или руководствам по установке (например, из источников вроде serveradmin.ru или firstvds.ru).
2. **Редактируйте конфигурацию**. Основной файл — `/etc/nginx/nginx.conf` (или в виртуальных хостах в `/etc/nginx/conf.d/` или `/etc/nginx/sites-available/`).
3. **Добавьте кастомный log_format**. В нём укажите переменные для ключевых tracing-заголовков:
   - Для W3C: `traceparent`, `tracestate`.
   - Для B3 (Zipkin): `x-b3-traceid`, `x-b3-spanid`, `x-b3-parentspanid`, `x-b3-sampled`.
   - Другие общие: `trace-id`, `span-id` (могут использоваться в кастомных системах).
   - Также полезно логировать стандартные поля, как IP, время, URL и статус.

### Пример конфигурации
Вот фрагмент `nginx.conf` (или отдельного файла конфигурации виртуального хоста). Добавьте это в раздел `http { ... }`:

```
http {
    # Кастомный формат лога для tracing
    log_format tracing '$remote_addr - $remote_user [$time_local] '
                      '"$request" $status $body_bytes_sent '
                      '"$http_referer" "$http_user_agent" '
                      # W3C Trace Context
                      'traceparent: $http_traceparent '
                      'tracestate: $http_tracestate '
                      # B3 (Zipkin)
                      'x-b3-traceid: $http_x_b3_traceid '
                      'x-b3-spanid: $http_x_b3_spanid '
                      'x-b3-parentspanid: $http_x_b3_parentspanid '
                      'x-b3-sampled: $http_x_b3_sampled '
                      # Общие/кастомные (если используются)
                      'trace-id: $http_trace_id '
                      'span-id: $http_span_id';

    # Укажите файл лога и формат
    access_log /var/log/nginx/access_tracing.log tracing;

    # ... (остальные настройки, такие как server { ... })

    server {
        listen 80;
        server_name example.com;

        location / {
            # Здесь может быть proxy_pass или root для вашего приложения
            proxy_pass http://backend;  # Пример: прокси на backend
            # Если нужно пропускать tracing-заголовки на upstream
            proxy_set_header traceparent $http_traceparent;
            proxy_set_header tracestate $http_tracestate;
            proxy_set_header x-b3-traceid $http_x_b3_traceid;
            proxy_set_header x-b3-spanid $http_x_b3_spanid;
            # И т.д. для других заголовков
        }
    }
}
```

### Пояснения
- **log_format tracing**: Определяет структуру строки лога. `$http_<header>` — это переменные NGINX для чтения HTTP-заголовков (имя в нижнем регистре, дефисы заменяются подчёркиваниями).
- **access_log**: Указывает путь к файлу лога и используемый формат. Логи будут храниться в `/var/log/nginx/access_tracing.log` (проверьте права доступа; по умолчанию логи в `/var/log/nginx/`).
- **proxy_set_header**: Если NGINX работает как прокси, это пропустит tracing-заголовки на backend-сервер, чтобы трассировка не прерывалась.
- Если заголовок отсутствует в запросе, в логе будет записан дефис (`-`).

### Как проверить
1. Перезагрузите NGINX: `sudo nginx -s reload` (или `sudo systemctl reload nginx`).
2. Сгенерируйте запрос с tracing-заголовками (например, через curl):
   ```
   curl -H "traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01" http://example.com
   ```
3. Проверьте лог: `tail -f /var/log/nginx/access_tracing.log`. Вы увидите строку с tracing-данными.

### Дополнительные рекомендации
- **Если нужен полный tracing**: Установите модуль `nginx-opentracing` (с поддержкой Jaeger, Zipkin или OpenTelemetry). Для этого соберите NGINX из исходников с `--with-compat` и добавьте динамический модуль. Подробности на nginx.org или в документации OpenTelemetry.
- **Форматы логов**: Если tracing в JSON или другом формате, настройте `log_format` соответственно (NGINX поддерживает escaping для JSON).
- **Безопасность и производительность**: Логирование дополнительных полей может увеличить размер логов. Оптимизируйте, как описано в статьях на habr.com или dev-notes.ru (например, настройте worker_processes и gzip).
- **Источники**: Эта конфигурация основана на официальной документации NGINX (nginx.org/docs) и примерах настройки логов (например, из timeweb.cloud или adminvps.ru).

Если у вас есть больше деталей о системе (например, какой backend или конкретный tracing-инструмент), я могу уточнить конфигурацию!
