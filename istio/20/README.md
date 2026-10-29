# 20. Подключение сервисов на обычных ВМ

[Подробный анализ](АНАЛИЗ.md) · [Общие условия](../README.md) · [Таблица](../ТАБЛИЦА.md)

Проверяется настоящий HTTP-сервис на отдельной ВМ с Istio-agent: Pod → ВМ с mTLS,
отказ при неверной identity и восстановление. Подмена ВМ Pod-имитацией недопустима.
Один ServiceEntry с plaintext IP ещё не означает включение ВМ в mesh.

## Предпосылки

Нужна отдельная лабораторная ВМ с Python 3.8 (`python`), входящим портом 8080,
Istio-agent/Envoy совместимой версии и действующим сертификатом **этого mesh**.
На машине с kubectl также нужен `python` ≥3.8 для проверки IPv4/identity.
Предполагается одна маршрутизируемая сеть: Pod могут достигнуть IP ВМ, ВМ —
адреса discovery/CA. Пересекающиеся сети и NAT требуют другой схемы с gateway.
Адрес 198.18.0.20 не должен конфликтовать с реальными маршрутами стенда: это VIP
для перехвата клиентским sidecar, а не IP ВМ и не DNS-запись.

Агент должен перехватывать входящий 8080, его workload labels и ServiceAccount
должны соответствовать выданной identity. Приложение запускается пользователем,
отличным от istio-proxy. Политики ВМ должны разрешать клиенту из `pmi-istio-20`
с ServiceAccount `allowed` обращение к 8080. Тест не ослабляет общие DENY/STRICT.

## Как подготовить агентскую часть

Это отдельная административная предпосылка, **01-prepare не устанавливает агент
по SSH**. Для РЕД ОС 8 и Deckhouse 1.73.x универсальная поддерживаемая команда
установки не подтверждена: сначала согласуйте пакет и способ выдачи identity
с вашей поставкой. Upstream-инструкция с RPM для CentOS не является сертификатом
совместимости РЕД ОС. Не устанавливайте текущий пакет поверх старого control plane.

В изолированной upstream-лаборатории порядок такой:

1. Выберите версию istioctl и VM runtime, совместимую с control plane стенда.
   Для прежней инструкции K3s это Istio 1.21.6, а не актуальный latest.
2. Подготовьте доступ ВМ к discovery/CA. Стандартная upstream-схема использует
   east-west gateway и экспонирование istiod; обычный ingress NodePort 30080
   из пункта 12 этого **не обеспечивает**. Используйте manifests и инструкции
   именно вашей версии. Cluster ID/network должны совпадать с установленным mesh.
3. Создайте отдельный bootstrap namespace и ServiceAccount для ВМ, например
   `vm-lab` и `vm-service`. Он не должен совпадать с удаляемым `pmi-istio-20`.
   Подготовьте WorkloadGroup и конфигурацию для агента. Минимальная форма:

```yaml
apiVersion: networking.istio.io/v1beta1
kind: WorkloadGroup
metadata:
  name: legacy
  namespace: vm-lab
spec:
  metadata:
    labels:
      app: legacy-vm
  template:
    serviceAccount: vm-service
    network: YOUR_MESH_NETWORK
    ports:
      http: 8080
```

4. После создания namespace/ServiceAccount сохраните описание в `workloadgroup.yaml`.
   В каталоге с ограниченным доступом сформируйте bootstrap-файлы. Это пример
   upstream-команды; значения CLUSTER_ID/адрес gateway берутся из вашего стенда,
   доступные флаги проверяются через `istioctl x workload entry configure --help`.

```bash
umask 077
# Укажите существующий cluster ID, не придумывайте новое значение.
: "${CLUSTER_ID:?Укажите cluster ID установленного mesh}"
istioctl x workload entry configure -f workloadgroup.yaml \
  -o ./vm-bootstrap --clusterID "$CLUSTER_ID"
```

5. По инструкции своей версии безопасно доставьте на ВМ root-cert.pem, istio-token,
   cluster.env, mesh.yaml и hosts. Установите согласованный VM runtime, разместите
   сертификат в `/etc/certs`, token в `/var/run/secrets/tokens`, cluster.env в
   `/var/lib/istio/envoy`, mesh.yaml как `/etc/istio/config/mesh`. Обеспечьте права
   istio-proxy на эти файлы, разрешение имени discovery и перехват 8080.
   Не публикуйте token в репозитории/протоколе. Для продолжительной эксплуатации
   нужны согласованные обновление token и ротация сертификатов.
6. Запустите агент (`sudo systemctl start istio` при таком пакете). Проверьте
   журнал `journalctl -u istio`, получение сертификата и `istioctl proxy-status`
   на машине с доступом к control plane. Убедитесь, что это именно ВМ и нужная identity.
   Автоматическая регистрация WorkloadEntry не требуется нашему статическому
   ServiceEntry, но нужна отдельная настройка, если вы хотите проверить auto-registration.

Полная первичная инструкция: [Istio VM installation](https://istio.io/latest/docs/setup/install/virtual-machine/).
Её latest-команды сверяйте с установленной версией. Если доступ к control plane или
runtime для ОС отсутствует, пункт пока **не готов к прогону**, а не пройден.
На стенде с 10 ГБ RAM заранее проверьте бюджет второй ВМ; не запускайте остальные
опыты одновременно.

## Запуск приложения и испытания

На самой ВМ скопируйте `vm-server.py` и запустите в отдельном терминале обычного
пользователя (не istio-proxy):

```bash
python vm-server.py
```

На машине с kubectl, из `istio/20`:

```bash
export VM_IP=192.0.2.20  # Замените на реальный IPv4 вашей ВМ.
export VM_IDENTITY=spiffe://cluster.local/ns/vm-lab/sa/vm-service
# Trust domain, namespace и ServiceAccount должны совпадать с сертификатом ВМ.
bash 01-prepare.sh
# Для K3s вместо предыдущей команды: bash 01-prepare-k3s.sh
bash 02-check.sh
bash 03-cleanup.sh
```

Prepare создаёт только клиентский Pod с sidecar и scoped ServiceEntry,
DestinationRule/VirtualService в `pmi-istio-20`. Check сначала требует HTTP 200
с маркером `pmi-istio-20-real-vm`, меняет ожидаемый SAN на заведомо неверный,
требует 503, возвращает исходный SAN и снова требует 200. При ошибке trap тоже
пытается восстановить policy. Проверки ограниченно ждут доставки xDS.
Обязательный `ISTIO_MUTUAL` не позволяет принять обычный plaintext HTTP за успех.
Код 0 — PASS этой последовательности, ненулевой — ошибка.

Cleanup удаляет только принадлежащий опыту namespace; bootstrap namespace,
системный gateway, агент и файлы ВМ остаются. Учебный сервер остановите Ctrl+C.
После всего цикла для полной очистки отдельной лабораторной ВМ предпочтительно
восстановить её snapshot; bootstrap-ресурсы и gateway удаляйте только если они
созданы исключительно для этой ВМ. Общий Istio удалять не нужно.

## Границы результата

Не проверяются обратный вызов ВМ → Kubernetes, DNS capture, авторизация на ВМ,
запрет plaintext, ротация сертификатов, смена IP, отказоустойчивость или поддержка ОС
производителем. Неверный SAN проверяет аутентификацию сервера, а не RBAC пользователя.
Статический ServiceEntry намеренно отделяет проверку mTLS от auto-registration.
В этой рабочей среде настоящая ВМ и доступный кластер отсутствуют; успешный runtime
не заявляется. См. [анализ](АНАЛИЗ.md) о пользе и эксплуатационной стоимости.
