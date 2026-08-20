mTLS (Mutual TLS) — это обычный TLS, но сертификат предъявляет и сервер, и клиент. То есть сервер аутентифицирует клиента криптографически, а клиент — сервер.

Если речь про типичный **HTTPS + mTLS + TLS 1.3 поверх TCP**, последовательность примерно такая:

```text
Client                                          Server
  |                                                |
  | -------- TCP SYN ----------------------------> |
  | <------- TCP SYN, ACK ------------------------ |
  | -------- TCP ACK ----------------------------> |
  |                                                |
  | ======== TLS 1.3 handshake ================== |
  |                                                |
  | -------- ClientHello ------------------------> |
  |                                                |
  | <------- ServerHello ------------------------- |
  | <------- EncryptedExtensions ---------------- |
  | <------- CertificateRequest ----------------- |  <-- "покажи клиентский сертификат"
  | <------- Certificate ------------------------- |  <-- сертификат сервера
  | <------- CertificateVerify ------------------- |  <-- сервер доказывает владение private key
  | <------- Finished ---------------------------- |
  |                                                |
  | -------- Certificate ------------------------> |  <-- сертификат клиента
  | -------- CertificateVerify ------------------> |  <-- клиент доказывает владение private key
  | -------- Finished ---------------------------> |
  |                                                |
  | ======== TLS tunnel established ============= |
  |                                                |
  | -------- HTTP GET /api/... ------------------> |  <-- уже зашифровано
  | <------- HTTP 200 OK ------------------------- |  <-- уже зашифровано
```

### Что происходит по шагам

Сначала обычно устанавливается TCP-соединение:

```text
Client -> Server: SYN
Server -> Client: SYN + ACK
Client -> Server: ACK
```

На этом этапе TLS ещё нет. Сервер знает IP/порт клиента, но не знает его TLS identity.

Затем клиент отправляет:

```text
ClientHello
```

В нём, среди прочего:

```text
supported TLS versions: TLS 1.3, TLS 1.2...
supported cipher suites
supported groups
key_share
SNI = api.example.com
ALPN = h2 / http/1.1
random
...
```

Для TLS 1.3 клиент уже отправляет свою часть ephemeral key exchange, например ECDHE key share.

Сервер отвечает:

```text
ServerHello
```

и выбирает:

```text
TLS version
cipher suite
key exchange parameters
```

Например:

```text
TLS_AES_256_GCM_SHA384
ECDHE / X25519
```

После `ServerHello` обе стороны уже могут вычислить handshake encryption keys.

Поэтому дальнейшая часть handshake в TLS 1.3 уже в основном **зашифрована**.

---

### Главное отличие mTLS

В обычном HTTPS сервер отправляет клиенту свой сертификат.

В mTLS сервер дополнительно говорит:

```text
CertificateRequest
```

По смыслу:

> Я хочу, чтобы ты тоже предъявил сертификат клиента.

Дальше сервер отправляет:

```text
Certificate
CertificateVerify
Finished
```

`Certificate` обычно содержит цепочку:

```text
server certificate
        |
        v
Intermediate CA
        |
        v
Root CA
```

Например:

```text
api.example.com
   signed by
Company Intermediate CA
   signed by
Company Root CA
```

Клиент проверяет:

* сертификат ещё действителен;
* hostname соответствует сертификату;
* сертификат подписан доверенным CA;
* цепочка сертификатов корректна;
* назначение сертификата разрешает server authentication;
* при необходимости — revocation/policy constraints.

Но одного сертификата недостаточно.

Поэтому сервер отправляет ещё:

```text
CertificateVerify
```

Это подпись данных handshake **private key сервера**.

Клиент проверяет её public key из сертификата.

Таким образом клиент убеждается не только:

> Этот сертификат принадлежит `api.example.com`.

но и:

> Сервер действительно владеет private key, соответствующим этому сертификату.

---

## Теперь аутентифицируется клиент

Клиент отправляет:

```text
Certificate
```

Например:

```text
client-service-17
       |
       v
Company Client Intermediate CA
       |
       v
Company Root CA
```

Сервер проверяет цепочку.

Например сервер может быть настроен доверять:

```text
/etc/ssl/my-company-client-ca.pem
```

и разрешать только клиентские сертификаты, выданные этим CA.

Затем клиент отправляет:

```text
CertificateVerify
```

Он подписывает handshake своим private key.

То есть клиент доказывает:

```text
У меня есть private key,
соответствующий public key из client certificate.
```

Это очень важный момент.

**Private key никогда не передаётся по сети.**

Передаётся только сертификат с public key и криптографическая подпись.

После проверки сервер отправляет/проверяет `Finished`, клиент — свой `Finished`, и handshake завершается.

---

# Что сервер в итоге знает

После успешного mTLS handshake сервер может знать identity клиента из сертификата, например:

```text
Subject:
CN=payment-service

SAN:
DNS:payment-service.internal
URI:spiffe://prod/payment/payment-service
```

И затем принимать authorization-решение:

```text
spiffe://prod/payment/payment-service
        ↓
может вызывать
POST /payments
```

То есть важно разделять:

```text
mTLS authentication
        ↓
Кто ты?

Authorization
        ↓
Что тебе разрешено?
```

mTLS сам по себе обычно решает прежде всего первую задачу.

---

# А когда отправляется HTTP request?

Только **после успешного TLS handshake**.

Например приложение делает:

```http
GET /users/123 HTTP/1.1
Host: api.example.com
```

Но по сети HTTP уже находится внутри TLS:

```text
TCP packet
└── TLS Application Data
    └── encrypted {
            GET /users/123
            Host: api.example.com
        }
```

Человек, смотрящий сетевой трафик, обычно увидит примерно:

```text
TCP SYN
TCP SYN/ACK
TCP ACK

TLS Client Hello
TLS Server Hello
TLS Application Data
TLS Application Data
TLS Application Data

TLS Application Data
TLS Application Data
```

Сам HTTP request после установления TLS будет зашифрован.

---

## Упрощённо весь mTLS можно представить так

```text
                 CLIENT                         SERVER

                    |                              |
                    |---- "Хочу TLS" ------------>|
                    |                              |
                    |<--- Server certificate ------|
                    |<--- Prove server key --------|
                    |                              |
           Проверяет server cert                   |
                    |                              |
                    |<--- "Дай свой cert" ---------|
                    |                              |
                    |---- Client certificate ----->|
                    |---- Prove client key ------->|
                    |                              |
                    |                    Проверяет client cert
                    |                              |
                    |<====== TLS established =====>|
                    |                              |
                    |---- encrypted HTTP request ->|
                    |<--- encrypted HTTP response -|
```

Взаимная проверка выглядит симметрично:

```text
Client                             Server
  |                                  |
  |         server certificate       |
  |<---------------------------------|
  |                                  |
  | client validates server          |
  |                                  |
  |         client certificate       |
  |--------------------------------->|
  |                                  |
  |                    server validates client
  |                                  |
```

### Почему `CertificateVerify` особенно важен

Представь, что я скопировал чужой публичный сертификат:

```text
client.crt
```

и попробовал подключиться с ним.

Сервер говорит:

```text
CertificateVerify?
```

Мне нужно создать корректную подпись.

Для неё необходим:

```text
client private key
```

которого у меня нет.

Поэтому проверка провалится.

Именно поэтому mTLS требует обычно пару:

```text
client.crt      # можно передавать
client.key      # секрет, никогда не передаётся
```

---

### В TLS 1.2 последовательность немного другая

Если встретишь packet capture старых систем, картина будет ближе к такой:

```text
Client                               Server
  |                                     |
  | -------- ClientHello -------------> |
  | <------- ServerHello -------------- |
  | <------- Certificate -------------- |
  | <------- ServerKeyExchange -------- |
  | <------- CertificateRequest ------- |
  | <------- ServerHelloDone ---------- |
  |                                     |
  | -------- Certificate -------------> |
  | -------- ClientKeyExchange -------> |
  | -------- CertificateVerify -------> |
  | -------- ChangeCipherSpec --------> |
  | -------- Finished ----------------> |
  |                                     |
  | <------- ChangeCipherSpec --------- |
  | <------- Finished ----------------- |
  |                                     |
  | ===== encrypted application ======= |
```

Поэтому если откроешь Wireshark, последовательность будет зависеть от того, используется **TLS 1.2 или TLS 1.3**.

Самая полезная ментальная модель mTLS такая:

```text
1. TCP connection

2. ClientHello
   "Какие параметры TLS поддерживаем?"

3. ServerHello
   "Используем вот эти."

4. Server → Client
   "Вот мой certificate + доказательство владения private key."

5. Client
   Проверяет server certificate.

6. Server → Client
   "А теперь предъяви client certificate."

7. Client → Server
   "Вот мой certificate + доказательство владения private key."

8. Server
   Проверяет client certificate.

9. Обе стороны:
   handshake OK → encryption keys готовы.

10. Только теперь:
    HTTP / gRPC / другой application protocol.
```

И важная деталь: **сертификаты нужны не для непосредственного шифрования HTTP-трафика**. Основное симметричное шифрование трафика выполняется session keys (например, AES-GCM/ChaCha20-Poly1305), полученными в ходе handshake. Сертификаты в первую очередь обеспечивают **аутентификацию сторон и привязку public key к identity**.

