#!/usr/bin/env bash
# Цель: проверить наблюдаемый ответ клиента и обращения на стороне backend.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-20

# Проверяем метку владельца: совпадение имени namespace само по себе не даёт права использовать или
# удалять его.
OWNER=$(kubectl get namespace "$NS" -o jsonpath='{.metadata.labels.pmi-istio-owner}')

# При несовпадении владельца останавливаемся; чужой namespace не изменяем и не удаляем.
if [ "$OWNER" != "$NS" ]; then
  echo "ОШИБКА: namespace не принадлежит этому испытанию."
  exit 1
fi

# Сначала положительный контроль. Затем намеренно неверная identity и восстановление.
# Trap возвращает исходную policy даже при неудаче отрицательного контроля.
ORIGINAL=$(kubectl -n "$NS" get destinationrule vm -o jsonpath='{.spec.trafficPolicy.tls.subjectAltNames[0]}')
restore_policy() {
  kubectl -n "$NS" patch destinationrule vm --type=merge \
    -p "{\"spec\":{\"trafficPolicy\":{\"tls\":{\"subjectAltNames\":[\"$ORIGINAL\"]}}}}" >/dev/null
}
trap restore_policy EXIT

# Python получает ожидаемый исход аргументом; внутри выполняется настоящий HTTP к ВМ.
probe() {
  kubectl -n "$NS" exec -i allowed -c app -- python - "$1" <<'PYTHON'
import sys
import time
import urllib.error
import urllib.request

expected = int(sys.argv[1])
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
# Зарезервированный тестовый VIP перехватывает sidecar. В DNS его создавать не нужно.
for attempt in range(30):
    query = urllib.request.Request("http://198.18.0.20:8080/", headers={"Host": "vm.pmi.invalid"})
    try:
        response = opener.open(query, timeout=8)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status = response.code
        body = response.read().decode()
    print(status, body, flush=True)
    if status == expected and (expected != 200 or body.strip() == "pmi-istio-20-real-vm"):
        break
    time.sleep(1)
else:
    raise SystemExit("Не получен ожидаемый ответ от ВМ: " + str(expected))
PYTHON
}
probe 200
# TLS с чужим SAN должен завершиться 503, хотя IP и работающий сервер прежние.
kubectl -n "$NS" patch destinationrule vm --type=merge -p   '{"spec":{"trafficPolicy":{"tls":{"subjectAltNames":["spiffe://invalid.example/ns/absent/sa/absent"]}}}}'
probe 503
restore_policy
probe 200
trap - EXIT
echo "PASS: реальная ВМ доступна через mTLS; проверка identity действует."
