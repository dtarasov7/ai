Для **OSS MinIO** рабочая схема такая:

* **server errors / server logs**: MinIO умеет писать их в **console** и дополнительно отправлять в **HTTP target** (`logger_webhook`). Консольный target всегда включён и не отключается. Отдельного **Kafka target для server logs** в OSS нет. ([GitHub][1])
* **audit logs**: в OSS есть отдельные targets для **HTTP** и **Kafka** (`audit_webhook`, `audit_kafka`). ([GitHub][1])
* Отдельного постоянного канала **“API logs”** в OSS нет как самостоятельного типа. Для production обычно используют **audit logs**, потому что их JSON уже содержит блок `api` с `name`, `bucket`, `object`, `status`, `statusCode`, `rx`, `tx`, `timeToResponse` и т. п. ([GitHub][1])
* `mc admin trace --errors` и прочие фильтры (`--status-code`, `--call`, `--path`) подходят для диагностики в реальном времени, но это не постоянный pipeline логов. ([MinIO AIStor Documentation][2])

Из этого следует важный вывод:
для **OSS MinIO** ваша задача “ошибки сервера + api + аудит → Kafka → Vector/OpenSearch” делается так:

## Вариант, который я бы рекомендовал

**1. Server logs**
MinIO → `logger_webhook` → локальный Vector (`http_server`) → Kafka topic `minio-server`

**2. API/audit logs**
MinIO → `audit_webhook` → локальный Vector (`http_server`) →

* Kafka topic `minio-audit` — весь audit stream
* Kafka topic `minio-api-errors` — только события, где `api.statusCode >= 400`

Почему именно так:

* всё проходит через **локальный Vector**, у вас единая точка маршрутизации, буферизации и нормализации;
* можно легко развести один и тот же audit stream на несколько Kafka topics;
* не нужно смешивать direct-to-Kafka из MinIO и sidecar/daemon-путь через Vector.

Это лучше, чем делать `audit_kafka` напрямую из MinIO, если вам нужна **гибкая маршрутизация** и разные Kafka topics из одного потока. Возможности Vector по `http_server`, `journald`, `file`, `kafka sink`, acknowledgements и disk buffer документированы отдельно. ([Vector][3])

---

## Что именно возможно в OSS MinIO

### Server logs

В OSS есть **console** и **HTTP target** для server logging. В quickstart MinIO прямо показаны `logger_webhook` и env-переменные `MINIO_LOGGER_WEBHOOK_ENABLE_*`, `MINIO_LOGGER_WEBHOOK_ENDPOINT_*`, плюс batch/queue/retry/http timeout. ([GitHub][1])

### Audit logs

В OSS есть:

* `audit_webhook`
* `audit_kafka`
  Для `audit_kafka` в репозитории MinIO задокументированы `brokers`, `topic`, SASL/TLS, client cert/key, version, queue settings, а в коде видны env-переменные `MINIO_AUDIT_KAFKA_*`. ([GitHub][1])

### “API logs”

В OSS это по сути **audit events с полем `api`**. То есть отдельного канала `api_logs` нет, но нужные API-данные уже есть внутри audit JSON. ([GitHub][1])

---

# Конфигурация MinIO

Ниже схема через **webhook → local Vector**.

## 1) MinIO server logs → local Vector HTTP endpoint

Пример для systemd environment file, например `/etc/default/minio`:

```bash
MINIO_LOGGER_WEBHOOK_ENABLE_local="on"
MINIO_LOGGER_WEBHOOK_ENDPOINT_local="http://127.0.0.1:8686/minio/server"
MINIO_LOGGER_WEBHOOK_BATCH_SIZE_local="1"
MINIO_LOGGER_WEBHOOK_QUEUE_SIZE_local="100000"
MINIO_LOGGER_WEBHOOK_QUEUE_DIR_local="/var/lib/minio/logger-webhook"
MINIO_LOGGER_WEBHOOK_MAX_RETRY_local="0"
MINIO_LOGGER_WEBHOOK_RETRY_INTERVAL_local="1s"
MINIO_LOGGER_WEBHOOK_HTTP_TIMEOUT_local="5s"
```

Эти env-переменные соответствуют тому, что MinIO использует для `logger_webhook`, включая endpoint, batch/queue/retry/timeout. ([GitHub][1])

## 2) MinIO audit logs → local Vector HTTP endpoint

```bash
MINIO_AUDIT_WEBHOOK_ENABLE_local="on"
MINIO_AUDIT_WEBHOOK_ENDPOINT_local="http://127.0.0.1:8686/minio/audit"
MINIO_AUDIT_WEBHOOK_QUEUE_SIZE_local="100000"
MINIO_AUDIT_WEBHOOK_QUEUE_DIR_local="/var/lib/minio/audit-webhook"
MINIO_AUDIT_WEBHOOK_MAX_RETRY_local="0"
MINIO_AUDIT_WEBHOOK_RETRY_INTERVAL_local="1s"
MINIO_AUDIT_WEBHOOK_HTTP_TIMEOUT_local="5s"
```

Эти переменные соответствуют OSS audit webhook target. ([GitHub][1])

После изменения env — перезапуск MinIO. Перезапуск через `mc admin service restart` у MinIO задокументирован. ([MinIO AIStor Documentation][4])

---

# Конфигурация Vector на узле с MinIO

Ниже один файл `vector.yaml`, который:

* принимает **server logs** от `logger_webhook`
* принимает **audit logs** от `audit_webhook`
* нормализует поля
* дублирует audit stream:

  * весь поток в `minio-audit`
  * только API-ошибки в `minio-api-errors`
* отправляет server logs в `minio-server`
* использует **disk buffer** для Kafka sinks

`http_server` в Vector подходит для приёма событий по HTTP, а Kafka sink — для отправки в Kafka; disk buffer и acknowledgements поддерживаются отдельно. ([Vector][5])

```yaml
data_dir: /var/lib/vector

api:
  enabled: true
  address: 127.0.0.1:8687

sources:
  minio_server_http:
    type: http_server
    address: 127.0.0.1:8686
    path: /minio/server
    method: post
    encoding: json

  minio_audit_http:
    type: http_server
    address: 127.0.0.1:8686
    path: /minio/audit
    method: post
    encoding: json

transforms:
  normalize_server:
    type: remap
    inputs: ["minio_server_http"]
    source: |
      .pipeline = "minio"
      .stream = "server"
      .service = "minio"
      .host = get_hostname!()
      .ingest_ts = now()

  normalize_audit:
    type: remap
    inputs: ["minio_audit_http"]
    source: |
      .pipeline = "minio"
      .stream = "audit"
      .service = "minio"
      .host = get_hostname!()
      .ingest_ts = now()

      # Удобные плоские поля для Kafka/OpenSearch
      .api_name = .api.name ?? null
      .bucket = .api.bucket ?? null
      .object = .api.object ?? null
      .api_status = .api.status ?? null
      .status_code = to_int(.api.statusCode) ?? null
      .remote_host = .remotehost ?? null
      .access_key = .accessKey ?? null

  route_audit:
    type: route
    inputs: ["normalize_audit"]
    route:
      all_audit: 'true'
      api_errors: '.status_code != null && .status_code >= 400'

sinks:
  kafka_minio_server:
    type: kafka
    inputs: ["normalize_server"]
    bootstrap_servers: "kafka1:9092,kafka2:9092,kafka3:9092"
    topic: "minio-server"
    encoding:
      codec: json
    acknowledgements:
      enabled: true
    buffer:
      type: disk
      max_size: 10737418240

  kafka_minio_audit:
    type: kafka
    inputs: ["route_audit.all_audit"]
    bootstrap_servers: "kafka1:9092,kafka2:9092,kafka3:9092"
    topic: "minio-audit"
    encoding:
      codec: json
    acknowledgements:
      enabled: true
    buffer:
      type: disk
      max_size: 10737418240

  kafka_minio_api_errors:
    type: kafka
    inputs: ["route_audit.api_errors"]
    bootstrap_servers: "kafka1:9092,kafka2:9092,kafka3:9092"
    topic: "minio-api-errors"
    encoding:
      codec: json
    acknowledgements:
      enabled: true
    buffer:
      type: disk
      max_size: 10737418240
```

Поддержка `bootstrap_servers` у Kafka sink, disk buffering и acknowledgements у Vector документированы в официальных docs. ([Vector][6])

---

# Что попадёт в Kafka

## Topic `minio-server`

Сюда пойдут **server logs** MinIO: ошибки сервера, внутренние сообщения, диагностические события. Это не audit trail. HTTP logger target для server logs в OSS есть, но он не равен audit logging. ([GitHub][1])

## Topic `minio-audit`

Сюда пойдут **все audit события**, включая S3/API операции. В примере формата audit логов у MinIO есть `api.name`, `bucket`, `object`, `status`, `statusCode`, `remotehost`, `requestID`, `timeToResponse`. ([GitHub][1])

## Topic `minio-api-errors`

Это уже **производный поток** из audit stream: только те события, где `api.statusCode >= 400`.
То есть “api logs” в этой схеме — это не отдельный встроенный target MinIO, а логически выделенная часть audit событий. ([GitHub][1])

---

# Если хотите без webhook для server logs

Можно сделать и так:

* MinIO пишет как обычно в stdout/stderr
* systemd кладёт это в journald
* Vector читает `journald` source и отправляет в Kafka

`journald` source в Vector официально поддерживается и использует `journalctl`. ([Vector][3])

Пример источника Vector:

```yaml
sources:
  minio_journald:
    type: journald
    include_units:
      - minio.service
```

И дальше тот же `remap` + `kafka sink`.

Но для MinIO мне больше нравится **`logger_webhook`**, потому что вы получаете более прямой и управляемый pipeline от самого MinIO, без привязки к формату journald. Поддержка `logger_webhook` в OSS показана в MinIO logging quickstart. ([GitHub][1])

---

# Если audit хотите слать в Kafka напрямую из MinIO

Это тоже допустимо:

```bash
MINIO_AUDIT_KAFKA_ENABLE_local="on"
MINIO_AUDIT_KAFKA_BROKERS_local="kafka1:9092,kafka2:9092,kafka3:9092"
MINIO_AUDIT_KAFKA_TOPIC_local="minio-audit"
MINIO_AUDIT_KAFKA_QUEUE_DIR_local="/var/lib/minio/audit-kafka"
MINIO_AUDIT_KAFKA_QUEUE_SIZE_local="100000"
MINIO_AUDIT_KAFKA_TLS_local="off"
MINIO_AUDIT_KAFKA_SASL_local="off"
```

В OSS MinIO для `audit_kafka` есть `brokers`, `topic`, SASL/TLS, version, queue_dir, queue_size. Это видно и в quickstart, и в коде конфигурации. ([GitHub][1])

Но тогда архитектура получится смешанная:

* server logs → Vector → Kafka
* audit logs → напрямую MinIO → Kafka

Это проще по числу hops, но хуже по единообразию маршрутизации и нормализации.

---

# Итоговая рекомендация

Для **OSS MinIO без Docker** я бы ставил так:

* **server logs**: `MINIO_LOGGER_WEBHOOK_*` → local Vector HTTP source → Kafka `minio-server`
* **audit/API logs**: `MINIO_AUDIT_WEBHOOK_*` → local Vector HTTP source →

  * Kafka `minio-audit`
  * Kafka `minio-api-errors`

Потому что именно эта схема:

* полностью совместима с **OSS** возможностями MinIO; ([GitHub][1])
* не требует Docker;
* позволяет отдельно вести **server**, **audit** и **API errors**;
* хорошо ложится на вашу цепочку **Kafka → Vector → OpenSearch**;
* даёт буферизацию на диске и подтверждения доставки на стороне Vector. ([Vector][6])

Могу следующим сообщением собрать это уже в виде готовых файлов:
`/etc/default/minio`, `minio.service.d/override.conf` и ` /etc/vector/vector.yaml`.

[1]: https://github.com/minio/minio/blob/master/docs/logging/README.md "minio/docs/logging/README.md at master · minio/minio · GitHub"
[2]: https://docs.min.io/enterprise/aistor-object-store/reference/cli/admin/mc-admin-trace/?utm_source=chatgpt.com "mc admin trace"
[3]: https://vector.dev/docs/reference/configuration/sources/journald/?utm_source=chatgpt.com "JournalD | Vector documentation"
[4]: https://docs.min.io/enterprise/aistor-object-store/reference/cli/admin/mc-admin-service/?utm_source=chatgpt.com "mc admin service"
[5]: https://vector.dev/docs/reference/configuration/sinks/http/?utm_source=chatgpt.com "HTTP | Vector documentation"
[6]: https://vector.dev/docs/reference/configuration/sinks/kafka/?utm_source=chatgpt.com "Kafka | Vector documentation"
m01.txtm01.txtlogs.mdlogs.md




Ниже готовый комплект под **OSS MinIO + systemd + локальный Vector + Kafka**.

Что получится:

* **server logs** MinIO → `logger_webhook` → Vector → Kafka topic `minio-server`
* **audit logs** MinIO → `audit_webhook` → Vector → Kafka topic `minio-audit`
* **API errors** как подмножество audit-событий (`statusCode >= 400`) → Kafka topic `minio-api-errors`

В OSS MinIO для server logs есть `console` и `http` target, а для audit logs есть отдельный `audit_webhook`; audit JSON уже содержит блок `api` с `name`, `bucket`, `object`, `statusCode` и другими полями. ([GitHub][1])
В Vector для этого подходят `http_server` source и `kafka` sink с disk buffer. ([vector.dev][2])

---

## 1) `/etc/default/minio`

Подставьте свои значения в `MINIO_VOLUMES`, `MINIO_OPTS`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`.

```bash
MINIO_VOLUMES="/srv/minio/data"
MINIO_OPTS="--address :9000 --console-address :9001"

MINIO_ROOT_USER="minioadmin"
MINIO_ROOT_PASSWORD="CHANGE_ME"

# Server logs -> local Vector
MINIO_LOGGER_WEBHOOK_ENABLE_local="on"
MINIO_LOGGER_WEBHOOK_ENDPOINT_local="http://127.0.0.1:8686/minio/server"
MINIO_LOGGER_WEBHOOK_BATCH_SIZE_local="1"
MINIO_LOGGER_WEBHOOK_QUEUE_SIZE_local="100000"
MINIO_LOGGER_WEBHOOK_QUEUE_DIR_local="/var/lib/minio/logger-webhook"
MINIO_LOGGER_WEBHOOK_MAX_RETRY_local="0"
MINIO_LOGGER_WEBHOOK_RETRY_INTERVAL_local="1s"
MINIO_LOGGER_WEBHOOK_HTTP_TIMEOUT_local="5s"

# Audit logs -> local Vector
MINIO_AUDIT_WEBHOOK_ENABLE_local="on"
MINIO_AUDIT_WEBHOOK_ENDPOINT_local="http://127.0.0.1:8686/minio/audit"
MINIO_AUDIT_WEBHOOK_QUEUE_SIZE_local="100000"
MINIO_AUDIT_WEBHOOK_QUEUE_DIR_local="/var/lib/minio/audit-webhook"
MINIO_AUDIT_WEBHOOK_MAX_RETRY_local="0"
MINIO_AUDIT_WEBHOOK_RETRY_INTERVAL_local="1s"
MINIO_AUDIT_WEBHOOK_HTTP_TIMEOUT_local="5s"
```

MinIO поддерживает эти env-переменные для `logger_webhook` и `audit_webhook`, причём HTTP target отправляет JSON на указанный endpoint. ([GitHub][1])

---

## 2) `/etc/systemd/system/minio.service`

Если у вас unit уже есть, этот шаг можно пропустить и использовать только override ниже. Если нужен полный unit, вот рабочий вариант:

```ini
[Unit]
Description=MinIO
Documentation=https://min.io/docs/
Wants=network-online.target
After=network-online.target
AssertFileIsExecutable=/usr/local/bin/minio

[Service]
WorkingDirectory=/usr/local
User=minio
Group=minio
EnvironmentFile=-/etc/default/minio
ExecStart=/usr/local/bin/minio server $MINIO_OPTS $MINIO_VOLUMES
Restart=always
LimitNOFILE=65536
TasksMax=infinity
TimeoutStopSec=infinity
SendSIGKILL=no

# обычный stdout/stderr оставляем в journald
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

---

## 3) `/etc/systemd/system/minio.service.d/override.conf`

Нужен, если unit уже существует и вы хотите только задать env-файл и политику рестарта.

```ini
[Service]
EnvironmentFile=-/etc/default/minio
Restart=always
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal
```

Если всё же решите читать server logs не через `logger_webhook`, а из journald, Vector умеет читать journald и фильтровать по `include_units`. ([vector.dev][3])

---

## 4) `/etc/vector/vector.yaml`

Это основной pipeline.

```yaml
data_dir: /var/lib/vector

api:
  enabled: true
  address: 127.0.0.1:8687

sources:
  minio_server_http:
    type: http_server
    address: 127.0.0.1:8686
    method: POST
    path: /minio/server
    strict_path: true
    decoding:
      codec: json
    framing:
      method: bytes

  minio_audit_http:
    type: http_server
    address: 127.0.0.1:8686
    method: POST
    path: /minio/audit
    strict_path: true
    decoding:
      codec: json
    framing:
      method: bytes

transforms:
  normalize_minio_server:
    type: remap
    inputs: ["minio_server_http"]
    source: |
      .service = "minio"
      .stream = "server"
      .pipeline = "minio"
      .host = get_hostname!()
      .ingest_timestamp = now()

  normalize_minio_audit:
    type: remap
    inputs: ["minio_audit_http"]
    source: |
      .service = "minio"
      .stream = "audit"
      .pipeline = "minio"
      .host = get_hostname!()
      .ingest_timestamp = now()

      .api_name = .api.name ?? null
      .bucket = .api.bucket ?? null
      .object = .api.object ?? null
      .api_status = .api.status ?? null
      .status_code = to_int(.api.statusCode) ?? null
      .remote_host = .remotehost ?? null
      .request_id = .requestID ?? null
      .request_path = .requestPath ?? null
      .request_host = .requestHost ?? null
      .user_agent = .userAgent ?? null
      .access_key = .accessKey ?? null

  route_minio_audit:
    type: route
    inputs: ["normalize_minio_audit"]
    route:
      all_audit: 'true'
      api_errors: '.status_code != null && .status_code >= 400'

sinks:
  kafka_minio_server:
    type: kafka
    inputs: ["normalize_minio_server"]
    bootstrap_servers: "kafka1:9092,kafka2:9092,kafka3:9092"
    topic: "minio-server"
    encoding:
      codec: json
    acknowledgements:
      enabled: true
    buffer:
      type: disk
      max_size: 10737418240

  kafka_minio_audit:
    type: kafka
    inputs: ["route_minio_audit.all_audit"]
    bootstrap_servers: "kafka1:9092,kafka2:9092,kafka3:9092"
    topic: "minio-audit"
    encoding:
      codec: json
    acknowledgements:
      enabled: true
    buffer:
      type: disk
      max_size: 10737418240

  kafka_minio_api_errors:
    type: kafka
    inputs: ["route_minio_audit.api_errors"]
    bootstrap_servers: "kafka1:9092,kafka2:9092,kafka3:9092"
    topic: "minio-api-errors"
    encoding:
      codec: json
    acknowledgements:
      enabled: true
    buffer:
      type: disk
      max_size: 10737418240
```

У `http_server` в Vector есть `address`, `method`, `path`, `strict_path`, а JSON можно принимать через `decoding.codec = "json"`. У `kafka` sink задаются `bootstrap_servers` и `topic`; disk buffer поддерживается и требует `buffer.type = "disk"` и `buffer.max_size`. ([vector.dev][2])

---

## 5) `/etc/systemd/system/vector.service.d/override.conf`

Чтобы Vector стартовал после сети и автоматически перезапускался:

```ini
[Service]
Restart=always
RestartSec=5
LimitNOFILE=65536
```

---

## 6) Создание каталогов и права

```bash
sudo useradd --system --home /var/lib/minio --shell /sbin/nologin minio || true
sudo useradd --system --home /var/lib/vector --shell /sbin/nologin vector || true

sudo mkdir -p /srv/minio/data
sudo mkdir -p /var/lib/minio/logger-webhook
sudo mkdir -p /var/lib/minio/audit-webhook
sudo mkdir -p /var/lib/vector

sudo chown -R minio:minio /srv/minio /var/lib/minio
sudo chown -R vector:vector /var/lib/vector
```

---

## 7) Перезапуск

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vector
sudo systemctl enable --now minio
sudo systemctl restart vector
sudo systemctl restart minio
```

---

## 8) Проверка

Проверка Vector:

```bash
sudo journalctl -u vector -f
curl -s http://127.0.0.1:8687/health
```

Проверка MinIO:

```bash
sudo journalctl -u minio -f
```

Проверка audit-потока: выполните любой S3-запрос к MinIO, после чего должны пойти события в `minio-audit`. Формат audit JSON у MinIO действительно содержит поля `api.name`, `api.bucket`, `api.object`, `api.statusCode`, `requestID`, `remotehost`. ([GitHub][1])

---

## 9) Что можно доработать сразу

Если у Kafka есть SASL/TLS, в `vector.yaml` обычно добавляют `librdkafka_options` для security-параметров. Kafka sink Vector это поддерживает. ([vector.dev][4])

Пример:

```yaml
    librdkafka_options:
      security.protocol: "SASL_SSL"
      sasl.mechanisms: "SCRAM-SHA-512"
      sasl.username: "vector"
      sasl.password: "CHANGE_ME"
      ssl.ca.location: "/etc/ssl/certs/ca-bundle.crt"
```

---

## 10) Практическая оговорка

В **OSS MinIO** отдельного постоянного встроенного канала **“API logs”** как самостоятельного target нет; для production-сценария его обычно моделируют как **audit stream** и дальше уже режут по `api.statusCode`, `api.name` и другим полям во внешнем пайплайне. Это следует из MinIO logging quickstart и примера audit JSON. ([GitHub][1])

Если хотите, я следующим сообщением дам ещё и готовый `vector.yaml` с:

* TLS/SASL для Kafka,
* добавлением hostname/IP в события,
* раздельными топиками `minio-put`, `minio-get`, `minio-delete`.

[1]: https://github.com/minio/minio/blob/master/docs/logging/README.md "minio/docs/logging/README.md at master · minio/minio · GitHub"
[2]: https://vector.dev/docs/reference/configuration/sources/http_server/ "HTTP Server | Vector documentation"
[3]: https://vector.dev/docs/reference/configuration/sources/journald/ "JournalD | Vector documentation"
[4]: https://vector.dev/docs/reference/configuration/sinks/kafka/ "Kafka | Vector documentation"
