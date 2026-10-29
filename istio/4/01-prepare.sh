#!/usr/bin/env bash
# Цель пункта: Проверяем подпись и claims JWT: валидный токен разрешён, неверная роль и недействительные
# токены запрещены.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-4
echo "Проверяем модуль Istio и API; глобальную конфигурацию не меняем."

# На Deckhouse нужны не только установленные CRD, но и модуль istio в состоянии Ready.
PHASE=$(kubectl get module istio -o jsonpath='{.status.phase}')
echo "istio: $PHASE"
if [ "$PHASE" != Ready ]; then
  echo "ОШИБКА: модуль istio должен быть Ready."
  exit 1
fi

# Проверяем, что API сервера предоставляет нужную версию и поле spec; наличие CRD без served-версии
# недостаточно.
kubectl explain virtualservice.spec --api-version=networking.istio.io/v1beta1 >/dev/null
kubectl explain destinationrule.spec --api-version=networking.istio.io/v1beta1 >/dev/null
kubectl explain requestauthentication.spec --api-version=security.istio.io/v1beta1 >/dev/null
kubectl explain authorizationpolicy.spec --api-version=security.istio.io/v1beta1 >/dev/null

# Передаём манифесты в Kubernetes через stdin. create требует свободных имён; apply обновляет правила
# текущего опыта.
kubectl create -f - <<YAML
apiVersion: v1
# Собственный namespace отделяет опыт от системных ресурсов; очистка удалит только этот namespace.
kind: Namespace
metadata:
  name: "$NS"
  labels:
    pmi-istio-owner: "$NS"
YAML

# При заданной ревизии выбираем соответствующий control plane или injection label; без неё используем
# стандартную установку.
if [ -n "${ISTIO_REV:-}" ]; then

  # Метка namespace включает автоматическое добавление sidecar при создании Pod. Уже запущенные Pod она
  # не изменяет.
  kubectl label namespace "$NS" istio.io/rev="$ISTIO_REV"
else

  # Метка namespace включает автоматическое добавление sidecar при создании Pod. Уже запущенные Pod она
  # не изменяет.
  kubectl label namespace "$NS" istio-injection=enabled
fi

# Можно подставить образ вашего registry через export TEST_IMAGE=...; внутри него требуется python 3.8 и
# доступная стандартная библиотека.
TEST_IMAGE=${TEST_IMAGE:-python:3.12-alpine}

# Передаём манифесты в Kubernetes через stdin. create требует свободных имён; apply обновляет правила
# текущего опыта.
kubectl -n "$NS" create -f - <<YAML
apiVersion: v1
# В ConfigMap хранится исходный код учебного HTTP-сервера; контейнер читает его как файл
# /config/server.py.
kind: ConfigMap
metadata:
  name: server
data:
  server.py: |
    # Стандартные библиотеки Python 3.8: файл-маркер, имя Pod, задержка и простой многопоточный
    # HTTP-сервер.
    import os
    import socket
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    # Обработчик одного HTTP-запроса. Это учебный backend, а не код вашего рабочего сервиса.
    class Handler(BaseHTTPRequestHandler):
        # Метод вызывается сервером для GET; ниже тот же обработчик назначен и для POST.
        def do_GET(self):
            # Искусственно замедляем ответ для опыта с circuit breaker: очередь заполнится только при
            # одновременных запросах.
            if self.path == "/slow":
                time.sleep(0.5)
            # Только /ready учитывает /tmp/unready: тест может снять готовность Pod, не останавливая
            # процесс сервера.
            unready = self.path == "/ready" and os.path.exists("/tmp/unready")
            # При неготовности или обращении к /fail возвращаем 503; все остальные пути обслуживаются с
            # 200.
            status = 503 if unready or self.path == "/fail" else 200
            # В ответе версия:имя-Pod. Так проверяющие определяют и версию приложения, и конкретную
            # реплику.
            body = f"{os.environ['VERSION']}:{socket.gethostname()}".encode()
            # Сначала отправляем HTTP-код и длину тела в байтах, затем завершаем заголовки.
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            # Отправляем тело ответа клиенту. На Python 3.8 поток ожидает bytes, поэтому выше
            # используется encode.
            self.wfile.write(body)

        # POST отвечает так же, как GET: если POST запрещён, это действие AuthorizationPolicy, а не
        # ограничение учебного сервера.
        do_POST = do_GET

    # Слушаем порт 8080 на всех интерфейсах Pod; отдельные потоки позволяют одновременно обрабатывать
    # нагрузку.
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
---
apiVersion: apps/v1
# Deployment поддерживает нужное число реплик одной версии backend. Образы и настройки приложения в
# версиях одинаковы, меняется VERSION.
kind: Deployment
metadata:
  name: demo-v1
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo
      version: v1
  template:
    metadata:
      labels:
        app: demo
        version: v1
      annotations:
        sidecar.istio.io/inject: 'true'
        sidecar.istio.io/rewriteAppHTTPProbers: 'true'
    spec:
      securityContext:
        runAsUser: 1000
        runAsGroup: 1000
        runAsNonRoot: true
      containers:
      - name: app
        # TEST_IMAGE задаётся перед prepare; образ должен быть доступен узлам и содержать python 3.8 со
        # стандартной библиотекой.
        image: "${TEST_IMAGE}"
        # В контейнере нужен бинарник python версии 3.8; этот интерпретатор должен быть доступен в PATH.
        command:
        - python
        - /config/server.py
        env:
        - name: VERSION
          value: v1
        ports:
        - containerPort: 8080
        # Kubelet обращается к /ready и исключает неготовый Pod из endpoints; бизнес-смысл готовности
        # задаёт приложение.
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          periodSeconds: 2
          failureThreshold: 1
        resources:
          requests:
            cpu: 20m
            memory: 32Mi
          limits:
            memory: 128Mi
        volumeMounts:
        - name: config
          mountPath: /config
        - name: tmp
          mountPath: /tmp
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop:
            - ALL
          readOnlyRootFilesystem: true
      volumes:
      - name: config
        configMap:
          name: server
      - name: tmp
        emptyDir: {}
---
apiVersion: apps/v1
# Deployment поддерживает нужное число реплик одной версии backend. Образы и настройки приложения в
# версиях одинаковы, меняется VERSION.
kind: Deployment
metadata:
  name: demo-v2
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo
      version: v2
  template:
    metadata:
      labels:
        app: demo
        version: v2
      annotations:
        sidecar.istio.io/inject: 'true'
        sidecar.istio.io/rewriteAppHTTPProbers: 'true'
    spec:
      securityContext:
        runAsUser: 1000
        runAsGroup: 1000
        runAsNonRoot: true
      containers:
      - name: app
        # TEST_IMAGE задаётся перед prepare; образ должен быть доступен узлам и содержать python 3.8 со
        # стандартной библиотекой.
        image: "${TEST_IMAGE}"
        # В контейнере нужен бинарник python версии 3.8; этот интерпретатор должен быть доступен в PATH.
        command:
        - python
        - /config/server.py
        env:
        - name: VERSION
          value: v2
        ports:
        - containerPort: 8080
        # Kubelet обращается к /ready и исключает неготовый Pod из endpoints; бизнес-смысл готовности
        # задаёт приложение.
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          periodSeconds: 2
          failureThreshold: 1
        resources:
          requests:
            cpu: 20m
            memory: 32Mi
          limits:
            memory: 128Mi
        volumeMounts:
        - name: config
          mountPath: /config
        - name: tmp
          mountPath: /tmp
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop:
            - ALL
          readOnlyRootFilesystem: true
      volumes:
      - name: config
        configMap:
          name: server
      - name: tmp
        emptyDir: {}
---
apiVersion: v1
# Стабильный Service выбирает Pod по labels; через него Istio направляет обращения к реальным endpoints.
kind: Service
metadata:
  name: demo
spec:
  selector:
    app: demo
  ports:
  - name: http
    port: 8080
    targetPort: 8080
---
apiVersion: v1
# Отдельная сервисная учётная запись позволяет различать клиентов по mTLS identity.
kind: ServiceAccount
metadata:
  name: allowed
---
apiVersion: v1
# Тестовый клиент или внешний относительно mesh сервер. Назначение определяется metadata.name и командой
# контейнера.
kind: Pod
metadata:
  name: allowed
  labels:
    app: allowed
  annotations:
    sidecar.istio.io/inject: 'true'
spec:
  serviceAccountName: allowed
  securityContext:
    runAsUser: 1000
    runAsNonRoot: true
  containers:
  - name: app
    # TEST_IMAGE задаётся перед prepare; образ должен быть доступен узлам и содержать python 3.8 со
    # стандартной библиотекой.
    image: "${TEST_IMAGE}"
    # В контейнере нужен бинарник python версии 3.8; этот интерпретатор должен быть доступен в PATH.
    command:
    - python
    - -c
    # Клиент остаётся запущенным сутки без нагрузки; запросы отдельно выполняются через kubectl exec.
    - import time; time.sleep(86400)
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop:
        - ALL
YAML

# Ждём завершения развёртывания с ограничением времени: запросы к ещё неготовым Pod не являются
# испытанием Istio.
kubectl -n "$NS" rollout status deployment/demo-v1 --timeout=180s
kubectl -n "$NS" rollout status deployment/demo-v2 --timeout=180s

# Ждём фактической готовности Pod; для Ready=false, наоборот, ждём снятия готовности после изменения
# /ready.
kubectl -n "$NS" wait --for=condition=Ready pod --all --timeout=180s
# Проверяем реальную injection: одной метки namespace недостаточно для доказательства наличия sidecar.

# Проверяем proxy у реально созданных Pod, а не делаем вывод только по наличию injection label.
PODS=$(kubectl -n "$NS" get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')

# Обходим Pod опыта; намеренно внешний plain пропускаем, у остальных должен отвечать контейнер
# istio-proxy.
for POD in $PODS; do
  if [ "$POD" = plain ]; then continue; fi

  # Обращаемся к административному интерфейсу Envoy через pilot-agent; отсутствие или неготовность
  # sidecar завершит проверку ошибкой.
  kubectl -n "$NS" exec "$POD" -c istio-proxy -- pilot-agent request GET server_info >/dev/null
done
# Одноразовый учебный ключ; рабочие токены/ключи IdP не используются.

# Передаём namespace в локальный Python-код подготовки JWT; значения рабочих токенов не используются.
export NS

# Временный закрытый ключ создаём рядом со скриптом и удаляем после подготовки; запуск из другого
# каталога допустим.
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

# Этот Python-блок выполняется локально, где есть kubectl и OpenSSL. Знак минус означает чтение программы
# из stdin.
python - "$SCRIPT_DIR" <<'PYTHON'
# Все модули ниже входят в стандартную библиотеку Python 3.8; дополнительных pip-пакетов не требуется.
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

# JWT использует Base64URL: заменённый алфавит и отсутствие завершающих знаков =. Это кодирование, а не
# шифрование.
def encode(raw):
    # OpenSSL и JSON работают с bytes; после кодирования возвращаем обычную строку для сборки токена.
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

# Читаем namespace, экспортированный Bash; ресурсы JWT создаются только в нём.
namespace = os.environ["NS"]

# Создаём одноразовый каталог рядом со скриптом. При выходе из with ключ удалится даже при ошибке Python.
with tempfile.TemporaryDirectory(prefix=".jwt-", dir=sys.argv[1]) as temporary:
    # Путь к учебному закрытому RSA-ключу. Он нужен только OpenSSL для подписи, в Kubernetes не
    # передаётся.
    key_path = Path(temporary) / "test-key.pem"
    # Генерируем RSA 2048 бит. check=True прерывает подготовку при ошибке OpenSSL, не продолжая с
    # отсутствующим ключом.
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key_path)], check=True)
    # Извлекаем открытый модуль RSA. capture_output сохраняет ответ для разбора, text=True декодирует его
    # в строку.
    modulus_result = subprocess.run(["openssl", "rsa", "-in", str(key_path), "-noout", "-modulus"], check=True, capture_output=True, text=True)
    # OpenSSL возвращает Modulus=<шестнадцатеричное число>; отделяем число от служебного префикса.
    modulus_hex = modulus_result.stdout.strip().split("=", 1)[1]
    # Переводим модуль из шестнадцатеричной записи в байты, чтобы затем закодировать его для JWKS.
    modulus_bytes = bytes.fromhex(modulus_hex)
    # Публичный набор ключей JWKS нужен Envoy для проверки подписи: n — модуль, e=AQAB — показатель
    # 65537. Закрытой части здесь нет.
    jwks = {"keys": [{
        "kty": "RSA",
        "kid": "pmi-test",
        "alg": "RS256",
        "use": "sig",
        "n": encode(modulus_bytes),
        "e": "AQAB",
    }]}
    # Словарь будущих учебных токенов по названиям случаев. Значения токенов в stdout не печатаем.
    tokens = {}
    # Текущее Unix-время в секундах. Часы рабочей машины и узлов должны быть синхронизированы.
    now = int(time.time())
    # Заголовок JWT объявляет RS256 и идентификатор ключа kid=pmi-test, совпадающий с открытым ключом
    # JWKS.
    header = encode(json.dumps({"alg": "RS256", "kid": "pmi-test", "typ": "JWT"}).encode())
    # Создаём случаи: правильные claims, чужая роль, чужая audience и истёкший срок. Подписи у всех этих
    # токенов настоящие.
    for name, role, audience, expiry in [
        ("valid", "reader", "pmi", now + 3600),
        ("wrong-role", "guest", "pmi", now + 3600),
        ("wrong-audience", "reader", "other", now + 3600),
        ("expired", "reader", "pmi", now - 3600),
    ]:
        # Claims: iss — издатель, sub — пользователь, aud — получатель, role — роль, iat/exp — времена
        # выпуска и окончания действия.
        claims = {
            "iss": "https://pmi.invalid",
            "sub": "test-user",
            "aud": audience,
            "role": role,
            "iat": now - 7200,
            "exp": expiry,
        }
        # Сериализуем claims как JSON и кодируем Base64URL — это средняя часть JWT, доступная для чтения
        # без закрытого ключа.
        payload = encode(json.dumps(claims).encode())
        # Подписываются первые две части JWT через точку: header.payload. Для OpenSSL передаём байты.
        signing_input = f"{header}.{payload}".encode()
        # Подписываем через OpenSSL: SHA-256 + RSA. check=True не даст создать ресурс с ошибочно пустой
        # подписью.
        signature_result = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key_path)], input=signing_input, capture_output=True, check=True)
        # Собираем три части токена: header.payload.signature. Подпись тоже кодируется Base64URL.
        tokens[name] = signing_input.decode() + "." + encode(signature_result.stdout)
    # Для отрицательного случая берём правильный JWT и отделяем подпись от первых двух частей.
    unsigned, signature = tokens["valid"].rsplit(".", 1)
    # Выбираем другой первый символ подписи: он гарантированно отличается от исходного.
    replacement = "A" if signature[0] != "A" else "B"
    # Меняем подпись при неизменных claims. Envoy должен вернуть 401 именно из-за недействительной
    # подписи.
    tokens["bad-signature"] = unsigned + "." + replacement + signature[1:]
    # Один пакет создаёт Secret с учебными токенами, проверку JWT и требование роли reader. Рабочий IdP
    # не используется.
    resources = [
        # stringData принимает исходные строки. Kubernetes сам сформирует Base64 в data.
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "test-tokens"},
            "stringData": tokens,
        },
        # Проверяем подпись, издателя и audience; один этот ресурс ещё разрешал бы запрос без JWT.
        {
            "apiVersion": "security.istio.io/v1beta1",
            "kind": "RequestAuthentication",
            "metadata": {"name": "jwt"},
            "spec": {
                "selector": {"matchLabels": {"app": "demo"}},
                "jwtRules": [{
                    "issuer": "https://pmi.invalid",
                    "audiences": ["pmi"],
                    "jwks": json.dumps(jwks),
                }],
            },
        },
        # ALLOW требует и проверенного пользователя, и role=reader; остальные обращения запрещены.
        {
            "apiVersion": "security.istio.io/v1beta1",
            "kind": "AuthorizationPolicy",
            "metadata": {"name": "reader"},
            "spec": {
                "selector": {"matchLabels": {"app": "demo"}},
                "action": "ALLOW",
                "rules": [{
                    "from": [{"source": {
                        "requestPrincipals": ["https://pmi.invalid/*"],
                    }}],
                    "when": [{
                        "key": "request.auth.claims[role]",
                        "values": ["reader"],
                    }],
                }],
            },
        },
    ]
    # Kubernetes List объединяет три независимых ресурса; все будут созданы в переданном namespace.
    document = {"apiVersion": "v1", "kind": "List", "items": resources}
    # Передаём JSON в kubectl через stdin. Ошибка API прервёт подготовку; готовность реальных правил
    # затем проверит check.
    subprocess.run(["kubectl", "-n", namespace, "create", "-f", "-"], input=json.dumps(document), text=True, check=True)
print("Тестовые JWT созданы на один час; закрытый ключ удалён.")
PYTHON

echo "Подготовка завершена; выполните 02-check.sh."
