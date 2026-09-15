# Deckhouse v1.74 / Istio: использование корпоративных сертификатов Windows AD CS

## Целевая схема

Рекомендуемая модель:

```text
Corporate Root CA
  └─ Corporate Issuing CA / Windows AD CS
       └─ DKP-PROD-Istio-CA  (Intermediate CA, CA:TRUE, pathLen=0)
            └─ istiod
                 └─ workload SPIFFE certificates для pod'ов Istio mesh
```

Идея: корпоративный Windows УЦ подписывает выделенный промежуточный CA для Istio. Далее `istiod` сам выпускает и ротирует короткоживущие workload-сертификаты для Envoy sidecar'ов. Vault OSS single-node не включается в runtime-путь выдачи сертификатов Istio.

## 0. Предварительные решения

Утвердить с ИБ:

1. Имя CA: например `DKP-PROD-Istio-CA`.
2. Область применения: только workload mTLS внутри Deckhouse/Istio.
3. Срок действия Intermediate CA: обычно 1–3 года, по внутреннему регламенту.
4. Key Usage: `Certificate Sign`, `CRL Sign`, при необходимости `Digital Signature`.
5. Basic Constraints: `CA=TRUE`, `pathLen=0`.
6. Где хранится приватный ключ Istio CA: в Kubernetes/Deckhouse как секрет; ключи корпоративного Root/Issuing CA в кластер не передаются.
7. Регламент продления: начать процедуру не позднее чем за 60–90 дней до истечения.

## 1. Подготовить openssl.cnf для CSR

Файл `istio-ca-openssl.cnf`:

```ini
[ req ]
default_bits       = 3072
prompt             = no
default_md         = sha256
distinguished_name = dn
req_extensions     = v3_req

[ dn ]
O  = MyCompany
OU = Kubernetes
CN = DKP-PROD-Istio-CA

[ v3_req ]
basicConstraints = critical, CA:true, pathlen:0
keyUsage = critical, keyCertSign, cRLSign, digitalSignature
subjectKeyIdentifier = hash
```

Важно: CSR может содержать желаемые extensions, но окончательные extensions задаются шаблоном Windows AD CS. После выпуска обязательно проверить итоговый сертификат.

## 2. Сгенерировать ключ и CSR

На защищенной Linux-машине или в выделенном административном контуре:

```bash
umask 077
openssl genrsa -out istio-ca.key 3072
openssl req -new -key istio-ca.key -out istio-ca.csr -config istio-ca-openssl.cnf
```

Проверить CSR:

```bash
openssl req -in istio-ca.csr -noout -text
```

## 3. Подписать CSR в Windows AD CS

### Вариант A: через certreq

На Windows-хосте, где доступна команда `certreq`:

```powershell
certreq -submit -attrib "CertificateTemplate:SubCA" istio-ca.csr istio-ca.crt
```

Название шаблона (`SubCA`, `SubordinateCA` или другое) зависит от вашей AD CS. Главное требование: итоговый сертификат должен быть CA-сертификатом, а не обычным TLS-сертификатом.

### Вариант B: через консоль Certification Authority

1. Открыть `Certification Authority`.
2. Выбрать нужный Issuing CA.
3. `All Tasks` → `Submit new request`.
4. Выбрать `istio-ca.csr`.
5. Выпустить по шаблону Subordinate Certification Authority.
6. Экспортировать сертификат в Base-64 X.509 (`.cer`/`.crt`).

## 4. Проверить выпущенный сертификат

На Linux-хосте:

```bash
openssl x509 -in istio-ca.crt -noout -text
```

Проверить, что есть:

```text
Basic Constraints: critical
    CA:TRUE, pathlen:0
Key Usage: critical
    Certificate Sign, CRL Sign
```

Проверить цепочку:

```bash
cat corporate-issuing-ca.crt > corporate-chain.crt

openssl verify \
  -CAfile corporate-root-ca.crt \
  -untrusted corporate-chain.crt \
  istio-ca.crt
```

Ожидаемый результат:

```text
istio-ca.crt: OK
```

Если корпоративных intermediate CA несколько, порядок в `corporate-chain.crt` обычно от ближайшего к Istio CA вверх к Root CA:

```text
Corporate-Issuing-CA-02
Corporate-Issuing-CA-01
```

## 5. Привести ключ к PKCS#8 при необходимости

Если Deckhouse/Istio ожидает `BEGIN PRIVATE KEY`, а ключ в формате `BEGIN RSA PRIVATE KEY`, конвертировать:

```bash
openssl pkcs8 -topk8 -nocrypt -in istio-ca.key -out istio-ca.pkcs8.key
```

Дальше использовать `istio-ca.pkcs8.key`.

## 6. Подготовить ModuleConfig istio

Получить текущий объект:

```bash
d8 k get mc istio -o yaml > istio-mc-before.yaml
```

Отредактировать:

```bash
d8 k edit mc istio
```

Пример целевого фрагмента:

```yaml
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: istio
spec:
  version: 3
  enabled: true
  settings:
    ca:
      cert: |
        -----BEGIN CERTIFICATE-----
        <DKP-PROD-Istio-CA>
        -----END CERTIFICATE-----
      key: |
        -----BEGIN PRIVATE KEY-----
        <PRIVATE KEY DKP-PROD-Istio-CA>
        -----END PRIVATE KEY-----
      chain: |
        -----BEGIN CERTIFICATE-----
        <CORPORATE ISSUING CA>
        -----END CERTIFICATE-----
      root: |
        -----BEGIN CERTIFICATE-----
        <CORPORATE ROOT CA>
        -----END CERTIFICATE-----
```

Если есть несколько corporate issuing CA:

```yaml
      chain: |
        -----BEGIN CERTIFICATE-----
        <CORPORATE ISSUING CA 02>
        -----END CERTIFICATE-----
        -----BEGIN CERTIFICATE-----
        <CORPORATE ISSUING CA 01>
        -----END CERTIFICATE-----
```

## 7. Проверить применение Deckhouse

```bash
d8 k get mc istio -o yaml
```

Проверить pod'ы istiod. Namespace может отличаться в зависимости от установки Deckhouse:

```bash
d8 k get pods -A | grep -i istiod
d8 k get pods -A | grep -i istio
```

Проверить события и ошибки:

```bash
d8 k get events -A --sort-by=.metadata.creationTimestamp | tail -100
```

## 8. Создать тестовый namespace и включить injection

Пример:

```bash
d8 k create ns istio-pki-test
```

Посмотреть используемую revision/label-модель Deckhouse Istio:

```bash
d8 k get ns --show-labels | grep istio
```

Варианты включения injection зависят от revision-based установки. Частые варианты:

```bash
d8 k label ns istio-pki-test istio-injection=enabled
```

или:

```bash
d8 k label ns istio-pki-test istio.io/rev=<REVISION>
```

## 9. Развернуть тестовые сервисы

```bash
d8 k -n istio-pki-test create deploy sleep --image=curlimages/curl -- sleep 365d
d8 k -n istio-pki-test create deploy httpbin --image=kennethreitz/httpbin
d8 k -n istio-pki-test expose deploy httpbin --port 80 --target-port 80
```

Проверить наличие sidecar'ов:

```bash
d8 k -n istio-pki-test get pods
```

В pod'ах должно быть по два контейнера: приложение и `istio-proxy`.

## 10. Проверить сертификаты Envoy

Получить имя pod'а:

```bash
POD=$(d8 k -n istio-pki-test get pod -l app=sleep -o jsonpath='{.items[0].metadata.name}')
```

Если доступен `istioctl`:

```bash
istioctl proxy-config secret "$POD" -n istio-pki-test
```

Для детального вывода:

```bash
istioctl proxy-config secret "$POD" -n istio-pki-test -o json > proxy-secrets.json
```

Искомые признаки:

1. Есть workload certificate.
2. В SAN присутствует URI вида `spiffe://cluster.local/ns/istio-pki-test/sa/default`.
3. Цепочка завершается корпоративным Root CA.
4. Срок действия workload certificate короткий и будет ротироваться автоматически.

## 11. Проверить mTLS STRICT

Создать PeerAuthentication:

```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-pki-test
spec:
  mtls:
    mode: STRICT
```

Применить:

```bash
d8 k apply -f peer-authentication-strict.yaml
```

Проверить вызов из pod'а с sidecar:

```bash
d8 k -n istio-pki-test exec deploy/sleep -c sleep -- curl -sS http://httpbin/status/200 -o /dev/null -w '%{http_code}\n'
```

Ожидаемо:

```text
200
```

Проверить, что трафик без sidecar не проходит. Создать namespace без injection:

```bash
d8 k create ns no-mesh-test
d8 k -n no-mesh-test create deploy curl --image=curlimages/curl -- sleep 365d
```

Попытаться вызвать сервис в mesh:

```bash
d8 k -n no-mesh-test exec deploy/curl -- curl -sS --max-time 5 http://httpbin.istio-pki-test.svc.cluster.local/status/200
```

При STRICT mTLS такой вызов должен завершиться ошибкой/таймаутом/сбросом соединения в зависимости от политики и маршрутизации.

## 12. Acceptance criteria для ИБ

Схема считается внедренной, если выполнены условия:

1. `DKP-PROD-Istio-CA` имеет `CA:TRUE`, `pathLen=0`, `keyCertSign`, `cRLSign`.
2. `openssl verify` подтверждает цепочку до корпоративного Root CA.
3. В Deckhouse `ModuleConfig/istio` содержит `settings.ca.cert/key/chain/root`.
4. `istiod` работает без ошибок выпуска сертификатов.
5. Workload certificate содержит SPIFFE URI SAN.
6. Workload certificate подписан `DKP-PROD-Istio-CA`.
7. При `PeerAuthentication STRICT` трафик из mesh проходит, а трафик без sidecar блокируется.
8. В мониторинге есть контроль срока действия Istio CA и ошибок SDS/CSR.

## 13. Эксплуатация и ротация

### Мониторинг

Контролировать:

1. `notAfter` у Istio Intermediate CA.
2. Ошибки istiod, связанные с CA, CSR, SDS, Secret Discovery Service.
3. Состояние pod'ов istiod.
4. Массовые ошибки mTLS после изменения цепочки.

### Плановая ротация Intermediate CA

Рекомендуемый подход:

1. Выпустить новый `DKP-PROD-Istio-CA-v2` заранее.
2. Проверить цепочку offline.
3. Применить в тестовом кластере/namespace.
4. Согласовать окно изменений.
5. Обновить `settings.ca` в production.
6. Перезапустить или дождаться обновления workloads по регламенту Deckhouse/Istio.
7. Проверить, что новые workload certificates выданы новой цепочкой.
8. Сохранить old/new evidence для ИБ.

## 14. Почему не Vault OSS single-node в runtime-пути Istio

Вариант через `cert-manager` + `istio-csr` + Vault технически возможен, но для текущей вводной он менее предпочтителен:

```text
Pod / Envoy → istio-csr → cert-manager → Vault PKI → certificate
```

Если Vault развернут на одном хосте, он становится SPOF для выпуска новых и ротации существующих workload certificates. Уже выданные сертификаты будут работать до истечения, но новые pod'ы и последующие ротации зависят от доступности Vault.

Использовать Vault в этой схеме стоит только если ИБ запрещает хранить приватный ключ любого CA в Kubernetes. Тогда сначала нужно проектировать Vault HA, регламент восстановления, мониторинг SLA и поддержку Deckhouse-managed Istio с внешним issuer.

## 15. Источники

- Deckhouse Kubernetes Platform, модуль `istio`, параметр `settings.ca`: https://deckhouse.io/modules/istio/configuration.html
- Istio, Plug in CA Certificates: https://istio.io/latest/docs/tasks/security/cert-management/plugin-ca-cert/
- Istio Security / mTLS and workload identity: https://istio.io/latest/docs/concepts/security/
