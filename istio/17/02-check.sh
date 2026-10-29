#!/usr/bin/env bash
# Цель пункта: Один ключ сессии выбирает один Pod; разные ключи должны использовать обе реплики.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-17

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
url = 'http://demo.pmi-istio-17.svc.cluster.local:8080/'

# Дополнительные HTTP-заголовки: например, группа A/B, ключ сессии или Host внешнего сервиса.
headers = {}

# Проверяем префикс v1/v2 в теле ответа; None означает, что на этом этапе важен только HTTP-код.
expected_version = None

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
url = "http://demo.pmi-istio-17.svc.cluster.local:8080/"

# Сюда попадут реальные ответы Pod для одного неизменного ключа сессии.
same_key_hosts = set()

# Повторяем запросы, чтобы подтвердить устойчивое поведение, а не один случайный ответ.
for sample in range(20):
    # Сохраняем HTTP-код и тело раздельно для проверки и показа результата комиссии.
    status, body = request(url, {"x-session-key": "fixed-user"})
    # Контроль работоспособности: перед оценкой маршрута или распределения нужен успешный ответ backend.
    assert status == 200, (status, body)
    # Повторы не увеличивают множество: один элемент означает один и тот же Pod.
    same_key_hosts.add(body)
print("Один ключ:", same_key_hosts)

# Для стабильного набора endpoints один ключ должен дать один Pod. Это мягкая привязка, а не гарантия
# хранения сессии.
assert len(same_key_hosts) == 1, same_key_hosts

# Для разных ключей ожидаем распределение по двум доступным Pod.
different_key_hosts = set()

# Повторяем запросы, чтобы подтвердить устойчивое поведение, а не один случайный ответ.
for sample in range(100):
    # Сохраняем HTTP-код и тело раздельно для проверки и показа результата комиссии.
    status, body = request(url, {"x-session-key": f"user-{sample}"})
    # Контроль работоспособности: перед оценкой маршрута или распределения нужен успешный ответ backend.
    assert status == 200, (status, body)
    # Запоминаем каждый встретившийся backend; смена ключа должна позволить выбрать другой Pod.
    different_key_hosts.add(body)
print("Разные ключи:", different_key_hosts)

# Проверяем, что разные ключи не были ошибочно привязаны все к одной реплике.
assert len(different_key_hosts) == 2, different_key_hosts
PYTHON

echo "PASS: заявленный сценарий пройден; границы результата указаны в README."
