Приведу примеры конфигурации nginx для всех трёх сценариев:

## 1. Прозрачный проброс traceid и spanid с логированием

```nginx
# Определяем переменные для логирования
map $http_traceparent $trace_id {
    ~^00-([a-f0-9]{32})-([a-f0-9]{16})-[0-9]{2}$ $1;
    default "";
}

map $http_traceparent $span_id {
    ~^00-([a-f0-9]{32})-([a-f0-9]{16})-[0-9]{2}$ $2;
    default "";
}

# Альтернативно для B3 headers
map $http_x_b3_traceid $b3_trace_id {
    default $http_x_b3_traceid;
}

map $http_x_b3_spanid $b3_span_id {
    default $http_x_b3_spanid;
}

# Настраиваем формат логов
log_format trace_log '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" '
                    'trace_id=$trace_id span_id=$span_id '
                    'b3_trace=$b3_trace_id b3_span=$b3_span_id';

server {
    listen 80;
    server_name example.com;
    
    # Используем наш формат логирования
    access_log /var/log/nginx/access_trace.log trace_log;
    
    location / {
        # Прозрачно пробрасываем все заголовки трассировки
        proxy_pass http://backend;
        
        # W3C Trace Context
        proxy_set_header traceparent $http_traceparent;
        proxy_set_header tracestate $http_tracestate;
        
        # Zipkin B3
        proxy_set_header X-B3-TraceId $http_x_b3_traceid;
        proxy_set_header X-B3-SpanId $http_x_b3_spanid;
        proxy_set_header X-B3-ParentSpanId $http_x_b3_parentspanid;
        proxy_set_header X-B3-Sampled $http_x_b3_sampled;
        
        # Jaeger
        proxy_set_header uber-trace-id $http_uber_trace_id;
    }
}
```

## 2. Добавление своего spanid (nginx как активный участник)

```nginx
# Генерация случайных spanid для nginx
map $request_id $nginx_span_id {
    ~^(?<p1>[0-9a-f]{8})(?<p2>[0-9a-f]{4})(?<p3>[0-9a-f]{4})(?<p4>[0-9a-f]{4})(?<p5>[0-9a-f]{12})$ "${p3}${p4}${p5}";
}

# Извлекаем данные из W3C traceparent
map $http_traceparent $w3c_trace_id {
    ~^00-([a-f0-9]{32})-([a-f0-9]{16})-[0-9]{2}$ $1;
    default "";
}

map $http_traceparent $w3c_parent_span_id {
    ~^00-([a-f0-9]{32})-([a-f0-9]{16})-[0-9]{2}$ $2;
    default "";
}

map $http_traceparent $w3c_flags {
    ~^00-([a-f0-9]{32})-([a-f0-9]{16})-([0-9]{2})$ $3;
    default "01";
}

# Формируем новый traceparent с нашим spanid
map $w3c_trace_id $new_traceparent {
    "" "";
    default "00-${w3c_trace_id}-${nginx_span_id}-${w3c_flags}";
}

server {
    listen 80;
    server_name example.com;
    
    # Логируем с нашим span
    access_log /var/log/nginx/access_trace.log trace_log;
    
    location / {
        # Добавляем заголовок о том, что это span от nginx
        add_header X-Nginx-Span-Id $nginx_span_id always;
        
        proxy_pass http://backend;
        
        # Передаем новый traceparent с нашим spanid
        proxy_set_header traceparent $new_traceparent;
        proxy_set_header tracestate $http_tracestate;
        
        # Для B3 - обновляем span и сохраняем старый как parent
        proxy_set_header X-B3-TraceId $http_x_b3_traceid;
        proxy_set_header X-B3-SpanId $nginx_span_id;
        proxy_set_header X-B3-ParentSpanId $http_x_b3_spanid;
        proxy_set_header X-B3-Sampled $http_x_b3_sampled;
        
        # Добавляем информацию о nginx в baggage
        proxy_set_header baggage "$http_baggage,nginx.span.id=${nginx_span_id}";
    }
}
```

## 3. Создание нового traceid (если фронт не создал)

```nginx
# Генерация trace_id из request_id (32 hex символа)
map $request_id $generated_trace_id {
    # request_id в nginx - это UUID, убираем дефисы
    ~^(?<p1>[0-9a-f]{8})-?(?<p2>[0-9a-f]{4})-?(?<p3>[0-9a-f]{4})-?(?<p4>[0-9a-f]{4})-?(?<p5>[0-9a-f]{12})$ "${p1}${p2}${p3}${p4}${p5}";
}

# Генерация span_id (16 hex символов)
map $request_id $generated_span_id {
    ~^(?<p1>[0-9a-f]{8})(?<p2>[0-9a-f]{4})(?<p3>[0-9a-f]{4}).*$ "${p1}${p2}${p3}";
}

# Выбираем trace_id: существующий или генерируем новый
map $http_traceparent $final_trace_id {
    ~^00-([a-f0-9]{32})-([a-f0-9]{16})-[0-9]{2}$ $1;
    default $generated_trace_id;
}

map $http_x_b3_traceid $final_b3_trace_id {
    "" $generated_trace_id;
    default $http_x_b3_traceid;
}

# Формируем traceparent
map $http_traceparent $final_traceparent {
    "" "00-${generated_trace_id}-${generated_span_id}-01";
    default $http_traceparent;
}

# Настройка для создания trace context если его нет
server {
    listen 80;
    server_name example.com;
    
    # Логируем все варианты
    set $log_trace_id $final_trace_id;
    set $log_span_id $generated_span_id;
    
    access_log /var/log/nginx/access_trace.log trace_log;
    
    location / {
        # Добавляем заголовок о создании трассировки nginx'ом
        set $trace_created "false";
        if ($http_traceparent = "") {
            set $trace_created "true";
        }
        add_header X-Trace-Created-By-Nginx $trace_created;
        
        proxy_pass http://backend;
        
        # W3C headers
        proxy_set_header traceparent $final_traceparent;
        
        # B3 headers  
        proxy_set_header X-B3-TraceId $final_b3_trace_id;
        proxy_set_header X-B3-SpanId $generated_span_id;
        proxy_set_header X-B3-Sampled "1";
        
        # Jaeger format
        set $jaeger_header "${final_trace_id}:${generated_span_id}:0:1";
        proxy_set_header uber-trace-id $jaeger_header;
        
        # Добавляем в baggage информацию о создании
        proxy_set_header baggage "trace.origin=nginx,trace.created=$trace_created";
    }
}
```

## Комбинированный вариант с OpenTelemetry модулем

```nginx
# Требует установки модуля ngx_otel_module
load_module modules/ngx_otel_module.so;

http {
    # Настройка OpenTelemetry
    opentelemetry_config /etc/nginx/otel-nginx.toml;
    
    server {
        listen 80;
        server_name example.com;
        
        location / {
            # Автоматическая работа с контекстом трассировки
            opentelemetry on;
            opentelemetry_operation_name "nginx-proxy";
            opentelemetry_trust_incoming_spans on;
            
            # Добавляем атрибуты к span
            opentelemetry_attribute "http.request_id" $request_id;
            opentelemetry_attribute "http.scheme" $scheme;
            opentelemetry_attribute "http.method" $request_method;
            
            proxy_pass http://backend;
            
            # OpenTelemetry автоматически обработает propagation
            opentelemetry_propagate;
        }
    }
}
```

Конфигурация `/etc/nginx/otel-nginx.toml`:
```toml
exporter = "otlp"
processor = "batch"

[exporters.otlp]
# Отправка трассировок в коллектор
host = "localhost"
port = 4317

[processors.batch]
max_queue_size = 2048
schedule_delay_millis = 5000

[service]
name = "nginx-proxy"
```

## Полезные дополнения

### Условная трассировка (sampling)
```nginx
# Трассируем только 10% запросов
map $request_id $should_trace {
    ~[0]$ "1";  # если request_id заканчивается на 0
    default "0";
}

location / {
    proxy_set_header X-B3-Sampled $should_trace;
}
```

### Добавление метаданных
```nginx
location / {
    # Добавляем информацию о nginx в baggage
    set $nginx_version $nginx_version;
    set $hostname $hostname;
    proxy_set_header baggage "$http_baggage,nginx.version=${nginx_version},nginx.host=${hostname}";
}
```

Эти конфигурации позволяют гибко управлять трассировкой в nginx в зависимости от ваших потребностей и используемых систем мониторинга.
