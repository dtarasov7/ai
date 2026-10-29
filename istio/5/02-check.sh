#!/usr/bin/env bash
# Цель пункта: Создаём трафик, ищем метрики и access log; полный результат требует отдельно проверить
# хранилища и трассировку.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-5

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

# Адрес назначения для этого этапа. Внутреннее имя Service разрешает DNS Kubernetes.
url = 'http://demo.pmi-istio-5.svc.cluster.local:8080/pmi-evidence-5'

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
for sample in range(100):
    # Выполняем запрос отдельно от проверок: код и тело можно просмотреть в отладчике.
    response_status, body = request(url, headers, 'GET')
    print(response_status, body)
    # При несовпадении assert завершит Python с ошибкой; Bash прекратит испытание и не напечатает УСПЕХ.
    assert response_status == 200, (response_status, body)
    # Дополнительно проверяем версию по телу: одного HTTP 200 недостаточно для доказательства правильной
    # маршрутизации.
    assert expected_version is None or body.startswith(expected_version + ":"), body
PYTHON

# Выбираем backend v1 для чтения его локальных метрик sidecar; это не проверка центрального Prometheus.
POD=$(kubectl -n "$NS" get pod -l app=demo,version=v1 -o jsonpath='{.items[0].metadata.name}')

# Выполняем короткую программу в контейнере app; код передаём аргументом -c интерпретатора.
kubectl -n "$NS" exec -i "$POD" -c app -- python -  <<'PYTHON'
# Все модули ниже входят в стандартную библиотеку Python 3.8; дополнительных pip-пакетов не требуется.
import re
import time
import urllib.request

# Istio распространяет настройки асинхронно: разрешаем до 30 попыток, вместо фиксированной длительной
# паузы.
for attempt in range(30):
    # Читаем endpoint метрик sidecar внутри того же Pod. Это ещё не доказательство доставки метрик в
    # Prometheus.
    with urllib.request.urlopen("http://127.0.0.1:15090/stats/prometheus", timeout=5) as response:
        # Метрики приходят байтами; переводим их в текст формата Prometheus для построчного разбора.
        metrics = response.read().decode()
    # Оставляем счётчик входящих HTTP 200 (reporter=destination); комментарии и другие серии не
    # учитываем.
    lines = [line for line in metrics.splitlines() if line.startswith("istio_requests_total{") and 'reporter="destination"' in line and 'response_code="200"' in line]
    # У каждой строки последнее поле — значение счётчика; переводим значения в числа для суммирования.
    values = [float(line.rsplit(" ", 1)[1]) for line in lines]
    # Нужен реально зарегистрированный успешный трафик; существование серии с нулём недостаточно.
    if sum(values) > 0:
        print("\n".join(lines))
        break
    # Небольшая пауза даёт контроллерам время обновить конфигурацию; число повторов ограничено внешним
    # циклом.
    time.sleep(1)
# Этот else относится к циклу: он выполнится только если ни одна попытка не завершилась через break.
else:
    # Явно завершаем проверку с ошибкой и понятной причиной. Ресурсы сохраняются для последующей
    # диагностики.
    raise SystemExit("ОШИБКА: нет положительного счётчика входящих HTTP 200")
PYTHON

# Настройки access log распространяются асинхронно; при ожидании продолжаем посылать запросы с маркером.
FOUND=false

# Ограниченный цикл ожидания маршрута, журнала или endpoints. Нужный результат дополнительно проверяем
# после цикла.
for ATTEMPT in $(seq 1 30); do
  echo "Попытка $ATTEMPT/30"

  # Выполняем Python в контейнере app. Флаг -i передаёт stdin; -c app выбирает приложение, а не sidecar.
  # Код и данные описаны в блоке ниже.
  kubectl -n "$NS" exec allowed -c app -- python -c '
# Создаём свежий запрос с уникальным путём-маркером для поиска access log.
# Ответ нужен только для завершения запроса; наличие записи затем проверит Bash.
import urllib.request
urllib.request.urlopen("http://demo.pmi-istio-5.svc.cluster.local:8080/pmi-evidence-5", timeout=5).read()
'

  # Читаем последние записи proxy у backend и ищем уникальный путь нашего запроса; старые посторонние
  # записи не подходят.
  LOGS=$(kubectl -n "$NS" logs -l app=demo -c istio-proxy --tail=500 --prefix=true)
  if [[ "$LOGS" == *"/pmi-evidence-5"* ]]; then
    printf '%s\n' "$LOGS"
    FOUND=true
    break
  fi
  sleep 1
done
if [ "$FOUND" != true ]; then
  echo "ОШИБКА: access log не найден; проверьте provider envoy, Telemetry и задержку применения."
  exit 1
fi
echo "Автоматическая часть пройдена. Полная приёмка НЕ завершена: выполните шаги UI/backend из README. Код 2."

# Код 2 обозначает неполную приёмку: автоматическая часть закончилась, но ещё нужны
# backend/UI-доказательства из README.
exit 2
