# 12. Публикация сервисов (входящий трафик)

[Практический разбор: что даёт Istio и что остаётся в сервисе](АНАЛИЗ.md).

**Можно:** Да. **Рекомендация:** Стоит при использовании mesh.

## Как реализуется возможность

В Deckhouse IngressIstioController создаёт gateway; Gateway выбирает его по istio.deckhouse.io/ingress-gateway-class, а VirtualService задаёт host/path → backend. Возможен и ingress-nginx с интеграцией Istio.

## Плюсы, минусы и границы ответственности

Плюс: TLS termination и общие политики входа, маршрутизация к subsets. Минус: отдельная эксплуатация gateway, сертификатов и внешнего LB/DNS.

Нужны доступный ingress controller, внешняя связность и сертификаты. Gateway CR сам не создаёт балансировщик. Тест использует HTTP на выделенном испытательном ingress; production требует HTTPS и проверки цепочки доверия.

Источник: [документация механизма](https://deckhouse.io/modules/istio/examples.html).
Версию/редакцию Deckhouse и условия стенда проверяют по [общему README](../README.md).

## Испытание и критерий

Используем существующий контроллер, создаём только namespace-scoped Gateway/VirtualService с уникальным тестовым host. С рабочей машины через GATEWAY_URL проверяем /allowed → v1, /blocked → 404. Это реальный вход снаружи, не port-forward к backend.

`01-prepare.sh` создаёт изолированные тестовые ресурсы; `02-check.sh` проверяет
заявленный сценарий; `03-cleanup.sh` удаляет namespace `pmi-istio-12` после проверки
метки владельца. Все три файла запускаются независимо через Bash, из любого каталога.
Порядок: prepare → check → сохранение результатов → cleanup. После неудачи сначала
сохраните диагностику, затем выполните cleanup. См. общие предпосылки и коды выхода.

```bash
bash 01-prepare.sh
bash 02-check.sh
bash 03-cleanup.sh
```

Для протокола сохраните версию DKP/Istio, kube-context, образы с digest, вывод команд,
HTTP-результаты и `kubectl -n pmi-istio-12 get pods,svc -o wide`.
Сценарий создан для испытания; фактическое прохождение на Deckhouse пока не подтверждено.

## Внешние параметры

```bash
export GATEWAY_CLASS=pmi-test  # существующий класс IngressIstioController
export GATEWAY_URL=http://192.0.2.10:80  # заменить реальным адресом listener
```

Это примеры, не адреса рабочего стенда. Посмотреть контроллеры:
`kubectl get ingressistiocontrollers.deckhouse.io -o yaml`.
Используйте выделенный испытательный HTTP listener; скрипт не включает его.
Gateway должен разрешать конфигурацию из namespace приложения; при ограничении
`PILOT_SCOPE_GATEWAY_TO_NAMESPACE` потребуется согласованный иной вариант размещения.
VirtualService/DestinationRule экспортированы в d8-ingress-istio для gateway.
Namespace DNS/запись example.invalid не нужны: curl передаёт Host явно.
Проверка с рабочей машины требует сетевого доступа к адресу; HTTP gateway
внутри кластера не считается доказательством внешней публикации.

## Вариант K3s

Для стенда по [инструкции K3s](../K3S-ISTIO-REDOS8.md) используйте отдельные файлы:
`01-prepare-k3s.sh`, `02-check-k3s.sh`, `03-cleanup-k3s.sh`.

```bash
export LAB_IP=192.168.122.50  # заменить реальным IPv4-адресом ВМ K3s
bash 01-prepare-k3s.sh
bash 02-check-k3s.sh
# Сохранить результаты, затем очистить окружение, в том числе после сбоя.
bash 03-cleanup-k3s.sh
```

`LAB_IP` задаётся и для prepare, и для check. Адрес проверки формируется как
`http://${LAB_IP}:30080`; `GATEWAY_CLASS` и внешний `GATEWAY_URL` в этом варианте
не используются. Выполняйте check с рабочей машины, имеющей kubeconfig и сетевой
доступ к ВМ:30080. Запуск на самой ВМ проверит только локальную доступность входа.

Prepare до создания namespace проверяет существующие Deployment/Service
`istio-system/istio-ingressgateway`, Ready Pod с selector `istio=ingressgateway`
и Service типа NodePort, у которого порт 80 опубликован как 30080. Общие ресурсы
Istio скриптами не создаются и не перенастраиваются.

Тестовый Gateway остаётся в namespace `pmi-istio-12`, выбирая Pod gateway в
`istio-system` через `istio: ingressgateway`. VirtualService и DestinationRule
экспортируются в `istio-system`. Установка должна допускать выбор gateway Pod
из другого namespace, как в стандартном профиле инструкции.

Критерий: `/allowed` возвращает HTTP 200 и тело `v1:<имя-Pod>`, `/blocked` — 404.
Check ожидает распространения маршрута и повторяет запрос при временном отказе
соединения. DNS-имя не требуется: Host передаётся явно.

Cleanup проверяет владельца и удаляет только `pmi-istio-12`. Gateway Deployment
и Service в `istio-system` сохраняются для других опытов. У вариантов Deckhouse
и K3s одинаковый тестовый namespace; выполняйте только один вариант за прогон.
