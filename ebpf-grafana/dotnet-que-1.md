## OBI vs Beyla: можно ли использовать OBI

Да, **можно и даже рекомендуется** использовать OBI (OpenTelemetry eBPF Instrumentation) вместо Beyla. Вот ключевые моменты:[1][2]

### Связь между проектами

Grafana Labs передала Beyla в проект OpenTelemetry в 2025 году, и теперь она стала основой для OBI. Beyla продолжает существовать как **дистрибутив Grafana Labs от upstream OBI проекта** — точно так же, как Grafana Alloy является дистрибутивом OpenTelemetry Collector.[2][3][1]

### Ключевые различия

**OBI (OpenTelemetry eBPF Instrumentation)**:[4][5]
- Vendor-нейтральный проект под OpenTelemetry
- Первый alpha релиз вышел в ноябре 2025 года[1]
- Поддержка протоколов: HTTP/1.1, HTTP/2, gRPC, Kafka, Redis, SQL[3]
- Базовая конфигурация через OTLP endpoint

**Beyla**:[2][3]
- Содержит все функции OBI + Grafana-специфичные интеграции
- Упрощенная интеграция с Grafana Cloud и Grafana Alloy[3]
- Более зрелый продукт (релиз с ноября 2023)[3]
- Дополнительные функции, не подходящие для vendor-нейтрального проекта

### Рекомендация для вашего случая

Для systemd-окружения с .NET Core на Linux:

1. **Если используете Grafana Cloud/Alloy** — выбирайте Beyla для более простой настройки[2]
2. **Если используете другой OTLP backend** (Tempo, Jaeger, другие vendors) — OBI будет чище, так как это vendor-нейтральный проект[5]
3. **Если нужна максимальная стабильность** — пока Beyla более зрелый (OBI в alpha)[1]

## Что такое queue time (время в очереди)

Queue time — это **время ожидания запроса между моментом получения его load balancer/web server и началом фактической обработки application кодом**.[6]

### Архитектура веб-сервера и очереди

Типичный путь HTTP-запроса в .NET Core приложении:

```
Client → Load Balancer → Kestrel Web Server → Thread Pool Queue → Application Handler
         ^                                      ^                   ^
         |                                      |                   |
    eBPF видит здесь                     Очередь здесь        SDK видит здесь
    (начало запроса)                                          (начало обработки)
```

### Когда возникает queue time

1. **Перегрузка worker threads**: Если все потоки в thread pool заняты обработкой других запросов, новый запрос встает в очередь и ждет освобождения потока.[6]

2. **Ограниченное количество application processes**: В случае Kestrel с ограниченным числом concurrent connections, запросы буферизуются.[6]

3. **Медленные клиенты**: Большие request payloads или медленные сетевые соединения увеличивают время нахождения в буфере.[6]

### Почему это критично

**eBPF измеряет на сетевом уровне** :
- Засекает время с момента TCP-подключения
- Видит **полное время = queue time + processing time**
- Это то, что видит клиент (реальная latency)

**SDK (.NET agent) измеряет на application уровне** :
- Засекает время только когда handler начал выполняться
- Видит **только processing time**
- Не включает время ожидания в очереди

### Практический пример

Представьте ситуацию:
```
Ваш .NET сервис настроен с MaxConcurrentRequests = 100
Приходит 150 запросов одновременно

Первые 100 запросов:
- eBPF: latency = 50ms
- SDK: latency = 50ms
(queue time = 0, нет очереди)

Запросы 101-150:
- eBPF: latency = 300ms (250ms ожидание + 50ms обработка)
- SDK: latency = 50ms (видит только обработку)

Разница в 250ms — это queue time, который SDK не видит!
```

### Почему это важно для диагностики

При возникновении проблем с производительностью :

- **SDK покажет**: "Все нормально, обработка занимает 50ms"
- **eBPF покажет**: "Проблема! Клиенты видят 300ms латентность"
- **Вывод**: Проблема не в коде приложения, а в capacity — нужно масштабировать количество воркеров или инстансов

Это одна из главных причин, почему eBPF/OBI дополняет SDK — он дает перспективу с точки зрения клиента, а не приложения.[2]

[1](https://opentelemetry.io/blog/2025/obi-announcing-first-release/)
[2](https://grafana.com/blog/why-opentelemetry-instrumentation-needs-both-ebpf-and-sdks/)
[3](https://www.reddit.com/r/OpenTelemetry/comments/1mnrh1x/grafana_beyla_opentelemetry_ebpf_instrumentation/)
[4](https://opentelemetry.io/docs/zero-code/obi/)
[5](https://last9.io/blog/opentelemetry-ebpf-instrumentation/)
[6](https://judoscale.com/blog/request-queue-time)
[7](https://www.youtube.com/watch?v=u-J3O5nizuE)
[8](https://opentelemetry.io/zh/docs/zero-code/obi/)
[9](https://ithelp.ithome.com.tw/articles/10396661)
[10](https://stackoverflow.com/questions/55646479/high-response-time-vs-queuing)
