#!/usr/bin/env bash
# Цель пункта: Конкурентные медленные запросы должны дать и 200, и 503 с приростом счётчика overflow
# Envoy.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-14

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
url = 'http://demo.pmi-istio-14.svc.cluster.local:8080/'

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

# Снимаем статистику Envoy до нагрузки, чтобы считать только прирост переполнений этого прогона.
BEFORE=$(kubectl -n "$NS" exec allowed -c istio-proxy -- pilot-agent request GET stats)

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

import collections
import concurrent.futures

# Адрес назначения для этого этапа. Внутреннее имя Service разрешает DNS Kubernetes.
url = "http://demo.pmi-istio-14.svc.cluster.local:8080/slow"

# 20 потоков создают одновременную нагрузку: последовательные запросы не проверили бы переполнение
# очереди.
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    # Отправляем 100 запросов на медленный endpoint и дожидаемся всех результатов. Аргумент lambda не
    # используется.
    responses = list(executor.map(lambda _: request(url), range(100)))

# Группируем реальные ответы по HTTP-кодам, чтобы отдельно увидеть успешные запросы и 503.
counts = collections.Counter(status for status, body in responses)
print("HTTP под нагрузкой:", dict(counts))

# Нужны и успехи, и отказы: полный отказ мог бы означать неработающий стенд, а не circuit breaker.
assert counts[200] > 0 and counts[503] > 0, counts

# Посторонние HTTP-коды не принимаем за успешное испытание ограничения очереди.
assert set(counts) <= {200, 503}, counts
PYTHON

# Снимаем статистику после нагрузки; успешный опыт требует роста счётчика переполнения очереди.
AFTER=$(kubectl -n "$NS" exec allowed -c istio-proxy -- pilot-agent request GET stats)
# Счётчик доказывает overflow, а не произвольный 503 со стороны приложения.
# Передаём оба снимка статистики в Python через stdin; маркер разделяет состояния до и после.
printf '%s\n---SPLIT---\n%s\n'  "$BEFORE" "$AFTER" |   kubectl -n "$NS" exec -i allowed -c app -- python -c '
# Все модули ниже входят в стандартную библиотеку Python 3.8; дополнительных pip-пакетов не требуется.
import sys

# Bash передал два снимка статистики через stdin; разделяем их по специальной строке-маркеру.
before, after = sys.stdin.read().split("---SPLIT---", 1)

# Суммируем только переполнения очереди для тестового сервиса, исключая статистику чужого трафика.
def overflow(stats):
    # Сюда складываем числовые значения нужного счётчика из разных upstream-кластеров proxy.
    values = []
    # Разбираем текст статистики Envoy построчно: каждая строка содержит имя и значение счётчика.
    for line in stats.splitlines():
        # Оставляем именно upstream_rq_pending_overflow нашего сервиса: это доказательство переполнения,
        # а не любого 503.
        if "demo.pmi-istio-14.svc.cluster.local" in line and ".upstream_rq_pending_overflow:" in line:
            print(line)
            # Отделяем число после последнего двоеточия и преобразуем его из текста в целое.
            values.append(int(line.rsplit(":", 1)[1].strip()))
    # Возвращаем общий счётчик переполнений по всем совпавшим upstream.
    return sum(values)

# Сначала считаем значение до нагрузки, чтобы старые отказы не дали ложное прохождение.
before_count = overflow(before)

# Затем считаем значение после нагрузки; сравнивать нужно прирост, а не просто ненулевое значение.
after_count = overflow(after)
print("Overflow до/после:", before_count, after_count)

# Рост счётчика подтверждает, что именно этот прогон вызвал переполнение очереди Envoy.
assert after_count > before_count, (before_count, after_count)
'
echo "PASS: заявленный сценарий пройден; границы результата указаны в README."
