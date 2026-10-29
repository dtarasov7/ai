#!/usr/bin/env bash
# Цель пункта: ServiceEntry открывает маршрут к сервису вне mesh; удаление записи должно закрыть маршрут
# при REGISTRY_ONLY.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-13

# Проверяем метку владельца: совпадение имени namespace само по себе не даёт права использовать или
# удалять его.
OWNER=$(kubectl get namespace "$NS" -o jsonpath='{.metadata.labels.pmi-istio-owner}')

# При несовпадении владельца останавливаемся; чужой namespace не изменяем и не удаляем.
if [ "$OWNER" != "$NS" ]; then
  echo "ОШИБКА: namespace не принадлежит этому испытанию."
  exit 1
fi

# Выполняем Python в контейнере app. Флаг -i передаёт stdin; -c app выбирает приложение, а не sidecar.
# Код и данные описаны в блоке ниже.
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
url = 'http://198.18.0.13:8080/'

# Дополнительные HTTP-заголовки: например, группа A/B, ключ сессии или Host внешнего сервиса.
headers = {'Host': 'external.pmi.invalid'}

# Проверяем префикс v1/v2 в теле ответа; None означает, что на этом этапе важен только HTTP-код.
expected_version = 'external'

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
for sample in range(10):
    # Выполняем запрос отдельно от проверок: код и тело можно просмотреть в отладчике.
    response_status, body = request(url, headers, 'GET')
    print(response_status, body)
    # При несовпадении assert завершит Python с ошибкой; Bash прекратит испытание и не напечатает УСПЕХ.
    assert response_status == 200, (response_status, body)
    # Дополнительно проверяем версию по телу: одного HTTP 200 недостаточно для доказательства правильной
    # маршрутизации.
    assert expected_version is None or body.startswith(expected_version + ":"), body
PYTHON

# Сохраняем ServiceEntry до удаления, чтобы после отрицательной проверки восстановить исходную запись
# этого опыта.
ENTRY=$(kubectl -n "$NS" get serviceentry external -o yaml)

# Удаляем только запись внешнего тестового сервиса: REGISTRY_ONLY должен перестать направлять к нему
# запросы.
kubectl -n "$NS" delete serviceentry external

# Выполняем Python в контейнере app. Флаг -i передаёт stdin; -c app выбирает приложение, а не sidecar.
# Код и данные описаны в блоке ниже.
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

# Istio распространяет настройки асинхронно: разрешаем до 30 попыток, вместо фиксированной длительной
# паузы.
for attempt in range(30):
    try:
        # Сохраняем HTTP-код и тело раздельно для проверки и показа результата комиссии.
        status, body = request("http://198.18.0.13:8080/", {"Host": "external.pmi.invalid"})
    # Ожидаем отказ самого соединения: backend требует mTLS либо маршрут к внешнему сервису удалён.
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        print("Ожидаемый сетевой отказ после удаления записи:", error)
        break
    # После удаления ServiceEntry proxy должен отказать неизвестному направлению. Успешный ответ здесь
    # недопустим.
    if status in (502, 503):
        print("Ожидаемый отказ незарегистрированному сервису:", status, body)
        break
    # Небольшая пауза даёт контроллерам время обновить конфигурацию; число повторов ограничено внешним
    # циклом.
    time.sleep(1)
# Этот else относится к циклу: он выполнится только если ни одна попытка не завершилась через break.
else:
    # Явно завершаем проверку с ошибкой и понятной причиной. Ресурсы сохраняются для последующей
    # диагностики.
    raise SystemExit("ОШИБКА: удаление ServiceEntry не закрыло маршрут")
PYTHON

printf '%s\n' "$ENTRY" | kubectl -n "$NS" apply -f -

# Выполняем Python в контейнере app. Флаг -i передаёт stdin; -c app выбирает приложение, а не sidecar.
# Код и данные описаны в блоке ниже.
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
url = 'http://198.18.0.13:8080/'

# Дополнительные HTTP-заголовки: например, группа A/B, ключ сессии или Host внешнего сервиса.
headers = {'Host': 'external.pmi.invalid'}

# Проверяем префикс v1/v2 в теле ответа; None означает, что на этом этапе важен только HTTP-код.
expected_version = 'external'

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
for sample in range(10):
    # Выполняем запрос отдельно от проверок: код и тело можно просмотреть в отладчике.
    response_status, body = request(url, headers, 'GET')
    print(response_status, body)
    # При несовпадении assert завершит Python с ошибкой; Bash прекратит испытание и не напечатает УСПЕХ.
    assert response_status == 200, (response_status, body)
    # Дополнительно проверяем версию по телу: одного HTTP 200 недостаточно для доказательства правильной
    # маршрутизации.
    assert expected_version is None or body.startswith(expected_version + ":"), body
PYTHON

echo "PASS: заявленный сценарий пройден; границы результата указаны в README."
