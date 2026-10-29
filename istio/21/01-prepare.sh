#!/usr/bin/env bash
# Цель: проверить поведение HTTP proxy и число реальных обращений к backend.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-21
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
    # Учебный backend считает реальные обращения по уникальному id запроса.
    # Счётчики позволяют отличить повторы Envoy от единственного вызова клиента.
    import json
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs

    counts = {}
    completed = {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # /stats только читает состояние: опрос не меняет результат опыта.
            parsed = urlparse(self.path)
            parameters = parse_qs(parsed.query)
            request_id = parameters.get("id", ["probe"])[0]
            if parsed.path == "/stats":
                with lock:
                    body = {"count": counts.get(request_id, 0),
                            "completed": completed.get(request_id, 0)}
                self.reply(200, body)
                return

            # Readiness и проверка распространения маршрута не попадают в счётчики.
            if parsed.path in ("/ready", "/"):
                self.reply(200, {"ready": True})
                return

            # Блокировка защищает счётчик при одновременной обработке запросов.
            with lock:
                attempt = counts.get(request_id, 0) + 1
                counts[request_id] = attempt

            # /flaky: первые два обращения дают 503, третье и следующие — 200.
            status = 200
            if parsed.path == "/always" or (parsed.path == "/flaky" and attempt <= 2):
                status = 503
            if parsed.path == "/bad":
                status = 400
            if parsed.path == "/slow":
                time.sleep(3)

            # Отмечаем завершение работы ДО отправки ответа. Даже после timeout
            # клиентского proxy прикладной поток может продолжать исполняться.
            with lock:
                completed[request_id] = completed.get(request_id, 0) + 1
            self.reply(status, {"attempt": attempt, "id": request_id})

        def reply(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError) as error:
                # Ожидаемо при timeout: фиксируем закрытие соединения, не скрываем его.
                print("Клиент уже отключился:", error, flush=True)

        # POST без тела нужен для демонстрации: Envoy не гарантирует идемпотентность.
        do_POST = do_GET

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

# Передаём манифесты в Kubernetes через stdin. create требует свободных имён; apply обновляет правила
# текущего опыта.
# Явно задаём retry/timeout; опыт не зависит от политики повторов по умолчанию.
kubectl -n "$NS" create -f - <<'YAML'
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: demo
spec:
  host: demo.pmi-istio-21.svc.cluster.local
  exportTo:
  - .
  subsets:
  - name: v1
    labels:
      version: v1
---
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: demo
spec:
  hosts:
  - demo.pmi-istio-21.svc.cluster.local
  exportTo:
  - .
  http:
  - route:
    - destination:
        host: demo.pmi-istio-21.svc.cluster.local
        subset: v1
    # Маркер ответа позволяет check дождаться доставки правила в Envoy.
    headers:
      response:
        set:
          x-pmi-rule: '21'
    match:
    - headers:
        x-pmi-case:
          exact: abort
    # Авария применяется только к запросам, выбранным match выше.
    fault:
      abort:
        httpStatus: 503
        # 100 процентов исключают случайность при приёмке механизма.
        percentage:
          value: 100
  - route:
    - destination:
        host: demo.pmi-istio-21.svc.cluster.local
        subset: v1
    # Маркер ответа позволяет check дождаться доставки правила в Envoy.
    headers:
      response:
        set:
          x-pmi-rule: '21'
    match:
    - headers:
        x-pmi-case:
          exact: delay
    # Авария применяется только к запросам, выбранным match выше.
    fault:
      delay:
        fixedDelay: 2s
        # 100 процентов исключают случайность при приёмке механизма.
        percentage:
          value: 100
  - route:
    - destination:
        host: demo.pmi-istio-21.svc.cluster.local
        subset: v1
    # Маркер ответа позволяет check дождаться доставки правила в Envoy.
    headers:
      response:
        set:
          x-pmi-rule: '21'
    # attempts — число повторов после исходной попытки; ноль отключает их.
    retries:
      attempts: 0
    # Общий бюджет маршрута, включая повторы; это не timeout клиентской библиотеки.
    timeout: 5s
YAML
echo "Подготовка завершена; выполните 02-check.sh."
