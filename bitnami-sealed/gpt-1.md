Bitnami **Sealed Secrets** — это Kubernetes-решение для GitOps: обычный `Secret` локально шифруется в `SealedSecret`, его можно хранить в Git, а расшифровать может только controller внутри целевого кластера. Проект состоит из controller/operator в кластере и CLI `kubeseal`. ([GitHub][1])

## Как это работает

`kubeseal` берёт публичный сертификат controller’а и шифрует данные секрета. В Git попадает объект:

```yaml
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: mysecret
  namespace: mynamespace
spec:
  encryptedData:
    password: AgB...
```

Controller видит `SealedSecret`, расшифровывает его приватным ключом внутри кластера и создаёт обычный Kubernetes `Secret`. Приватный ключ хранится в кластере как Kubernetes Secret; без него восстановить исходный секрет нельзя. ([GitHub][1])

## Установка

Через Helm:

```bash
helm repo add sealed-secrets https://bitnami.github.io/sealed-secrets
helm install sealed-secrets \
  -n kube-system \
  --set-string fullnameOverride=sealed-secrets-controller \
  sealed-secrets/sealed-secrets
```

`fullnameOverride` удобен, потому что `kubeseal` по умолчанию ищет controller с именем `sealed-secrets-controller` в `kube-system`. ([GitHub][1])

CLI:

```bash
brew install kubeseal
```

На Linux обычно скачивают tar.gz из GitHub Releases и кладут `kubeseal` в `/usr/local/bin`. ([GitHub][1])

## Базовое использование

Создать Secret локально, не применяя его в кластер:

```bash
echo -n 'super-password' | kubectl create secret generic db-secret \
  --dry-run=client \
  --from-file=password=/dev/stdin \
  -n app \
  -o yaml > secret.yaml
```

Зашифровать:

```bash
kubeseal -f secret.yaml -w sealed-secret.yaml
```

Закоммитить `sealed-secret.yaml` в Git и применить:

```bash
kubectl apply -f sealed-secret.yaml
kubectl get secret db-secret -n app
```

Важно: по умолчанию `SealedSecret` привязан к **имени** и **namespace**. Если поменять `metadata.name` или `metadata.namespace`, controller не сможет расшифровать объект. ([GitHub][1])

## Scopes

Есть 3 режима:

```bash
# default: привязка к name + namespace
kubeseal --scope strict

# можно переименовывать secret внутри того же namespace
kubeseal --scope namespace-wide

# можно использовать в любом namespace и с любым именем
kubeseal --scope cluster-wide
```

`strict` — самый безопасный дефолт. `cluster-wide` удобен для shared manifests, но слабее с точки зрения изоляции. ([GitHub][1])

## Обновление секрета

Добавить новый ключ без расшифровки старых:

```bash
echo -n 'new-value' | kubectl create secret generic db-secret \
  --dry-run=client \
  --from-file=newkey=/dev/stdin \
  -n app \
  -o json | kubeseal --merge-into sealed-secret.yaml
```

Для частичного обновления существующего Kubernetes `Secret` есть аннотация:

```yaml
sealedsecrets.bitnami.com/patch: "true"
```

Тогда controller не удалит ключи, которых нет в `SealedSecret`. ([GitHub][1])

## Ротация ключей

Controller автоматически создаёт новый sealing key каждые 30 дней, но старые ключи не удаляются, чтобы старые `SealedSecret` продолжали расшифровываться. Это **не заменяет ротацию самих паролей/API keys**. Если приватный sealing key утёк, нужно сначала сгенерировать новый sealing key, потом заменить реальные секреты и заново зашифровать их. ([GitHub][1])

Бэкап ключей controller’а критичен:

```bash
kubectl get secret -n kube-system \
  -l sealedsecrets.bitnami.com/sealed-secrets-key \
  -o yaml > sealed-secrets-keys-backup.yaml
```

Этот файл содержит приватные ключи и должен храниться максимально защищённо. ([GitHub][1])

## Сильные стороны

Главный плюс — простая GitOps-модель: секреты можно хранить рядом с манифестами, использовать Argo CD/Flux, делать code review и не держать plaintext в репозитории. Инструмент нативен для Kubernetes: CRD, controller, YAML, `kubectl`, Helm. Хорошо подходит для команд, которым нужен простой “encrypt before commit” без внешнего Vault/KMS.

Ещё плюс — асимметричная криптография: разработчику нужен только публичный ключ для шифрования; расшифровка возможна только в кластере. Это удобно для CI/CD: pipeline может создавать `SealedSecret`, но не обязан иметь доступ к plaintext после шифрования.

## Слабые стороны

Главная слабость — зависимость от приватного ключа controller’а. Потеряли ключи и кластер — старые `SealedSecret` больше не расшифровать. Утёк приватный ключ — все старые sealed secrets, доступные атакующему, считаются скомпрометированными.

Вторая слабость — это не полноценный secrets manager. Нет динамических секретов, lease/TTL, audit доступа к значениям, автоматической ротации паролей в БД, fine-grained runtime access как в Vault/External Secrets + cloud KMS.

Третья — операционные нюансы: секрет шифруется под конкретный cluster key, namespace и name. Это повышает безопасность, но мешает переиспользовать один YAML между окружениями, если не использовать менее строгие scopes.

## Когда выбирать

Хороший выбор: GitOps для Kubernetes, небольшая/средняя команда, секреты меняются не слишком часто, хочется простого решения без Vault.

Не лучший выбор: строгие compliance-требования, динамические креды, централизованное управление секретами между многими платформами, потребность в KMS/HSM, регулярная автоматическая ротация и аудит чтения секретов.

[1]: https://github.com/bitnami/sealed-secrets "GitHub - bitnami/sealed-secrets: A Kubernetes controller and tool for one-way encrypted Secrets · GitHub"

