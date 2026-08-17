# Установка recording rules

Правила из [`yabeda-dashboard.rules.yml`](yabeda-dashboard.rules.yml)
предварительно вычисляют пятиминутные скорости histogram buckets для тяжелых
percentile-запросов дашбордов:

- `Yabeda Rails Kubernetes Overview`;
- `Yabeda Rails Kubernetes Actions`.

Результаты сохраняются как три новые метрики:

- `job_namespace_service_pod_le:rails_request_duration_seconds_bucket:rate5m`;
- `job_namespace_service_pod_controller_action_le:rails_request_duration_seconds_bucket:rate5m`;
- `job_namespace_service_pod_config_le:activerecord_query_duration_seconds_bucket:rate5m`.

Правила должны исполняться тем Prometheus, который выбран как datasource в
Grafana. Исходные серии должны содержать метки `job`, `namespace`, `service` и
`pod`; правила сохраняют эти метки в агрегированных сериях.

## Проверка перед установкой

Проверьте наличие исходных histogram buckets в том же Prometheus:

```promql
count(rails_request_duration_seconds_bucket{job!="",namespace!="",service!="",pod!=""})
```

```promql
count(activerecord_query_duration_seconds_bucket{job!="",namespace!="",service!="",pod!=""})
```

Оба запроса должны вернуть значение больше нуля. Затем проверьте синтаксис
файла правил с помощью `promtool` той же основной версии, что и сервер:

```shell
promtool check rules prometheus-rules/yabeda-dashboard.rules.yml
```

## Ванильный Kubernetes с Prometheus Operator

Этот вариант подходит, если в кластере установлен Prometheus Operator, в том
числе как часть `kube-prometheus` или `kube-prometheus-stack`.

1. Убедитесь, что CRD установлен, и найдите объект Prometheus:

   ```shell
   kubectl api-resources | grep -w PrometheusRule
   kubectl get prometheus --all-namespaces
   ```

2. Посмотрите селекторы правил у нужного Prometheus:

   ```shell
   kubectl -n <prometheus-namespace> get prometheus <prometheus-name> \
     -o yaml
   ```

   В `spec.ruleSelector` указаны метки, по которым выбираются
   `PrometheusRule`, а `spec.ruleNamespaceSelector` определяет допустимые
   namespaces. Для `ruleSelector` значение `{}` выбирает все объекты, а
   отсутствующий селектор не выбирает ни одного. Для
   `ruleNamespaceSelector` значение `{}` разрешает все namespaces, а
   отсутствующий селектор — только namespace самого Prometheus. Если
   `ruleSelector` содержит `matchLabels` или `matchExpressions`, добавьте
   соответствующие метки в `metadata.labels` подготовленного манифеста.

3. Примените правило в namespace, разрешенном
   `ruleNamespaceSelector`:

   ```shell
   kubectl -n <rules-namespace> apply \
     -f prometheus-rules/kubernetes/prometheus-rule.yaml
   ```

4. Проверьте объект:

   ```shell
   kubectl -n <rules-namespace> get prometheusrule \
     yabeda-dashboard-recording -o yaml
   ```

Prometheus Operator сам преобразует `PrometheusRule` в файл правил и инициирует
перезагрузку Prometheus. Если объект существует, но правило не появляется в
Prometheus, почти всегда не совпал `ruleSelector` либо namespace не выбран
`ruleNamespaceSelector`.

Удаление:

```shell
kubectl -n <rules-namespace> delete prometheusrule \
  yabeda-dashboard-recording
```

## Ванильный Kubernetes без Prometheus Operator

Этот вариант нужен, если StatefulSet или Deployment с Prometheus управляется
напрямую. Не используйте его для ресурса, сгенерированного Helm-релизом или
оператором: в таком случае меняйте values/chart либо используйте
`PrometheusRule`.

### 1. Создайте ConfigMap с файлом правил

```shell
PROMETHEUS_NAMESPACE=monitoring

kubectl -n "$PROMETHEUS_NAMESPACE" create configmap \
  yabeda-dashboard-recording-rules \
  --from-file=yabeda-dashboard.rules.yml=prometheus-rules/yabeda-dashboard.rules.yml \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 2. Подключите ConfigMap к pod Prometheus

Добавьте в pod template существующего StatefulSet или Deployment следующие
фрагменты. Имя контейнера при необходимости замените на фактическое:

```yaml
spec:
  template:
    spec:
      containers:
        - name: prometheus
          volumeMounts:
            - name: yabeda-dashboard-recording-rules
              mountPath: /etc/prometheus/yabeda-rules
              readOnly: true
      volumes:
        - name: yabeda-dashboard-recording-rules
          configMap:
            name: yabeda-dashboard-recording-rules
```

Монтируйте каталог целиком, без `subPath`: тогда Kubernetes сможет обновлять
файл после изменения ConfigMap.

### 3. Добавьте путь в конфигурацию Prometheus

В корне `prometheus.yml` добавьте путь к смонтированным файлам, сохранив уже
существующие элементы `rule_files`:

```yaml
rule_files:
  - /etc/prometheus/yabeda-rules/*.yml
```

Изменение pod template запустит rollout. Дождитесь готовности workload:

```shell
kubectl -n "$PROMETHEUS_NAMESPACE" rollout status \
  statefulset/<prometheus-statefulset>
```

Для Deployment замените `statefulset` на `deployment`.

### 4. Обновление правил

Повторно создайте ConfigMap той же командой из шага 1. После обновления
смонтированного файла Prometheus необходимо перечитать конфигурацию. Возможны
два способа:

- вызвать `POST /-/reload`, если Prometheus запущен с
  `--web.enable-lifecycle`;
- выполнить rollout restart workload.

Пример с lifecycle endpoint:

```shell
kubectl -n "$PROMETHEUS_NAMESPACE" port-forward \
  service/<prometheus-service> 9090:9090
```

В другом терминале:

```shell
curl -fsS -X POST http://127.0.0.1:9090/-/reload
```

Альтернатива без lifecycle endpoint:

```shell
kubectl -n "$PROMETHEUS_NAMESPACE" rollout restart \
  statefulset/<prometheus-statefulset>
```

Для постоянной автоматизации обновлений полезен config-reloader sidecar,
который отслеживает ConfigMap и вызывает reload.

## Deckhouse Kubernetes Platform

Для Deckhouse рекомендуемый способ — кластерный ресурс
`CustomPrometheusRules`. Он не имеет namespace и обрабатывается модулем
`prometheus`.

1. Проверьте состояние модуля и наличие CRD:

   ```shell
   d8 k get module prometheus
   d8 k api-resources | grep -w CustomPrometheusRules
   ```

2. Примените подготовленный манифест:

   ```shell
   d8 k apply \
     -f prometheus-rules/deckhouse/custom-prometheus-rules.yaml
   ```

3. Проверьте созданный ресурс:

   ```shell
   d8 k get customprometheusrules \
     yabeda-dashboard-recording -o yaml
   ```

Deckhouse сам создает внутренний `PrometheusRule`, доставляет его в основной
Prometheus и выполняет reload. Перезапуск pod вручную не требуется.

Удаление:

```shell
d8 k delete customprometheusrules yabeda-dashboard-recording
```

### Альтернатива: обычный PrometheusRule в Deckhouse

Deckhouse также может следить за namespaced `PrometheusRule`. Для этого
namespace должен иметь специальную метку:

```shell
d8 k label namespace <rules-namespace> \
  prometheus.deckhouse.io/rules-watcher-enabled="true"

d8 k -n <rules-namespace> apply \
  -f prometheus-rules/kubernetes/prometheus-rule.yaml
```

Используйте этот способ только при необходимости совместимости с общими Helm
charts. Не размещайте пользовательский `PrometheusRule` в namespace Deckhouse:
это вызывает системный alert `D8CustomPrometheusRuleFoundInCluster`. Для
Deckhouse-native конфигурации предпочтителен `CustomPrometheusRules`.

## Проверка после установки

Подождите не менее одного evaluation interval (`1m`) и выполните в Grafana
Explore или Prometheus UI:

```promql
count(job_namespace_service_pod_le:rails_request_duration_seconds_bucket:rate5m)
```

```promql
count(job_namespace_service_pod_controller_action_le:rails_request_duration_seconds_bucket:rate5m)
```

```promql
count(job_namespace_service_pod_config_le:activerecord_query_duration_seconds_bucket:rate5m)
```

Каждый запрос должен вернуть значение больше нуля при наличии трафика. В
Prometheus UI правила группы `yabeda-dashboard-recording` должны иметь
состояние `ok`; то же можно проверить через HTTP API:

```shell
curl -fsS 'http://127.0.0.1:9090/api/v1/rules?type=record' | \
  jq '.data.groups[] | select(.name == "yabeda-dashboard-recording")'
```

Если группа загружена, но результат пустой, проверьте исходные bucket-серии и
метки из раздела «Проверка перед установкой». Если `health` равен `err`, поле
`lastError` в API содержит причину ошибки.

Recording rules не создают историю задним числом. После установки панели
начнут показывать новые точки, а выбранный шестичасовой диапазон заполнится
постепенно.

## Официальная документация

- [Prometheus: defining recording rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/)
- [Prometheus: configuration and reload](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Prometheus Operator API: rule selectors](https://prometheus-operator.dev/docs/api-reference/api/)
- [Deckhouse Prometheus FAQ: alerts and recording rules](https://deckhouse.io/modules/prometheus/faq.html#how-do-i-add-alerts-andor-recording-rules)
- [Deckhouse: CustomPrometheusRules](https://deckhouse.io/modules/prometheus/cr.html#customprometheusrules)
- [Deckhouse operator-prometheus](https://deckhouse.io/modules/operator-prometheus/)
