#!/usr/bin/env bash
# Цель пункта: Неготовый backend v2 исключается из трафика и возвращается после восстановления readiness.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-18

# Проверяем метку владельца: совпадение имени namespace само по себе не даёт права использовать или
# удалять его.
OWNER=$(kubectl get namespace "$NS" -o jsonpath='{.metadata.labels.pmi-istio-owner}')

# При несовпадении владельца останавливаемся; чужой namespace не изменяем и не удаляем.
if [ "$OWNER" != "$NS" ]; then
  echo "ОШИБКА: namespace не принадлежит этому испытанию."
  exit 1
fi

# Выполняем короткую программу в контейнере app; код передаём аргументом -c интерпретатора.
kubectl -n "$NS" exec -i allowed -c app -- python -  <<'PYTHON'
# Все модули ниже входят в стандартную библиотеку Python 3.8; дополнительных pip-пакетов не требуется.
import time
import urllib.error
import urllib.request

# Прямой HTTP-клиент: отключаем proxy из переменных окружения, чтобы запрос действительно прошёл через
# проверяемый sidecar.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Единый порядок HTTP-проверки: возвращаем пару (код ответа, текст тела). Сетевые сбои здесь не скрываем.
def request(url, headers=None, method="GET"):
    # Собираем URL, заголовки и HTTP-метод. Отправка произойдёт при opener.open, а не при создании
    # Request.
    query = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        # Ожидаем ответ не более 5 секунд; with закроет соединение после чтения результата.
        with opener.open(query, timeout=5) as response:
            # Код нужен для проверки разрешения/запрета; тело преобразуем из байтов в текст для
            # определения версии backend.
            return response.status, response.read().decode()
    # HTTP 4xx/5xx — полноценный ответ сервера: сохраняем его для сравнения с ожидаемым кодом.
    except urllib.error.HTTPError as error:
        # Возвращаем код и тело отказа; сам по себе отказ не означает ошибку теста, если он ожидается.
        return error.code, error.read().decode()

# Множество хранит только разные версии: повторный ответ от той же версии не увеличивает его размер.
versions = set()

# Повторяем запросы, чтобы подтвердить устойчивое поведение, а не один случайный ответ.
for sample in range(100):
    # Сохраняем HTTP-код и тело раздельно для проверки и показа результата комиссии.
    status, body = request("http://demo.pmi-istio-18.svc.cluster.local:8080/")
    # Контроль работоспособности: перед оценкой маршрута или распределения нужен успешный ответ backend.
    assert status == 200, (status, body)
    # В ответе формат версия:Pod; отделяем имя версии от имени конкретной реплики.
    versions.add(body.split(":")[0])
    # Можно остановить сбор, когда реально получены ответы обеих версий.
    if versions == {"v1", "v2"}:
        break
    # Даём endpoints и маршрутам обновиться между пробами, сохраняя ограниченное число запросов.
    time.sleep(0.2)
print("Доступные версии:", versions)

# Наличие двух Deployment в API не является доказательством: требуются ответы и v1, и v2.
assert versions == {"v1", "v2"}, versions
PYTHON

# Определяем конкретный Pod версии v2; файл готовности меняем только в этой реплике.
POD_V2=$(kubectl -n "$NS" get pod -l app=demo,version=v2 -o jsonpath='{.items[0].metadata.name}')

# Выполняем короткую программу в контейнере app; код передаём аргументом -c интерпретатора.
kubectl -n "$NS" exec "$POD_V2" -c app -- python -c '
# Меняем только тестовый Pod: создаём файл-маркер, из-за которого /ready начнёт возвращать 503.
from pathlib import Path
Path("/tmp/unready").touch()
'

# Ждём фактической готовности Pod; для Ready=false, наоборот, ждём снятия готовности после изменения
# /ready.
kubectl -n "$NS" wait --for=condition=Ready=false pod/"$POD_V2" --timeout=60s
# Дождаться не только Pod Ready=false, но и обновления EndpointSlice.

# Ограниченный цикл ожидания маршрута, журнала или endpoints. Нужный результат дополнительно проверяем
# после цикла.
for ATTEMPT in $(seq 1 30); do
  echo "Попытка $ATTEMPT/30"

  # Проверяем готовность адреса именно Pod v2 в EndpointSlice, а не состояние всех endpoints сразу.
  READY=$(kubectl -n "$NS" get endpointslices -l kubernetes.io/service-name=demo -o "jsonpath={.items[*].endpoints[?(@.targetRef.name=='$POD_V2')].conditions.ready}")
  if [ "$READY" = false ]; then break; fi
  sleep 1
done
echo "Endpoint v2 ready: $READY"

# Требуем явное false у готовности endpoint; пустое значение или таймаут не считаются прохождением.
test "$READY" = false

# Выполняем короткую программу в контейнере app; код передаём аргументом -c интерпретатора.
kubectl -n "$NS" exec -i allowed -c app -- python -  <<'PYTHON'
# Все модули ниже входят в стандартную библиотеку Python 3.8; дополнительных pip-пакетов не требуется.
import time
import urllib.error
import urllib.request

# Прямой HTTP-клиент: отключаем proxy из переменных окружения, чтобы запрос действительно прошёл через
# проверяемый sidecar.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Единый порядок HTTP-проверки: возвращаем пару (код ответа, текст тела). Сетевые сбои здесь не скрываем.
def request(url, headers=None, method="GET"):
    # Собираем URL, заголовки и HTTP-метод. Отправка произойдёт при opener.open, а не при создании
    # Request.
    query = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        # Ожидаем ответ не более 5 секунд; with закроет соединение после чтения результата.
        with opener.open(query, timeout=5) as response:
            # Код нужен для проверки разрешения/запрета; тело преобразуем из байтов в текст для
            # определения версии backend.
            return response.status, response.read().decode()
    # HTTP 4xx/5xx — полноценный ответ сервера: сохраняем его для сравнения с ожидаемым кодом.
    except urllib.error.HTTPError as error:
        # Возвращаем код и тело отказа; сам по себе отказ не означает ошибку теста, если он ожидается.
        return error.code, error.read().decode()

# Адрес назначения для этого этапа. Внутреннее имя Service разрешает DNS Kubernetes.
url = 'http://demo.pmi-istio-18.svc.cluster.local:8080/'

# Дополнительные HTTP-заголовки: например, группа A/B, ключ сессии или Host внешнего сервиса.
headers = {}

# Проверяем префикс v1/v2 в теле ответа; None означает, что на этом этапе важен только HTTP-код.
expected_version = 'v1'

# Istio распространяет настройки асинхронно: разрешаем до 30 попыток, вместо фиксированной длительной
# паузы.
for attempt in range(30):
    # Выполняем запрос отдельно от проверок: код и тело можно просмотреть в отладчике.
    response_status, body = request(url, headers, 'GET')
    # Успех первой попытки требует одновременно ожидаемого HTTP-кода и нужной версии, если она задана.
    matched = response_status == 200 and (expected_version is None or body.startswith(expected_version + ":"))
    # Первый правильный ответ означает, что можно перейти к серии контрольных запросов.
    if matched:
        break
    print("Ожидаем применения правила:", response_status, body)
    # Небольшая пауза даёт контроллерам время обновить конфигурацию; число повторов ограничено внешним
    # циклом.
    time.sleep(1)
# Этот else относится к циклу: он выполнится только если ни одна попытка не завершилась через break.
else:
    # Явно завершаем проверку с ошибкой и понятной причиной. Ресурсы сохраняются для последующей
    # диагностики.
    raise SystemExit("ОШИБКА: правило не применилось")

# Повторяем запросы, чтобы подтвердить устойчивое поведение, а не один случайный ответ.
for sample in range(30):
    # Выполняем запрос отдельно от проверок: код и тело можно просмотреть в отладчике.
    response_status, body = request(url, headers, 'GET')
    print(response_status, body)
    # При несовпадении assert завершит Python с ошибкой; Bash прекратит испытание и не напечатает УСПЕХ.
    assert response_status == 200, (response_status, body)
    # Дополнительно проверяем версию по телу: одного HTTP 200 недостаточно для доказательства правильной
    # маршрутизации.
    assert expected_version is None or body.startswith(expected_version + ":"), body
PYTHON

kubectl -n "$NS" exec "$POD_V2" -c app -- python -c '
# Меняем только тестовый Pod: удаляем файл-маркер, чтобы /ready снова возвращал 200.
from pathlib import Path
Path("/tmp/unready").unlink()
'

# Ждём фактической готовности Pod; для Ready=false, наоборот, ждём снятия готовности после изменения
# /ready.
kubectl -n "$NS" wait --for=condition=Ready pod/"$POD_V2" --timeout=60s

# Выполняем короткую программу в контейнере app; код передаём аргументом -c интерпретатора.
kubectl -n "$NS" exec -i allowed -c app -- python -  <<'PYTHON'
# Все модули ниже входят в стандартную библиотеку Python 3.8; дополнительных pip-пакетов не требуется.
import time
import urllib.error
import urllib.request

# Прямой HTTP-клиент: отключаем proxy из переменных окружения, чтобы запрос действительно прошёл через
# проверяемый sidecar.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Единый порядок HTTP-проверки: возвращаем пару (код ответа, текст тела). Сетевые сбои здесь не скрываем.
def request(url, headers=None, method="GET"):
    # Собираем URL, заголовки и HTTP-метод. Отправка произойдёт при opener.open, а не при создании
    # Request.
    query = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        # Ожидаем ответ не более 5 секунд; with закроет соединение после чтения результата.
        with opener.open(query, timeout=5) as response:
            # Код нужен для проверки разрешения/запрета; тело преобразуем из байтов в текст для
            # определения версии backend.
            return response.status, response.read().decode()
    # HTTP 4xx/5xx — полноценный ответ сервера: сохраняем его для сравнения с ожидаемым кодом.
    except urllib.error.HTTPError as error:
        # Возвращаем код и тело отказа; сам по себе отказ не означает ошибку теста, если он ожидается.
        return error.code, error.read().decode()

# Множество хранит только разные версии: повторный ответ от той же версии не увеличивает его размер.
versions = set()

# Повторяем запросы, чтобы подтвердить устойчивое поведение, а не один случайный ответ.
for sample in range(100):
    # Сохраняем HTTP-код и тело раздельно для проверки и показа результата комиссии.
    status, body = request("http://demo.pmi-istio-18.svc.cluster.local:8080/")
    # Контроль работоспособности: перед оценкой маршрута или распределения нужен успешный ответ backend.
    assert status == 200, (status, body)
    # В ответе формат версия:Pod; отделяем имя версии от имени конкретной реплики.
    versions.add(body.split(":")[0])
    # Можно остановить сбор, когда реально получены ответы обеих версий.
    if versions == {"v1", "v2"}:
        break
    # Даём endpoints и маршрутам обновиться между пробами, сохраняя ограниченное число запросов.
    time.sleep(0.2)
print("Доступные версии:", versions)

# Наличие двух Deployment в API не является доказательством: требуются ответы и v1, и v2.
assert versions == {"v1", "v2"}, versions
PYTHON

echo "PASS: заявленный сценарий пройден; границы результата указаны в README."
