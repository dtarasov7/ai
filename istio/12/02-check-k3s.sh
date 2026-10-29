#!/usr/bin/env bash
# Цель пункта: Внешний HTTP-вход: /allowed → 200 от v1, /blocked → 404.
# Запускайте этапы prepare → check → cleanup; после ошибки сначала сохраните диагностику.
# При неожиданной ошибке, неопределённой переменной или сбое части конвейера останавливаем сценарий.
# Очистка запускается отдельно.
set -euo pipefail

# Все имена и проверки привязаны к namespace этого опыта. Не размещайте в нём посторонние ресурсы.
NS=pmi-istio-12
: "${LAB_IP:?Задайте IPv4-адрес ВМ K3s, доступный с рабочей машины}"

# Формируем внешний HTTP-адрес входа. Это адрес ВМ с NodePort, а не ClusterIP backend.
GATEWAY_URL="http://${LAB_IP}:30080"
echo "Проверяем вход через $GATEWAY_URL"

# Проверяем метку владельца: совпадение имени namespace само по себе не даёт права использовать или
# удалять его.
OWNER=$(kubectl get namespace "$NS" -o jsonpath='{.metadata.labels.pmi-istio-owner}')

# При несовпадении владельца останавливаемся; чужой namespace не изменяем и не удаляем.
if [ "$OWNER" != "$NS" ]; then
  echo "ОШИБКА: namespace не принадлежит этому испытанию."
  exit 1
fi

# Ограниченный цикл ожидания маршрута, журнала или endpoints. Нужный результат дополнительно проверяем
# после цикла.
for ATTEMPT in $(seq 1 30); do
  echo "Попытка $ATTEMPT/30"
  if BODY=$(curl --noproxy '*' --silent --show-error --max-time 5 -H 'Host: pmi-istio-12.example.invalid' "${GATEWAY_URL}/allowed"); then
    if [[ "$BODY" == v1:* ]]; then break; fi
    echo "Ожидаем маршрут к v1; получен ответ: $BODY"
  else
    echo "Gateway пока недоступен; повторяем запрос."
  fi
  sleep 1
done
echo "Входящий ответ: $BODY"
[[ "$BODY" == v1:* ]]

# Проверяем HTTP-код отдельно от текста ответа; /allowed должен дать 200, а /blocked — 404.
STATUS=$(curl --noproxy '*' --silent --show-error --max-time 5 -o /dev/null -w '%{http_code}' -H 'Host: pmi-istio-12.example.invalid' "${GATEWAY_URL%/}/allowed")

# Несовпадение HTTP-кода вернёт ненулевой код Bash и не позволит объявить проверку успешной.
test "$STATUS" = 200

# Проверяем HTTP-код отдельно от текста ответа; /allowed должен дать 200, а /blocked — 404.
STATUS=$(curl --noproxy '*' --silent --show-error --max-time 5 -o /dev/null -w '%{http_code}' -H 'Host: pmi-istio-12.example.invalid' "${GATEWAY_URL%/}/blocked")
echo "Несуществующий маршрут: $STATUS"

# Несовпадение HTTP-кода вернёт ненулевой код Bash и не позволит объявить проверку успешной.
test "$STATUS" = 404
echo "PASS: заявленный сценарий пройден; границы результата указаны в README."
