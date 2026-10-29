#!/usr/bin/env bash
# Цель: проверить mTLS к настоящему сервису на отдельной ВМ.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-20
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

# VM_IP — реальный адрес отдельной ВМ, доступный напрямую из Pod сети.
# Агент ВМ уже должен быть подключён к этому mesh; README описывает подготовку.
: "${VM_IP:?Укажите IPv4 отдельной ВМ с настроенным Istio-agent}"
: "${VM_IDENTITY:?Укажите spiffe://trust-domain/ns/namespace/sa/service-account ВМ}"
# Проверяем параметры до первой записи в Kubernetes. Не допускаем внедрения YAML.
python - "$VM_IP" "$VM_IDENTITY" <<'PYTHON'
import ipaddress
import re
import sys
address = ipaddress.IPv4Address(sys.argv[1])
assert not address.is_loopback and not address.is_unspecified, address
assert re.fullmatch(r"spiffe://[a-zA-Z0-9.-]+/ns/[a-z0-9-]+/sa/[a-z0-9-]+", sys.argv[2]), sys.argv[2]
PYTHON
kubectl wait --for=condition=Established crd/serviceentries.networking.istio.io --timeout=60s
kubectl explain serviceentry.spec --api-version=networking.istio.io/v1beta1 >/dev/null

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
# Внешняя ВМ регистрируется как mesh-сервис. IP не принадлежит Kubernetes Pod.
# TLS обязателен: plaintext HTTP-сервер без агента не сможет пройти этот опыт.
kubectl -n "$NS" create -f - <<YAML
apiVersion: networking.istio.io/v1beta1
kind: ServiceEntry
metadata:
  name: vm
spec:
  hosts: [vm.pmi.invalid]
  addresses: [198.18.0.20]
  exportTo: ["."]
  location: MESH_INTERNAL
  resolution: STATIC
  ports:
  - number: 8080
    name: http
    protocol: HTTP
  endpoints:
  - address: "$VM_IP"
    ports:
      http: 8080
---
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: vm
spec:
  host: vm.pmi.invalid
  exportTo: ["."]
  trafficPolicy:
    tls:
      mode: ISTIO_MUTUAL
      # Проверяем не только доверенную CA, но и конкретную identity ВМ.
      subjectAltNames: ["$VM_IDENTITY"]
---
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: vm
spec:
  hosts: [vm.pmi.invalid]
  exportTo: ["."]
  http:
  - retries:
      attempts: 0
    timeout: 5s
    route:
    - destination:
        host: vm.pmi.invalid
        port:
          number: 8080
YAML
echo "Подготовка завершена; выполните 02-check.sh."
