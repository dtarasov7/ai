Да. Для вашей схемы я бы **не делал Windows CA или Vault непосредственным CA для каждого pod**. Оптимальная архитектура — выдать отдельный промежуточный CA специально для Istio, подписанный корпоративным Windows УЦ:

```text
Corporate Root CA
        │
        ▼
Corporate Issuing CA / AD CS
        │
        │ подписывает CA:TRUE
        ▼
DKP / Istio Intermediate CA
        │
        │ ключ находится у Istio
        ▼
istiod
        │
        ├── spiffe://cluster.local/ns/app1/sa/service1
        ├── spiffe://cluster.local/ns/app2/sa/service2
        └── ...
             короткоживущие workload certificates
```

В результате все mTLS-сертификаты Istio будут строить цепочку до вашего корпоративного Root CA, но Windows CA не придется обслуживать огромный поток короткоживущих сертификатов. Это соответствует модели Istio: workload генерирует ключ и CSR, а `istiod` автоматически выдает и ротирует SPIFFE-сертификаты. ([Istio][1])

### Как это сделать в Deckhouse

У Deckhouse есть для этого штатная настройка `istio.settings.ca`. Она принимает сертификат CA, его приватный ключ, цепочку и root CA. ([Deckhouse][2])

Я бы сделал отдельный сертификат примерно:

```text
CN = DKP-PROD-Istio-CA
Basic Constraints:
    CA = TRUE
    pathLen = 0

Key Usage:
    Certificate Sign
    CRL Sign
    Digital Signature
```

Важно: **не передавайте в Kubernetes приватный ключ корпоративного Root CA или корпоративного Issuing CA**. Создайте отдельный ключ именно для `DKP-PROD-Istio-CA`.

Например, ключ и CSR можно создать на защищенной Linux-машине:

```bash
openssl genrsa -out istio-ca.key 3072

openssl req \
  -new \
  -key istio-ca.key \
  -out istio-ca.csr \
  -subj "/O=MyCompany/OU=Kubernetes/CN=DKP-PROD-Istio-CA"
```

CSR отдаете Windows AD CS и подписываете шаблоном **Subordinate CA**, то есть итоговый сертификат обязательно должен иметь `CA:TRUE`.

На выходе должно получиться примерно:

```text
istio-ca.key             # private key Istio intermediate
istio-ca.crt             # DKP-PROD-Istio-CA

corporate-issuing-ca.crt # если имеется intermediate AD CS
corporate-root-ca.crt    # корпоративный Root
```

Проверить:

```bash
openssl x509 -in istio-ca.crt -noout -text
```

И:

```bash
openssl verify \
  -CAfile corporate-root-ca.crt \
  -untrusted corporate-issuing-ca.crt \
  istio-ca.crt
```

Должно быть:

```text
istio-ca.crt: OK
```

### Настройка Deckhouse

Лучше отредактировать существующий `ModuleConfig`, чтобы не ошибиться с версией schema конкретно в вашем DKP 1.74:

```bash
d8 k edit mc istio
```

Добавить:

```yaml
spec:
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

Deckhouse прямо описывает `ca.cert` как root или intermediate CA, `ca.key` — его приватный ключ, `ca.chain` — цепочку для intermediate, а `ca.root` — root CA. ([Deckhouse][2])

Если у вас цепочка:

```text
Root
  └─ Corp-CA-01
       └─ Corp-CA-02
            └─ Istio-CA
```

то логика будет:

```text
ca.cert  = Istio-CA
ca.key   = private key Istio-CA

ca.chain =
    Corp-CA-02
    Corp-CA-01

ca.root =
    Root
```

### А где здесь Vault?

С учетом того, что у вас **Vault OSS 2.0.4 на одном сервере**, я бы **не ставил его в runtime-путь выдачи сертификатов Istio**.

Причина простая. Workload-сертификаты Istio регулярно ротируются. Если сделать:

```text
Pod
 ↓
istio-csr
 ↓
cert-manager
 ↓
Vault
 ↓
PKI
```

то доступность Vault становится частью доступности PKI service mesh. `istio-csr` действительно умеет отдавать запросы cert-manager, а cert-manager умеет использовать Vault Issuer. ([cert-manager][3])

Но при одном экземпляре Vault получится:

```text
              ┌──── SPOF ────┐
Pod → Istio → cert-manager → Vault single node
                             ↓
                       certificates
```

Существующие сертификаты при падении Vault продолжат работать до expiration, но новые workload и последующие ротации начнут зависеть от восстановления Vault.

При штатной схеме Deckhouse:

```text
                 Corporate PKI
                       │
              подписывает редко
                       ▼
                 Istio CA cert
                       │
                       ▼
Pod ──────────────→ istiod
                      │
                      └─ подписывает workload CSR
```

Windows CA и Vault вообще не нужны в момент обычной работы mesh.

### Когда всё-таки имеет смысл Vault

Есть один существенный случай: корпоративная политика говорит:

> «Приватный ключ любого CA категорически запрещено хранить в Kubernetes/etcd».

Тогда `settings.ca` вам концептуально не подходит, потому что Deckhouse требуется `ca.key`. В этом случае имеет смысл проектировать:

```text
Corporate Windows CA
          │
          ▼
   Vault Intermediate CA
          │
          ▼
      Vault PKI
          ▲
          │
     cert-manager
          ▲
          │
       istio-csr
          ▲
          │
        Istio
```

`istio-csr` специально предназначен для замены встроенного CA Istio внешним issuer и поддерживает Vault через cert-manager. ([cert-manager][4])

Но для **Deckhouse-managed Istio** это уже не просто настройка `settings.ca`: нужно изменять поведение Istio CA/control plane. В документации Deckhouse штатным механизмом является именно `settings.ca`; прямой поддерживаемой настройки `Vault → istio-csr` в модуле я не нашел. Поэтому такую схему я бы согласовывал с поддержкой Deckhouse перед production.

И в этом варианте сначала сделал бы Vault HA, а не single-host.

### Еще один важный нюанс

Корпоративный CA не изменяет модель идентичности Istio. Внутри workload-сертификата будет не обычный:

```text
CN=service01.corp.local
```

а SPIFFE identity вроде:

```text
URI SAN:
spiffe://cluster.local/ns/payments/sa/payment-api
```

Это нормально. Корпоративный PKI предоставляет **корень доверия**, а Istio сохраняет свою модель service identity. ([Istio][1])

И отдельно: **сертификаты Istio mTLS и сертификаты на Istio Ingress Gateway — две разные задачи**. Для `https://app.company.ru` можно выпускать обычный корпоративный DNS-сертификат через Vault/cert-manager/AD CS, а `settings.ca` использовать для внутреннего service-to-service mTLS.

**Для вашей инфраструктуры я рекомендую именно:**

```text
Windows Corporate CA
        ↓
выдать отдельный Subordinate CA
        ↓
DKP-PROD-Istio-CA
        ↓
Deckhouse settings.ca
        ↓
Istio workload SPIFFE certificates
```

Vault 2.0.4 при этом можно оставить для других PKI/secret-задач; делать single-node Vault обязательной зависимостью Istio смысла нет. Vault 2.0.4 действительно является актуальным релизом ветки 2.0, выпущенным 4 августа 2026 года. ([HashiCorp Developer][5])

Если хотите, следующим сообщением могу дать **полную пошаговую инструкцию именно для `Windows AD CS → CSR → Deckhouse 1.74 → Istio`**, включая шаблон сертификата AD CS, `openssl.cnf`, готовый `ModuleConfig` и команды проверки цепочки внутри Envoy.

[1]: https://istio.io/latest/docs/concepts/security/?utm_source=chatgpt.com "Istio / Security"
[2]: https://deckhouse.io/modules/istio/configuration.html?utm_source=chatgpt.com "Configuration | istio | Deckhouse"
[3]: https://cert-manager.io/docs/usage/istio-csr/installation/?utm_source=chatgpt.com "Installing istio-csr - cert-manager Documentation"
[4]: https://cert-manager.io/v1.18-docs/usage/istio-csr/?utm_source=chatgpt.com "Securing Istio Service Mesh - cert-manager Documentation"
[5]: https://developer.hashicorp.com/vault/docs/updates/release-notes?utm_source=chatgpt.com "Release notes - 2.x | Vault | HashiCorp Developer"
