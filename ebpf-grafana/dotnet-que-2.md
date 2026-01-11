Да, в .NET метриках **можно увидеть признаки очереди**, но это зависит от версии .NET и типа очереди.[1][2][3]

## Метрики для обнаружения очередей в .NET

### 1. Thread Pool Queue Length (с .NET 9)

Метрика `dotnet.thread_pool.queue.length` показывает количество рабочих элементов, ожидающих выполнения в thread pool:[2]

```
# TYPE dotnet_thread_pool_queue_length gauge
dotnet_thread_pool_queue_length{} 45
```

Эта метрика эквивалентна вызову `ThreadPool.PendingWorkItemCount`. Если значение растет — это прямой индикатор, что запросы стоят в очереди, ожидая свободного потока.[2]

**Ограничение**: Доступна только начиная с .NET 9.[2]

### 2. HTTP Client Request Time in Queue (с .NET 8)

Метрика `http.client.request.time_in_queue` измеряет время, которое HTTP-запросы проводят в очереди перед отправкой по сети:[4][3]

```
# TYPE http_client_request_time_in_queue histogram
http_client_request_time_in_queue_bucket{le="0.005"} 100
http_client_request_time_in_queue_bucket{le="0.01"} 150
http_client_request_time_in_queue_bucket{le="0.025"} 180
```

Это измеряет queue time **для исходящих запросов** (когда ваш сервис вызывает другие сервисы), но не для входящих.[3]

### 3. Косвенные индикаторы для входящих запросов

Для входящих HTTP-запросов в .NET нет прямой метрики "request queue depth", но есть косвенные индикаторы:[1]

#### Thread Pool Metrics (с .NET 8+)

```
# Количество активных потоков
dotnet.thread_pool.thread.count

# Количество завершенных элементов
dotnet.thread_pool.completed_items.count
```

**Признаки проблемы**: Если `thread_count` стабилизировался на высоком уровне (более чем 3× количество ядер процессора), это признак thread pool starvation.[5]

#### Kestrel Connection Queue Length

Kestrel не экспортирует метрику глубины очереди подключений напрямую в Prometheus формате, но вы можете видеть косвенные признаки через:[6][1]

```
# Текущие активные подключения
kestrel_active_connections

# Общее количество подключений
kestrel_total_connections

# Длина очереди подключений (требует кастомной инструментации)
kestrel_connection_queue_length
```

## Что НЕ показывают стандартные .NET метрики

**Критическое ограничение**: Стандартные метрики .NET не показывают **полное время ожидания запроса между TCP accept и началом обработки handler'ом** .

Метрика `http.server.request.duration` в ASP.NET Core измеряет "time to last byte", но начинает отсчет **только когда request pipeline начал обрабатывать запрос**, а не когда TCP-соединение было установлено.[4]

## Сравнение: что видит .NET vs eBPF

| Метрика | .NET Metrics | eBPF/OBI |
|---------|--------------|----------|
| Thread pool queue length | ✅ (.NET 9+) [2] | ❌ |
| HTTP client queue time | ✅ (.NET 8+) [3] | ❌ |
| **HTTP server queue time** | ❌ | ✅ |
| TCP connection latency | ❌ | ✅ |
| Network-level timing | ❌ | ✅ |
| Time client actually sees | ❌ | ✅ |

## Практический пример проблемы

Предположим, ваш .NET сервис перегружен:

**Что покажут .NET метрики**:
```
http_server_request_duration_seconds{code="200"} 0.05  # 50ms
dotnet_thread_pool_queue_length 150                    # Очередь есть!
dotnet_thread_pool_thread_count 64                     # Много потоков
```

Вы видите, что есть очередь в thread pool, но **не видите, как это влияет на реальную latency клиентов** .

**Что покажет eBPF/OBI**:
```
http_server_request_duration_seconds{code="200"} 0.35  # 350ms
```

eBPF показывает, что клиенты видят 350ms латентность (50ms обработка + 300ms ожидание в очереди) .

## Рекомендации для мониторинга

Для полной картины используйте **комбинацию**:

1. **Thread pool метрики из .NET** — для диагностики внутреннего состояния application[2]
2. **eBPF/OBI метрики** — для измерения real user experience 
3. **Алерты на разрыв между ними** — если eBPF показывает высокую latency, а .NET показывает нормальную обработку + большую очередь — это четкий сигнал к масштабированию

В .NET 9+ вы получаете лучшую видимость внутренних очередей, но eBPF все равно остается единственным способом измерить **что реально видит клиент на сетевом уровне**.[7][2]

[1](https://learn.microsoft.com/en-us/aspnet/core/log-mon/metrics/metrics?view=aspnetcore-10.0)
[2](https://learn.microsoft.com/en-us/dotnet/core/diagnostics/built-in-metrics-runtime)
[3](https://learn.microsoft.com/en-us/dotnet/core/diagnostics/built-in-metrics-system-net)
[4](https://opentelemetry.io/docs/specs/semconv/dotnet/dotnet-http-metrics/)
[5](https://learn.microsoft.com/en-us/dotnet/core/diagnostics/debug-threadpool-starvation)
[6](https://grafana.com/grafana/dashboards/23178-kestrel-metrics/)
[7](https://grafana.com/blog/why-opentelemetry-instrumentation-needs-both-ebpf-and-sdks/)
[8](https://github.com/prometheus-net/prometheus-net)
[9](https://stackoverflow.com/questions/75879540/how-long-metrics-endpoint-retain-data-for-prometheus-net-core-client-applicatio)
[10](https://hamedsalameh.com/adding-metrics-to-an-asp-net-core-application-easily/)
[11](https://github.com/prometheus-net/prometheus-net/blob/master/Prometheus.AspNetCore/KestrelMetricServer.cs)
