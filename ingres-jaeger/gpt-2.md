Ниже — что именно делают эти ключи **ConfigMap** у **kubernetes/ingress-nginx** (community Ingress NGINX), когда включена интеграция с OpenTelemetry. Они управляют тем, **как ingress-nginx создаёт и отправляет трейсы (spans) через OTLP**. ([kubernetes.github.io][1])

---

## `opentelemetry-operation-name: "HTTP $request_method $service_name $uri"`

**Что делает:** задаёт **кастомное имя server-span’а** (основного спана входящего HTTP-запроса на уровне ingress). По умолчанию имя пустое (то есть используется дефолтное поведение модуля). ([kubernetes.github.io][1])

**Зачем нужно:**

* Имя спана — это то, что вы чаще всего видите в трейсинге как “операцию” (operation/span name).
* Хорошо подобранное имя сильно влияет на удобство агрегации в APM (группировка по эндпойнтам/маршрутам).

**Про шаблон:**

* Можно использовать **переменные NGINX** (например `$request_method`, `$uri` и т.п.).
* В вашем шаблоне имя будет выглядеть примерно так:
  `HTTP GET my-service /api/v1/orders`

**Практические советы:**

* Если у вас много уникальных `$uri` (например, содержит ID: `/users/123`), это может “раздувать” кардинальность имён. Часто лучше использовать нормализованный путь (если он доступен в переменных) или не включать динамические части.

---

## `opentelemetry-trust-incoming-span: "true"`

**Что делает:** включает использование **контекста трассировки из входящего запроса** как **parent** для спана, который создаёт ingress-nginx. ([kubernetes.github.io][1])

Иными словами:

* если клиент/прокси перед ingress прислал заголовки трассировки (например, W3C `traceparent`), ingress **продолжит существующий trace**;
* если заголовков нет — ingress создаст новый trace (станет “корнем”).

**Зачем нужно:**

* Это нужно для “сквозной” трассировки: LB/API-gateway → ingress → сервисы.

**Риски/нюансы:**

* На публичном периметре это буквально “доверие заголовкам клиента”. Злоумышленник может подсовывать trace-id/parent-id и “засорять” трассы. В проде на edge иногда делают так: доверять входящим спанам только если ingress стоит **за доверенным** L7/LB, который сам формирует trace headers.

---

## `otel-sampler: "TraceIdRatioBased"`

**Что делает:** выбирает **самплер** (правило, какие трейсы записывать). Доступные значения: `AlwaysOff`, `AlwaysOn`, `TraceIdRatioBased`, `remote`. Дефолт: `AlwaysOn`. ([kubernetes.github.io][1])

**`TraceIdRatioBased`** — это вероятностная выборка по trace-id:

* условно, “N% трейсов записываем, остальные отбрасываем”;
* важно: решение детерминированно по trace-id → если разные компоненты используют тот же trace-id, они чаще будут принимать одинаковое решение о sampling (это помогает согласованности).

---

## `otel-sampler-ratio: "0.1"`

**Что делает:** задаёт **долю (rate)** для sampling. В документации ingress-nginx указано: “sample rate for any traces created”, дефолт `0.01`. ([kubernetes.github.io][1])

При `0.1` — это **10%** трейсов.

**Важный нюанс про “created”:**

* Этот ratio применяется к трассам, **которые создаёт ingress** (например, когда нет родителя).
* Если у вас включено “доверять входящему спану” и/или используется parent-based поведение (у ingress-nginx есть отдельный ключ `otel-sampler-parent-based`, дефолт `true`), то если **родитель уже “sampled”**, дочерние спаны обычно тоже будут sampled. ([kubernetes.github.io][1])

---

## `opentelemetry-config: "/etc/ingress-controller/telemetry/opentelemetry.toml"`

**Что делает:** указывает путь к **конфигурационному файлу OpenTelemetry** (TOML), который использует ingress-nginx для настройки OTel-пайплайна/экспортёра. Дефолтный путь именно такой. ([kubernetes.github.io][1])

**Зачем нужно:**

* В этом файле обычно задаются детали экспорта (например, куда слать OTLP, параметры TLS, процессоры/батчинг и т.п.) — в зависимости от сборки/модуля.

**Типичная проблема:**

* Если файл указан, но **не существует/не примонтирован**, nginx может ругаться при перезагрузке конфигурации (есть реальные кейсы с ошибкой “no such file or directory”). ([GitHub][2])

---

## `otel-service-name: "nginx-ingress"`

**Что делает:** задаёт `service.name` (имя сервиса) для спанов, которые создаёт ingress-nginx. Дефолт: `"nginx"`. ([kubernetes.github.io][1])

**Зачем нужно:**

* В большинстве APM/трейс-бэкендов именно по `service.name` строятся списки сервисов и зависимости (service map).
* Хорошая практика — задавать понятное имя вроде `nginx-ingress`, `edge-ingress`, `ingress-nginx-controller` и т.д., чтобы оно не смешивалось с “обычным nginx”.

---

## `otel-max-queuesize: "2048"`

**Что делает:** ограничивает размер **очереди (буфера) спанов** перед отправкой — максимальное число спанов, которые могут накапливаться до экспорта. В ingress-nginx дефолт тоже `2048`. ([kubernetes.github.io][1])

**Что происходит при превышении:**

* Когда очередь заполняется, **новые спаны начинают дропаться** (теряются), чтобы не раздувать память и не “класть” воркер. (Это типичное поведение batch-процессоров.) ([open-telemetry.github.io][3])

**Как тюнить:**

* Увеличивать имеет смысл при высоком RPS/латентном экспортёре (чтобы меньше терять данные), но это увеличивает потребление памяти.
* Если видите потери — часто полезнее не только поднимать очередь, но и:

  * уменьшать sampling (например, ratio),
  * ускорять/стабилизировать OTLP endpoint,
  * настраивать batching (у ingress-nginx рядом есть параметры типа `otel-schedule-delay-millis`, `otel-max-export-batch-size`).

---

Если скажете, **какой именно ingress-controller** вы используете (community `ingress-nginx` или F5 NGINX Ingress Controller) и покажете пример вашего `opentelemetry.toml`, я могу разобрать ещё и **что именно настроено в экспорте/процессорах** и как это влияет на задержки/потери спанов.

[1]: https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/configmap/ "ConfigMap - Ingress-Nginx Controller"
[2]: https://github.com/kubernetes/ingress-nginx/issues/12904?utm_source=chatgpt.com "open /etc/ingress-controller/telemetry/opentelemetry.toml: ..."
[3]: https://open-telemetry.github.io/opentelemetry-ruby/opentelemetry-sdk/v1.4.0/OpenTelemetry/SDK/Trace/Export/BatchSpanProcessor.html?utm_source=chatgpt.com "OpenTelemetry::SDK::Trace::Export::BatchSpanProcessor"

