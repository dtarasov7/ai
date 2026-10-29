#!/usr/bin/env bash
# Цель: проверить наблюдаемый ответ клиента и обращения на стороне backend.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-23

# Проверяем метку владельца: совпадение имени namespace само по себе не даёт права использовать или
# удалять его.
OWNER=$(kubectl get namespace "$NS" -o jsonpath='{.metadata.labels.pmi-istio-owner}')

# При несовпадении владельца останавливаемся; чужой namespace не изменяем и не удаляем.
if [ "$OWNER" != "$NS" ]; then
  echo "ОШИБКА: namespace не принадлежит этому испытанию."
  exit 1
fi

# Запускаем измерения внутри клиента mesh, не на рабочей машине.
kubectl -n "$NS" exec -i allowed -c app -- python - <<'PYTHON'
# Используем стандартную библиотеку Python 3.8; клиент сам запросы не повторяет.
import json
import socket
import time
import urllib.error
import urllib.request
import uuid

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
base = "http://demo.pmi-istio-23.svc.cluster.local:8080"

def request(path, headers=None, method="GET", timeout=10):
    query = urllib.request.Request(base + path, headers=headers or {}, method=method)
    started = time.monotonic()
    try:
        response = opener.open(query, timeout=timeout)
    except urllib.error.HTTPError as error:
        # 4xx/5xx — ответ HTTP, его нужно сохранить, а не принять за сбой скрипта.
        response = error
    with response:
        body = response.read().decode()
        elapsed = time.monotonic() - started
        print(method, path, response.code, round(elapsed, 3), body, flush=True)
        return response.code, body, elapsed, response.headers

# Ждём маркер именно нашего VirtualService: Ready Pod не означает доставку xDS.
for attempt in range(30):
    status, body, elapsed, headers = request("/")
    if status == 200 and headers.get("x-pmi-rule") == "23":
        break
    time.sleep(1)
else:
    raise SystemExit("Маршрут Istio не применился за 30 попыток")

def stats(request_id):
    status, body, _, _ = request("/stats?id=" + request_id)
    assert status == 200, body
    return json.loads(body)

def case(path, expected_status, expected_count, headers=None, method="GET"):
    # Новый id отделяет каждое измерение от предыдущего прогона и readiness probes.
    request_id = uuid.uuid4().hex
    result = request(path + "?id=" + request_id, headers, method)
    assert result[0] == expected_status, result
    observed = stats(request_id)
    assert observed["count"] == expected_count, observed
    return result, request_id
case("/ok", 200, 1)
# Backend ждёт 3 с до заголовков; proxy прекращает ожидание через 1 с.
result, request_id = case("/slow", 504, 1)
assert 0.7 <= result[2] < 2.8, result
# Проверяем, что работа backend всё-таки завершилась после ответа 504 клиенту.
for attempt in range(30):
    observed = stats(request_id)
    if observed["completed"] == 1:
        break
    time.sleep(0.2)
else:
    raise SystemExit("Backend не завершил работу после timeout")
# Тот же endpoint при достаточном бюджете возвращает нормальный 200.
result, _ = case("/slow", 200, 1, {"x-pmi-case": "long"})
assert result[2] >= 2.8, result
# Если первым истёк timeout библиотеки, HTTP-кода может вообще не быть.
try:
    request("/slow?id=" + uuid.uuid4().hex, {"x-pmi-case": "long"}, timeout=0.2)
except (socket.timeout, urllib.error.URLError) as error:
    # URLError принимаем только с причиной timeout, а не с DNS/connect failure.
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    assert isinstance(reason, socket.timeout), repr(error)
    print("Ожидаемый timeout клиентской библиотеки:", repr(error))
else:
    raise SystemExit("Ожидался timeout клиента, а не HTTP-ответ")
PYTHON
echo "PASS: заявленные HTTP-сценарии пройдены."
