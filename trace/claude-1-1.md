Вот универсальная конфигурация nginx для логирования всех популярных форматов трассировки:

```nginx
http {
    # Определяем формат лога с поддержкой множества форматов трассировки
    log_format trace_log escape=json '{'
        '"time": "$time_iso8601",'
        '"remote_addr": "$remote_addr",'
        '"request": "$request",'
        '"status": $status,'
        '"body_bytes_sent": $body_bytes_sent,'
        '"request_time": $request_time,'
        '"upstream_response_time": "$upstream_response_time",'
        
        # W3C Trace Context
        '"traceparent": "$http_traceparent",'
        '"tracestate": "$http_tracestate",'
        
        # B3 (Zipkin) - single header
        '"b3": "$http_b3",'
        
        # B3 (Zipkin) - multi header
        '"x_b3_traceid": "$http_x_b3_traceid",'
        '"x_b3_spanid": "$http_x_b3_spanid",'
        '"x_b3_parentspanid": "$http_x_b3_parentspanid",'
        '"x_b3_sampled": "$http_x_b3_sampled",'
        '"x_b3_flags": "$http_x_b3_flags",'
        
        # Jaeger
        '"uber_trace_id": "$http_uber_trace_id",'
        
        # AWS X-Ray
        '"x_amzn_trace_id": "$http_x_amzn_trace_id",'
        
        # Google Cloud Trace
        '"x_cloud_trace_context": "$http_x_cloud_trace_context",'
        
        # Datadog
        '"x_datadog_trace_id": "$http_x_datadog_trace_id",'
        '"x_datadog_parent_id": "$http_x_datadog_parent_id",'
        
        # Generic correlation ID
        '"x_request_id": "$http_x_request_id",'
        '"x_correlation_id": "$http_x_correlation_id"'
    '}';

    server {
        listen 80;
        server_name example.com;

        # Используем формат trace_log
        access_log /var/log/nginx/trace_access.log trace_log;

        # Пробрасываем все заголовки трассировки в upstream
        location / {
            # W3C Trace Context
            proxy_set_header traceparent $http_traceparent;
            proxy_set_header tracestate $http_tracestate;
            
            # B3
            proxy_set_header b3 $http_b3;
            proxy_set_header X-B3-TraceId $http_x_b3_traceid;
            proxy_set_header X-B3-SpanId $http_x_b3_spanid;
            proxy_set_header X-B3-ParentSpanId $http_x_b3_parentspanid;
            proxy_set_header X-B3-Sampled $http_x_b3_sampled;
            proxy_set_header X-B3-Flags $http_x_b3_flags;
            
            # Jaeger
            proxy_set_header uber-trace-id $http_uber_trace_id;
            
            # AWS X-Ray
            proxy_set_header X-Amzn-Trace-Id $http_x_amzn_trace_id;
            
            # Google Cloud
            proxy_set_header X-Cloud-Trace-Context $http_x_cloud_trace_context;
            
            # Datadog
            proxy_set_header X-Datadog-Trace-Id $http_x_datadog_trace_id;
            proxy_set_header X-Datadog-Parent-Id $http_x_datadog_parent_id;
            
            # Generic
            proxy_set_header X-Request-ID $http_x_request_id;
            proxy_set_header X-Correlation-ID $http_x_correlation_id;

            proxy_pass http://backend;
        }
    }
}
```

**Ключевые особенности:**

1. **JSON формат** - удобен для парсинга и анализа
2. **Все популярные форматы** трассировки:
   - W3C Trace Context (современный стандарт)
   - B3 (Zipkin) - оба варианта (single и multi header)
   - Jaeger
   - AWS X-Ray
   - Google Cloud Trace
   - Datadog

3. **Проброс заголовков** в upstream сервисы

**Альтернатива - минималистичный вариант:**

Если хотите более компактные логи, можно логировать только непустые значения с помощью условного логирования или использовать этот упрощенный формат:

```nginx
log_format trace_simple '$remote_addr - [$time_local] "$request" $status '
                        'trace: $http_traceparent$http_b3$http_x_b3_traceid$http_uber_trace_id';
```

Это позволит увидеть, какой именно заголовок присутствует, без избыточного логирования пустых полей.
