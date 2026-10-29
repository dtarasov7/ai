#!/usr/bin/env bash
# Цель пункта: Проверяем subsets по labels и выбор версии по заголовку группы.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-8
echo "Проверяем istiod, injection webhook и API Istio."

# В K3s control plane обычно расположен в istio-system; переменная позволяет указать другой namespace.
ISTIO_NAMESPACE=${ISTIO_NAMESPACE:-istio-system}
ISTIOD_DEPLOYMENT=istiod
INJECTOR_CONFIG=istio-sidecar-injector

# При заданной ревизии выбираем соответствующий control plane или injection label; без неё используем
# стандартную установку.
if [ -n "${ISTIO_REV:-}" ]; then
  ISTIOD_DEPLOYMENT="istiod-$ISTIO_REV"
  INJECTOR_CONFIG="istio-sidecar-injector-$ISTIO_REV"
fi

# Ждём завершения развёртывания с ограничением времени: запросы к ещё неготовым Pod не являются
# испытанием Istio.
kubectl -n "$ISTIO_NAMESPACE" rollout status "deployment/$ISTIOD_DEPLOYMENT" --timeout=180s

# Успешный rollout при replicas=0 ещё не означает работающий istiod; проверяем хотя бы одну готовую
# реплику.
READY_REPLICAS=$(kubectl -n "$ISTIO_NAMESPACE" get deployment "$ISTIOD_DEPLOYMENT" -o jsonpath='{.status.readyReplicas}')
echo "Готовые реплики $ISTIOD_DEPLOYMENT: ${READY_REPLICAS:-0}"
if [ "${READY_REPLICAS:-0}" -lt 1 ]; then
  echo "ОШИБКА: нужна хотя бы одна готовая реплика istiod."
  exit 1
fi

# Проверяем наличие готового адреса у Service, обслуживающего injection webhook.

# Ограниченно ждём готового адреса istiod: сведения endpoints могут обновиться немного позже готовности
# Deployment.
for ATTEMPT in {1..30}; do
  READY_ADDRESSES=$(kubectl -n "$ISTIO_NAMESPACE" get endpoints "$ISTIOD_DEPLOYMENT" -o jsonpath='{.subsets[*].addresses[*].ip}')
  if [ -n "$READY_ADDRESSES" ]; then break; fi
  echo "Ожидаем готовый endpoint istiod: $ATTEMPT/30"
  sleep 1
done
if [ -z "$READY_ADDRESSES" ]; then
  echo "ОШИБКА: Service istiod не имеет готовых endpoints."
  exit 1
fi

# Само наличие конфигурации webhook недостаточно: проверяем Service, путь и CA.

# Извлекаем только webhooks выбранного istiod. Проверяем namespace, путь /inject и наличие доверенного
# CA.
WEBHOOK_DETAILS=$(kubectl get mutatingwebhookconfiguration "$INJECTOR_CONFIG" -o "jsonpath={range .webhooks[?(@.clientConfig.service.name=='$ISTIOD_DEPLOYMENT')]}{.clientConfig.service.namespace}{'|'}{.clientConfig.service.path}{'|'}{.clientConfig.caBundle}{'\n'}{end}")
WEBHOOK_READY=false

# Один istiod может иметь несколько injection webhooks. Достаточно корректной записи для его Service; CA
# не выводим в журнал.
while IFS='|' read -r WEBHOOK_NAMESPACE WEBHOOK_PATH WEBHOOK_CA; do
  if [ "$WEBHOOK_NAMESPACE" = "$ISTIO_NAMESPACE" ] && [ "$WEBHOOK_PATH" = /inject ] && [ -n "$WEBHOOK_CA" ]; then
    WEBHOOK_READY=true
  fi
done <<< "$WEBHOOK_DETAILS"

# Без подходящего webhook нельзя надёжно создать Pod с sidecar; остановимся до создания ресурсов опыта.
if [ "$WEBHOOK_READY" != true ]; then
  echo "ОШИБКА: $INJECTOR_CONFIG должен указывать на $ISTIO_NAMESPACE/$ISTIOD_DEPLOYMENT, путь /inject, с непустым caBundle."
  exit 1
fi
echo "Injection webhook $INJECTOR_CONFIG настроен; istiod имеет готовые endpoints."

echo "Проверяем Established у CRD, используемых этим пунктом."

# Ждём регистрации CRD до использования ресурса; отсутствие CRD или таймаут прервёт подготовку.
kubectl wait --for=condition=Established "crd/virtualservices.networking.istio.io" --timeout=60s
kubectl wait --for=condition=Established "crd/destinationrules.networking.istio.io" --timeout=60s

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
apiVersion: networking.istio.io/v1beta1
# Определяем subsets по labels и настройки upstream: балансировку, TLS или ограничения очередей.
kind: DestinationRule
metadata:
  name: demo
spec:
  host: demo.pmi-istio-8.svc.cluster.local
  # Видимость конфигурации: точка означает текущий namespace; namespace gateway добавлен только для
  # ingress.
  exportTo:
  - .
  # Имя subset связывается с labels version у Pod; сами Deployment этим разделом не создаются.
  subsets:
  - name: v1
    labels:
      version: v1
  - name: v2
    labels:
      version: v2
---
apiVersion: networking.istio.io/v1beta1
# Правила выбора маршрута: host/заголовки/путь сопоставляются с версией backend и её весом.
kind: VirtualService
metadata:
  name: demo
spec:
  hosts:
  - demo.pmi-istio-8.svc.cluster.local
  # Видимость конфигурации: точка означает текущий namespace; namespace gateway добавлен только для
  # ingress.
  exportTo:
  - .
  http:
  - match:
    - headers:
        x-cohort:
          exact: B
    route:
    - destination:
        host: demo.pmi-istio-8.svc.cluster.local
        subset: v2
    retries:
      # Отключаем автоматические повторы, чтобы они не скрывали проверяемые отказы и распределение
      # трафика.
      attempts: 0
  - route:
    - destination:
        host: demo.pmi-istio-8.svc.cluster.local
        subset: v1
      # Вес задаёт вероятность выбора версии, а не точное число запросов в маленькой выборке.
      weight: 100
    - destination:
        host: demo.pmi-istio-8.svc.cluster.local
        subset: v2
      # Вес задаёт вероятность выбора версии, а не точное число запросов в маленькой выборке.
      weight: 0
    retries:
      # Отключаем автоматические повторы, чтобы они не скрывали проверяемые отказы и распределение
      # трафика.
      attempts: 0
    timeout: 5s
YAML

echo "Подготовка завершена; выполните 02-check.sh."
