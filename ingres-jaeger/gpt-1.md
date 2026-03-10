Да, **трейсы из ingress-nginx в Jaeger отправить можно**, а вот **переход из графика метрик ingress-nginx к точному trace “из коробки” — нет**. Причина в том, что для такого перехода Grafana использует **exemplars**, а Prometheus хранит их только если они приходят от scrape-target’а; в ingress-nginx официально документированы OTLP-tracing и Prometheus-метрики, но не документирована выдача trace ID в exemplars для его метрик. ([kubernetes.github.io][1])

Рабочая картина для вашего стека такая:

1. **ingress-nginx 1.9.2 → Jaeger 1.53**: включаете OpenTelemetry в ingress-nginx и отправляете OTLP в Jaeger. ingress-nginx поддерживает `enable-opentelemetry`, `otlp-collector-host`, `otlp-collector-port`, `otel-service-name`, а Jaeger умеет принимать OTLP на `4317` gRPC и `4318` HTTP. ([kubernetes.github.io][1])

2. **Prometheus 2.55 → Grafana 11.5**: для клика из метрики в trace нужны exemplars. Prometheus должен быть запущен с `--enable-feature=exemplar-storage`, а в Grafana у Prometheus datasource нужно настроить exemplar link на Jaeger datasource по полю вроде `traceID`/`trace_id`. ([prometheus.io][2])

3. **Ограничение**: даже если Prometheus и Grafana готовы к exemplars, сами метрики ingress-nginx должны содержать exemplar с trace ID. По официальной документации ingress-nginx это не следует; поэтому точный drill-down “из latency/error графика ingress-nginx в соответствующий trace” я бы считал **недоступным штатно**. Это вывод по совокупности официальных документов: tracing и metrics есть отдельно, а механика exemplar для ingress-nginx не описана. ([kubernetes.github.io][1])

### Что настроить для ingress-nginx → Jaeger

Пример ConfigMap для ingress-nginx:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ingress-nginx-controller
  namespace: ingress-nginx
data:
  enable-opentelemetry: "true"
  opentelemetry-trust-incoming-span: "true"
  opentelemetry-operation-name: "HTTP $request_method $service_name $uri"
  otlp-collector-host: "jaeger-collector.observability.svc"
  otlp-collector-port: "4317"
  otel-service-name: "ingress-nginx"
```

Это соответствует официальным ключам ingress-nginx для OTel. `opentelemetry-trust-incoming-span` полезен, если хотите продолжать входящий trace context, а не всегда начинать новый trace на ingress. ([kubernetes.github.io][1])

Если у вас Jaeger all-in-one / collector, проверьте, что OTLP-приёмник включён и доступен на `4317`/`4318`. В Jaeger v1 OTLP поддерживается нативно. ([Jaeger][3])

### Что настроить в Grafana

1. Добавьте **Jaeger datasource**.
2. В **Prometheus datasource** добавьте exemplar link:

   * Internal link: `On`
   * Data source: ваш Jaeger datasource
   * Label name: `traceID` или `trace_id` — зависит от того, как exemplar приходит в метрике. Grafana это поддерживает штатно. ([Grafana Labs][4])

Пример provisioning для Prometheus datasource:

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    uid: prom
    type: prometheus
    access: proxy
    url: http://prometheus.monitoring.svc:9090
    jsonData:
      prometheusType: Prometheus
      exemplarTraceIdDestinations:
        - datasourceUid: jaeger
          name: traceID
```

Такой формат provisioning прямо описан в документации Grafana. ([Grafana Labs][5])

### Где именно затык

Затык не в Jaeger, не в Grafana и не в Prometheus.
Затык в источнике метрик: **ingress-nginx экспортирует метрики, а tracing настраивается отдельно, но связка метрика→trace через exemplar для этих метрик официально не показана**. Grafana умеет открыть Jaeger trace из exemplar, но exemplar должен уже быть в метрике. ([Grafana Labs][4])

### Что реально можно сделать

**Вариант A — лучший технически:**
оставить ingress-nginx → Jaeger для трейсов, но для перехода из метрик в trace использовать **не метрики ingress-nginx**, а метрики приложения/прокси, которые умеют exemplars. Тогда на графике будет точка exemplar, и Grafana откроет нужный trace в Jaeger. Это штатный путь, под который Grafana/Prometheus и сделаны. ([prometheus.io][2])

**Вариант B — компромисс:**
в Grafana на панели ingress-nginx добавить **data link** не на конкретный trace ID, а на **поиск в Jaeger** по:

* service=`ingress-nginx`
* operation=`HTTP ...`
* временному диапазону панели
* тегам/атрибутам вроде `http.method`, `http.route`, `host`, `service`

Это даст переход “к набору вероятных трейсов”, но не к одному точному trace. Это уже practical workaround, а не exemplar drill-down. Возможность искать trace в Jaeger datasource у Grafana есть. ([Grafana Labs][4])

### Итог

Для вашего набора версий:

* **Отправка трейсов из ingress-nginx в Jaeger — да, поддерживается.** ([kubernetes.github.io][1])
* **Переход из графика метрик ingress-nginx в точный trace — только если в этих метриках есть exemplars с trace ID.**
* **У ingress-nginx штатной связки его Prometheus-метрик с exemplars для trace ID я по официальной документации не нашёл**, поэтому “клик по метрике ingress-nginx → exact trace” лучше считать **неподдерживаемым из коробки**. ([kubernetes.github.io][1])
* **Реалистичный путь**: либо использовать другой источник метрик с exemplars, либо делать ссылку из панели на Jaeger search по label/time range вместо exact trace. ([Grafana Labs][4])

Могу сразу дать готовые `values.yaml` для ingress-nginx, Jaeger и provisioning Grafana под ваш Kubernetes 1.24.

[1]: https://kubernetes.github.io/ingress-nginx/user-guide/third-party-addons/opentelemetry/ "OpenTelemetry - Ingress-Nginx Controller"
[2]: https://prometheus.io/docs/prometheus/latest/feature_flags/ "Feature flags | Prometheus"
[3]: https://www.jaegertracing.io/docs/1.76/apis/?utm_source=chatgpt.com "APIs"
[4]: https://grafana.com/docs/grafana/latest/datasources/jaeger/ "Jaeger data source | Grafana documentation
"
[5]: https://grafana.com/docs/grafana/latest/datasources/prometheus/configure/ "Configure the Prometheus data source | Grafana documentation
"

