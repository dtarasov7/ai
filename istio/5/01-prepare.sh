#!/usr/bin/env bash
# Цель пункта: Создаём трафик, ищем метрики и access log; полный результат требует отдельно проверить
# хранилища и трассировку.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-5
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
kubectl explain telemetry.spec --api-version=telemetry.istio.io/v1alpha1 >/dev/null

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

# Передаём манифесты в Kubernetes через stdin. create требует свободных имён; apply обновляет правила
# текущего опыта.
kubectl -n "$NS" create -f - <<'YAML'
apiVersion: telemetry.istio.io/v1alpha1
# Включаем сетевой access log только у тестового backend; хранилище логов этот ресурс не создаёт.
kind: Telemetry
metadata:
  name: access-log
spec:
  selector:
    matchLabels:
      app: demo
  accessLogging:
  - providers:
    - name: envoy
YAML

echo "Подготовка завершена; выполните 02-check.sh."
