Ниже — практическая проработка вопроса безопасности и anti-DoS для хранения фото/видео, загружаемых пользователями, в Yandex Cloud Object Storage / S3-совместимом хранилище.

Главная идея: **нельзя просто принимать файлы из браузера и складывать их в S3**. Нужен многослойный pipeline:

> клиент → backend-контроль → временное приватное хранилище → валидация/переупаковка → финальное хранилище → CDN → очистка/квоты/мониторинг.

---

## 1. Что важно учитывать

### 1.1 S3/Yandex Object Storage не “переполняется” в классическом смысле

Объектное облачное хранилище обычно масштабируется автоматически. Проблема “DOS” здесь чаще всего не в том, что диск закончится, а в том, что злоумышленник или ошибочный сценарий может:

- залить огромный объем файлов;
- создать миллионы мелких объектов;
- вызвать дорогой трафик из хранилища/CDN;
- перегрузить процессор/очереди обработки видео;
- создать огромные счета за хранение, запросы, egress и processing.

То есть нужно защищаться не только от “файла”, а от **потока файлов, стоимости обработки и неправильного доступа**.

---

## 2. Модель угроз

### 2.1 Злоумышленник загружает вредоносный файл

Примеры:

- файл с расширением `.jpg`, но внутри исполняемый код;
- polyglot-файл: одновременно изображение и archive/executable;
- malicious MP4/WEBM с уязвимостями в ffmpeg/ImageMagick;
- SVG со скриптами;
- анимированный GIF с огромным числом кадров;
- “zip bomb” или “pixel bomb”: маленький файл, который при декодировании занимает огромную память/CPU.

### 2.2 Upload flooding / storage abuse

- пользователь или бот загружает тысячи видео;
- несколько аккаунтов массово загружают файлы;
- anonymous upload без аутентификации;
- атака через multipart upload;
- атака через presigned URLs, если они выдаются без ограничений.

### 2.3 Cost DoS

- огромные видео;
- высокая частота запросов к хранилищу;
- много GET-запросов из origin без CDN;
- хранение оригиналов “навсегда”;
- отсутствие lifecycle rules;
- дублирование одинаковых файлов;
- отсутствие hard quotas в приложении.

### 2.4 Методы атак через хранение

- публичная запись в bucket;
- публичный bucket с listing;
- неправильные IAM-роли;
- long-lived access keys в браузере;
- public presigned URLs;
- bucket website hosting включенный и позволяющий обслуживать HTML/JS;
- CORS открыт на `*`;
- отсутствие TLS / signed URLs / CDN.

---

## 3. Рекомендуемая архитектура

### 3.1 Общая схема

```text
Browser
  ↓
Backend API: auth, quota, rate limit, upload ticket
  ↓
Temporary staging bucket: private, TTL 24–72h
  ↓
Processing worker: validation, AV, transcoding, metadata strip
  ↓
Media bucket: public-read only or private via signed URLs
  ↓
CDN
  ↓
Cleanup / lifecycle / monitoring
```

### 3.2 Bucket-ы

Желательно разделить хранилище на несколько bucket-ов:

| Bucket | Назначение | Доступ |
|---|---|---|
| `staging` | временные оригиналы после загрузки | private, только backend/worker |
| `quarantine` | подозрительные файлы | private, короткий TTL |
| `media` | обработанные фото/видео для показа | public-read только через CDN или signed URLs |
| `archive` | долгосрочное хранение, если нужно | private, lifecycle/cold storage |

Не используйте один bucket для всего.

---

## 4. Контроль загрузки и защита от DoS

### 4.1 Не доверяйте браузеру

Клиентские ограничения в `<input type="file">`, JavaScript или HTML `accept` — только UX-помощь.

Все ограничения должны быть на backend:

- максимальный размер файла;
- максимальный размер multipart upload;
- максимальное число файлов в сутки;
- максимальный объем на пользователя;
- максимальный объем на IP;
- максимальный объем на весь сервис;
- ограничение частоты запросов;
- ограничение длительности видео;
- ограничение разрешения и битрейта;
- ограничение числа одновременных загрузок.

---

### 4.2 Upload ticket / upload reservation

Перед загрузкой backend должен выдать “разрешение на загрузку”.

Пример:

```json
POST /api/upload-ticket
{
  "type": "video",
  "estimatedSize": 104857600,
  "clientRequestId": "uuid"
}
```

Backend проверяет:

- аутентификация пользователя;
- роль/тариф;
- дневная квота пользователя;
- дневная квота IP;
- глобальная квота проекта;
- текущая загрузка очереди обработки;
- текущее использование storage budget;
- наличие CAPTCHA или challenge, если пользователь anonymous.

Если проверка пройдена, backend возвращает:

```json
{
  "uploadId": "uuid",
  "uploadUrl": "https://staging.example.com/...",
  "expiresIn": 900
}
```

Важно: backend должен **зарезервировать квоту заранее**, а не только после факта загрузки.

---

### 4.3 Hard quotas

Нужны несколько уровней квот.

#### Пример квот

| Уровень | Пример ограничения |
|---|---|
| Один файл | image ≤ 20 MB, video ≤ 300 MB |
| Один пользователь | 20 файлов/сутки |
| Один пользователь | 2 GB/сутки |
| Один IP | 5 файлов/час для anonymous |
| Один аккаунт | 10 одновременных загрузок |
| Весь проект | 100 GB/сутки upload |
| Весь проект | 1 TB storage active media |
| Весь проект | 100 одновременных video processing jobs |

Эти числа нужно подобрать под бизнес-модель. Но принцип один: **без hard quotas облачное хранилище может стать источником огромного счета**.

---

### 4.4 Rate limiting

Рекомендуется:

- rate limit по user ID;
- rate limit по IP;
- rate limit по session/device;
- exponential backoff;
- 429 Too Many Requests;
- CAPTCHA при превышении порога;
- temporary ban после повторяющихся нарушений.

Можно использовать Redis, Postgres, API Gateway, WAF или Yandex Cloud CDN/edge rules, если они доступны.

---

### 4.5 Direct upload в S3: только с ограничениями

Если браузер загружает файл напрямую в S3/Yandex Object Storage через presigned URL, это может быть удобно, но опасно.

Если используете presigned upload, обязательно ограничьте:

- срок действия URL, например 5–15 минут;
- максимальный размер объекта;
- prefix в bucket, например `staging/{tenant}/{uploadId}/`;
- allowed Content-Type;
- запрет на public write;
- запрет на arbitrary object key;
- запрет на multipart без контроля.

Для S3-совместимого API можно использовать presigned POST policy с ограничениями вроде:

```text
Content-Length-Range: min,max
expiration: short
key prefix: staging/...
success_action_status: 201
```

Но если Yandex Object Storage в вашем регионе/сценарии не поддерживает нужные ограничения, безопаснее загружать файл через backend.

---

### 4.6 Multipart upload

Multipart upload — важный источник DoS.

Нужно контролировать:

- максимальный размер part;
- максимальное число parts;
- максимальный общий размер upload;
- срок жизни upload ID;
- запрет на dangling multipart uploads;
- автоматическую очистку незавершенных multipart upload.

Иначе злоумышленник может создать много незавершенных multipart upload и увеличить стоимость/загрузку.

---

### 4.7 Global kill switch

Нужен механизм, который при превышении лимитов временно отключает загрузку.

Пример:

```text
if storage_used > 80% of budget:
  disable new uploads

if processing_queue > threshold:
  reject new uploads with 503

if daily_upload_bytes > global_limit:
  reject uploads
```

Это защитит от runaway-сценариев.

---

## 5. Безопасная валидация файлов

### 5.1 Не доверять расширению и MIME

Нельзя определять тип файла только по:

- имени файла;
- расширению;
- `Content-Type` из браузера;
- `file.name`.

Нужно проверять:

- magic bytes;
- структуру контейнера;
- метаданные через `ffprobe`, `libmagic`, `libvips`, `mediainfo`;
- размер, разрешение, длительность, битрейт;
- количество дорожек/стримов;
- наличие подозрительных полей.

---

### 5.2 Whitelist форматов

Для фото/видео лучше использовать узкий allowlist.

Например:

#### Фото

Разрешить:

- JPEG;
- PNG;
- WebP.

Осторожно:

- GIF — только с ограничениями по кадрам, размеру, длительности;
- HEIC/HEIF — только если есть надежный конвертер;
- SVG — не хранить как SVG, а конвертировать в raster или использовать строгий sanitizer.

#### Видео

Разрешить:

- MP4;
- MOV;
- WebM.

Но после загрузки лучше **перекодировать** в единый безопасный формат, например:

```text
MP4 + H.264 + AAC
```

или, если нужно:

```text
WebM + VP9 + Opus
```

---

### 5.3 Проверка magic bytes

Примеры сигнатур:

| Формат | Magic bytes |
|---|---|
| JPEG | `FF D8 FF` |
| PNG | `89 50 4E 47 0D 0A 1A 0A` |
| WebP | `RIFF....WEBP` |
| MP4/MOV | часто `ftyp` в начале файла |
| WebM | `EBM` или `1A45DFA3` для Matroska/WebM |

Но magic bytes — только первый шаг. Дальше нужна структурная проверка.

---

### 5.4 Проверка изображений

Для изображений ограничьте:

- максимальный размер файла;
- максимальное разрешение;
- максимальное количество пикселей;
- максимальное количество цветов;
- максимальное число кадров для GIF;
- максимальную длительность анимации;
- запрет на SVG с external entities, scripts, foreignObject и т.п.

Пример безопасных ограничений:

```text
max image file size: 20 MB
max pixels: 20,000,000
max width/height: 8192 px
max GIF frames: 100
max GIF duration: 30 sec
```

Важно: некоторые библиотеки обработки изображений могут быть уязвимы к malformed files. Используйте sandbox и минимально необходимые библиотеки.

---

### 5.5 Проверка видео

Перед перекодированием проверьте через `ffprobe` или аналог:

- длительность;
- разрешение;
- битрейт;
- количество видеодорожек;
- количество аудиодорожек;
- количество subtitle tracks;
- контейнер;
- кодек;
- наличие поврежденных структур.

Пример ограничений:

```text
max video file size: 300 MB
max duration: 180 seconds
max resolution: 1920x1080
max bitrate: 10 Mbps
max video streams: 1
max audio streams: 1
max subtitle streams: 1
```

Если файл не проходит проверки — не запускать ffmpeg.

---

### 5.6 Переупаковка / transcoding

Не храните пользовательский оригинал “как есть”, если он не нужен.

Для фото:

- перекодировать в JPEG/WebP;
- удалить EXIF/GPS;
- удалить комментарии/метаданные;
- ограничить разрешение;
- сжать.

Для видео:

- перекодировать в безопасный контейнер и кодек;
- удалить metadata;
- удалить subtitles, если они не нужны;
- ограничить разрешение;
- ограничить битрейт;
- ограничить длительность;
- сгенерировать превью/thumbnail.

Примерный безопасный ffmpeg-шаблон:

```bash
ffmpeg \
  -i input.mp4 \
  -map_metadata -1 \
  -map 0:v:0 \
  -map 0:a:0? \
  -vf "scale=1280:-2" \
  -c:v libx264 \
  -preset medium \
  -crf 28 \
  -maxrate 3M \
  -bufsize 6M \
  -c:a aac \
  -b:a 96k \
  -movflags +faststart \
  -f mp4 \
  output.mp4
```

Но важно:

- запускать ffmpeg в изолированном контейнере;
- с timeout;
- с ограничением CPU/memory;
- с ограничением file descriptors;
- с запретом network, если не нужно;
- с временными файлами в изолированной директории;
- с UUID вместо user filename;
- с проверкой `input` и `output` paths;
- с удалением временных файлов.

---

### 5.7 Защита от decompression/pixel bombs

Пример атаки: файл 200 KB, который при декодировании занимает 8 GB RAM.

Защита:

- лимит pixel dimensions до декодирования;
- лимит total pixels;
- лимит duration/bitrate для видео;
- лимит memory/CPU для worker;
- timeout;
- kill process при превышении лимита;
- не использовать библиотеки с уязвимыми parser’ами в небезопасном режиме.

---

### 5.8 AV-проверка

Даже для фото/видео желательно использовать антивирусную проверку.

Варианты:

- ClamAV;
- Yandex Cloud Security / VirusScan, если доступно в вашем сценарии;
- внешний AV-сервис;
- проверка hashes против известных bad hashes.

Но AV — не единственный контроль. Для медиа важнее structural validation и safe transcoding.

---

## 6. Безопасность хранения в Yandex Object Storage

### 6.1 Разделение bucket-ов

Пример:

```text
staging.example.ru
quarantine.example.ru
media.example.ru
archive.example.ru
```

Или один bucket с prefix’ами, но тогда IAM-политики должны строго ограничивать prefix.

---

### 6.2 Запретить public write

Категорически нельзя разрешать запись в bucket всем желающим.

Разрешить public-read можно только для уже обработанных медиа-объектов, но лучше через CDN и с правильными headers.

Плохо:

```text
bucket: public-read-write
```

Хорошо:

```text
staging: private
media: public-read only if needed, or private + signed URLs
```

---

### 6.3 IAM: least privilege

Backend и workers должны иметь только нужные права.

Примеры:

#### Web API role

Разрешения:

- `GetObject` для нужных prefix’ов;
- `PutObject` только в `staging/...`;
- `DeleteObject` только в `staging/...`;
- запрет `ListAllMyBuckets`;
- запрет `DeleteBucket`;
- запрет записи в `media/...` напрямую.

#### Processing worker role

Разрешения:

- `GetObject` из `staging/...`;
- `PutObject` в `media/...`;
- `DeleteObject` в `staging/...`;
- `PutObject` в `quarantine/...`;
- запрет удаления `media/...`, если не нужно.

---

### 6.4 Object naming

Никогда не используйте пользовательское имя файла как object key.

Плохо:

```text
uploads/%username%/my photo.jpg
```

Хорошо:

```text
media/{tenant}/{user_id}/{year}/{month}/{uuid}.jpg
staging/{tenant}/{uploadId}/original.bin
```

Object key должен быть server-generated.

---

### 6.5 Metadata объектов

В объектах можно хранить служебные metadata:

```text
x-amz-meta-status: processing|ready|quarantine|deleted
x-amz-meta-user-id: ...
x-amz-meta-upload-id: ...
x-amz-meta-hash: sha256...
x-amz-meta-created-at: ...
x-amz-meta-expires-at: ...
```

Это помогает lifecycle, cleanup и аудиту.

---

### 6.6 Lifecycle rules

Это один из главных механизмов защиты от роста стоимости.

#### `staging`

Правила:

- expire через 24–72 часа;
- удалить незавершенные multipart uploads;
- transition в cold storage не нужен, обычно лучше сразу удалить.

Пример:

```text
staging/*
  expiration: 24h
```

#### `quarantine`

Правила:

- expire через 7–30 дней;
- доступ только для security/moderation.

#### `media`

Правила зависят от бизнес-политики:

- active media может храниться 30/90/365 дней;
- старые превью можно удалять раньше;
- оригиналы можно удалять после обработки;
- cold/archive storage можно использовать, если требуется долгосрочное хранение.

Пример:

```text
media/thumbnails/*
  expiration: 30 days

media/videos/*
  transition to cold after 90 days
  expire after 365 days
```

Важно: lifecycle rules нужно тестировать и учитывать, что они не мгновенные.

---

### 6.7 Versioning

Versioning может быть полезен для important media, но он увеличивает стоимость и сложность cleanup.

Рекомендация:

- для `staging` versioning обычно не нужен;
- для `quarantine` обычно не нужен;
- для `media` versioning может быть включен только при необходимости;
- если versioning включен, обязательно настройте lifecycle для non-current versions и delete markers.

---

### 6.8 Server-side encryption

Проверьте актуальные возможности Yandex Object Storage в вашем регионе/тарифе.

Если доступно:

- включите server-side encryption;
- используйте KMS, если требуется;
- для чувствительных данных рассмотрите application-level encryption.

Но для public media encryption at rest обычно важнее, чем public write protection.

---

### 6.9 CORS

Если браузер напрямую обращается к S3 для upload, CORS нужен.

Но CORS не должен быть открыт на `*`.

Разрешайте только ваши origins:

```text
https://app.example.com
```

Запрещайте:

- arbitrary origins;
- public GET если не нужно;
- public PUT.

---

### 6.10 Отключить public bucket website hosting

Если bucket может обслуживать HTML/JS, это риск XSS/phishing.

Для фото/видео bucket website hosting лучше отключить.

---

### 6.11 Access logs

Включите access logging для bucket-ов, если доступно.

Логи должны попадать в:

- Cloud Logging;
- SIEM;
- отдельный private bucket;
- monitoring/alerting.

Метрики:

- GET/PUT/DELETE;
- 403/404/429;
- размер запросов;
- source IP;
- user agent;
- object prefix.

---

## 7. CDN и контроль трафика

### 7.1 Используйте CDN

Для публичных фото/видео CDN критически важен.

Он снижает:

- origin egress;
- load на backend;
- количество запросов к Object Storage;
- стоимость трафика.

### 7.2 Правильная схема доступа

Плохо:

```text
Browser → Object Storage directly
```

Хорошо:

```text
Browser → CDN → Object Storage
```

Если media bucket private:

```text
Browser → CDN → signed URL to Object Storage
```

### 7.3 Cache headers

Для immutable media используйте:

```text
Cache-Control: public, max-age=31536000, immutable
```

Object key должен содержать hash/version:

```text
/media/videos/2026/01/abc123def456.mp4
```

Тогда можно кэшировать агрессивно.

### 7.4 Контроль egress

Нужно мониторить:

- egress из Object Storage;
- egress из CDN;
- cache hit rate;
- количество GET-запросов;
- размер отдаваемых объектов.

Если CDN cache hit rate низкий, счет может расти быстро.

---

## 8. Anti-abuse и защита от ботов

### 8.1 Аутентификация

Если возможно, загрузка должна быть только для авторизованных пользователей.

Для anonymous-загрузки нужны более жесткие ограничения:

- CAPTCHA;
- proof-of-work;
- email verification;
- phone verification;
- device fingerprint;
- ограничение по IP;
- ограничение по session;
- временные upload quotas.

### 8.2 Репутация пользователей

Можно использовать:

- tier для новых аккаунтов;
- пониженные лимиты для новых пользователей;
- повышенные лимиты для verified users;
- shadow ban при подозрительной активности;
- hash-based blocking для повторяющихся вредоносных файлов.

### 8.3 Deduplication

Вычисляйте hash загруженного файла, например SHA-256.

Если файл уже есть:

- не хранить дубликат;
- не перекодировать повторно;
- переиспользовать готовый derivative.

Это снижает storage и processing cost.

Но нужно учитывать copyright/legal требования: если нужно хранить именно экземпляр пользователя, dedup может быть ограничен.

---

## 9. Защита от DoS на этапе обработки

### 9.1 Проблема

Даже если файл маленький, он может быть дорогим в обработке:

- длинное видео;
- высокий битрейт;
- 4K/8K;
- много дорожек;
- поврежденный контейнер;
- анимированный GIF с тысячами кадров.

### 9.2 Контроль processing

Нужно ограничивать:

- количество одновременных transcoding jobs;
- timeout обработки;
- CPU quota;
- memory quota;
- disk quota;
- максимальный размер входного файла;
- максимальный размер выходного файла;
- максимальную длительность;
- максимальный битрейт;
- максимальное разрешение.

### 9.3 Queue backpressure

Если очередь обработки перегружена, backend должен:

- возвращать 429/503;
- отказывать в новых upload ticket;
- временно снижать лимиты;
- масштабировать workers только до hard limit.

### 9.4 Serverless/containers

Для видео-обработки лучше использовать:

- Yandex Cloud Serverless Containers;
- VM/managed instance groups;
- очереди: Yandex Message Queue / Kafka / RabbitMQ;
- max instances;
- timeouts.

Не стоит запускать ffmpeg внутри основного web backend без изоляции и лимитов.

---

## 10. Контроль стоимости и “огромных счетов”

### 10.1 Yandex Cloud budgets и alerts

Нужно настроить:

- месячный budget;
- alerts на 50%, 80%, 100%;
- отдельный проект для media storage;
- отдельный проект для staging/processing;
- tagging объектов для аналитики.

Но alerts сами по себе не всегда автоматически останавливают сервис. Поэтому нужен application-level kill switch.

---

### 10.2 Storage quotas в приложении

S3/Yandex Object Storage может не иметь удобного hard quota “до 100 GB” для bucket. Поэтому квоты должны быть в приложении:

- перед загрузкой backend резервирует объем;
- после загрузки фиксирует фактический объем;
- при превышении — отклоняет новые загрузки;
- при превышении budget — включает read-only или disable upload mode.

---

### 10.3 Lifecycle как основной механизм экономии

Пример политики:

| Тип объекта | Срок хранения |
|---|---|
| staging original | 24 часа |
| failed upload | 24 часа |
| quarantine | 7–30 дней |
| thumbnail | 30–90 дней |
| processed photo | 90–365 дней |
| processed video | 90–365 дней |
| archive video | 1–3 года cold storage |
| deleted user media | 30 дней purge |

---

### 10.4 Не храните лишнее

Для комментария часто достаточно:

- thumbnail;
- preview 720p;
- optimized JPEG/WebP.

Не обязательно хранить:

- 4K видео;
- оригинал 100 MB;
- несколько копий одного файла.

---

### 10.5 Оценивайте стоимость

Упрощенная оценка:

```text
Storage cost =
  active media bytes
  + staging bytes
  + archive bytes
  + versioning overhead
  + object count cost

Processing cost =
  transcoding CPU
  AV scanning CPU
  queue operations

Traffic cost =
  Object Storage egress
  CDN egress
  CDN cache misses

Request cost =
  GET/PUT/DELETE
  List operations
  multipart operations
```

Нужно заранее смоделировать worst case:

```text
100 000 пользователей × 10 видео × 50 MB = 50 GB
```

Но если пользователи загружают 100 видео по 500 MB:

```text
100 000 × 100 × 500 MB = 5 TB
```

Без квот это может быть катастрофой.

---

## 11. Безопасность доступа к готовым медиа

### 11.1 Public media

Если фото/видео публичные:

- bucket public-read только для нужных prefix’ов;
- public write запрещен;
- CDN обязателен;
- object keys должны быть immutable;
- cache TTL длинный;
- no directory listing;
- no website hosting;
- correct Content-Type;
- `X-Content-Type-Options: nosniff`;
- `Content-Disposition` при необходимости;
- CSP на frontend.

### 11.2 Private media

Если доступ ограничен:

- bucket private;
- backend генерирует signed URL;
- TTL signed URL короткий, например 5–15 минут;
- CDN может использовать signed origin URL;
- нельзя хранить long-lived public links;
- нельзя выдавать access key браузеру.

---

## 12. Обработка ошибок и cleanup

Нужно предусмотреть:

- upload начался, но не завершился;
- worker упал после загрузки;
- файл загружен, но не обработан;
- файл обработан, но DB не обновилась;
- пользователь удалил комментарий, но медиа осталось;
- пользователь удалил аккаунт;
- модерация заблокировала контент.

### 12.1 Состояния медиа

В БД лучше хранить статус:

```text
pending_upload
uploaded
processing
processing_failed
ready
blocked
deleted
purged
```

Нельзя показывать пользователю файлы со статусом:

- `pending_upload`;
- `processing_failed`;
- `blocked`;
- `purged`.

### 12.2 Cleanup jobs

Регулярные задачи:

```text
1. Delete staging objects older than 24h.
2. Delete failed processing objects.
3. Delete orphaned objects not referenced in DB.
4. Delete media of deleted users/comments.
5. Clean multipart uploads.
6. Recalculate storage quota usage.
7. Send alerts if storage exceeds threshold.
```

---

## 13. Логирование и мониторинг

### 13.1 Что логировать

Для каждого upload:

- request ID;
- user ID;
- IP;
- user agent;
- upload ID;
- file hash;
- declared size;
- actual size;
- detected type;
- validation result;
- processing duration;
- processing status;
- final object key;
- error reason.

Не логируйте лишние персональные данные.

### 13.2 Метрики

Рекомендуемые метрики:

```text
uploads_total
uploads_rejected
uploads_per_user
uploads_per_ip
storage_bytes_used
object_count
processing_queue_depth
processing_failures
processing_time_p95
egress_bytes
cdn_cache_hit_ratio
429_responses
503_responses
storage_alerts
```

### 13.3 Alerts

Алерты:

- storage > 70% budget;
- daily upload > 150% average;
- processing queue > threshold;
- rejected uploads spike;
- AV detections spike;
- unusual object count growth;
- unusual egress growth;
- 403/403 abuse spike;
- many failed uploads from one IP.

---

## 14. Модерация и юридические аспекты

Если пользователи могут публиковать контент, нужно учитывать:

- незаконный контент;
- персональные данные;
- авторские права;
- retention policy;
- право на удаление;
- требования 152-ФЗ или иных применимых норм;
- порядок блокировки и удаления.

Рекомендуется:

- статус `pending` до модерации;
- показ только после модерации или после автоматической проверки;
- возможность удалить контент;
- хранение hash и audit trail;
- blacklist для известных bad files;
- жалоба/модерация.

---

## 15. Пример безопасного upload flow

### Шаг 1. Клиент хочет загрузить видео

```http
POST /api/media/upload-ticket
Authorization: Bearer ...
Content-Type: application/json

{
  "type": "video",
  "estimatedSize": 52428800,
  "clientRequestId": "uuid"
}
```

### Шаг 2. Backend проверяет

- user authenticated;
- user quota not exceeded;
- IP quota not exceeded;
- global quota not exceeded;
- storage budget ok;
- processing queue ok;
- file type allowed.

### Шаг 3. Backend резервирует квоту

```text
reserve_bytes(user_id, 52428800)
reserve_bytes(global, 52428800)
```

### Шаг 4. Backend выдает upload URL

```json
{
  "uploadId": "uuid",
  "uploadUrl": "https://staging.example.com/...",
  "expiresIn": 900
}
```

### Шаг 5. Клиент загружает файл

Backend или S3 event уведомляет backend, что upload завершен.

### Шаг 6. Backend валидирует файл

- magic bytes;
- ffprobe;
- max size;
- max duration;
- max resolution;
- AV scan;
- hash calculation.

### Шаг 7. Worker переупаковывает

- transcode video;
- strip metadata;
- generate thumbnail;
- generate preview.

### Шаг 8. Worker записывает результат в `media`

```text
media/{tenant}/{user_id}/2026/01/{uuid}.mp4
media/{tenant}/{user_id}/2026/01/{uuid}.jpg
```

### Шаг 9. Backend обновляет БД

```text
status = ready
object_key = ...
thumbnail_key = ...
hash = sha256...
```

### Шаг 10. Original удаляется из staging

```text
Delete staging/{tenant}/{uploadId}/original.*
```

---

## 16. Рекомендуемые ограничения для фото/видео

Ниже — пример разумных стартовых лимитов. Их нужно адаптировать под продукт.

### Фото

| Параметр | Рекомендуемый лимит |
|---|---:|
| Max input file | 20 MB |
| Max output file | 5 MB |
| Max pixels | 20,000,000 |
| Max width/height | 8192 px |
| Max GIF frames | 100 |
| Max GIF duration | 30 sec |
| Allowed formats | JPEG, PNG, WebP |
| Metadata | strip EXIF/GPS |
| User daily quota | 20 files |
| User daily bytes | 500 MB |
| IP hourly quota | 5 files |

### Видео

| Параметр | Рекомендуемый лимит |
|---|---:|
| Max input file | 300 MB |
| Max output file | 50 MB |
| Max duration | 180 sec |
| Max resolution | 1920×1080 |
| Max bitrate | 10 Mbps |
| Max audio bitrate | 128 kbps |
| Max video streams | 1 |
| Max audio streams | 1 |
| Max subtitle streams | 1 |
| Allowed input containers | MP4, MOV, WebM |
| Output format | MP4 H.264 + AAC |
| User daily quota | 5 videos |
| User daily bytes | 1 GB |
| IP hourly quota | 2 videos |
| Global daily upload | 100 GB |

Для комментария можно сделать еще жестче:

```text
comment image max 5 MB
comment video max 30 MB
comment video max 15 sec
```

---

## 17. Пример lifecycle policy

### staging bucket

```text
Prefix: staging/
Expiration: 24 hours
AbortIncompleteMultipartUpload: 24 hours
```

### quarantine bucket

```text
Prefix: quarantine/
Expiration: 14 days
```

### media bucket

```text
Prefix: media/thumbnails/
Expiration: 90 days

Prefix: media/photos/
Transition to cold: 90 days
Expiration: 365 days

Prefix: media/videos/
Transition to cold: 180 days
Expiration: 365 days
```

### archive bucket

```text
Prefix: archive/
Transition to cold: 30 days
Expiration: 3 years
```

---

## 18. Пример IAM-подхода

### Backend upload role

Разрешено:

```text
PutObject: staging/{tenant}/{uploadId}/*
GetObject: staging/{tenant}/{uploadId}/*
DeleteObject: staging/{tenant}/{uploadId}/*
```

Запрещено:

```text
PutObject: media/*
DeleteObject: media/*
ListBucket: all
DeleteBucket
PutBucketPolicy
```

### Processing worker role

Разрешено:

```text
GetObject: staging/*
PutObject: media/{tenant}/{user_id}/*
PutObject: quarantine/*
DeleteObject: staging/*
```

Запрещено:

```text
DeleteObject: media/*
PutObject: staging/*
PutBucketPolicy
DeleteBucket
```

---

## 19. Что точно не стоит делать

1. **Не разрешайте браузеру напрямую писать в public bucket.**
2. **Не используйте имя файла пользователя как object key.**
3. **Не доверяйте MIME/расширению.**
4. **Не храните оригиналы “навсегда” без lifecycle.**
5. **Не включайте public write.**
6. **Не давайте long-lived AWS/Yandex access keys фронтенду.**
7. **Не запускайте ffmpeg с root и без timeout.**
8. **Не разрешайте arbitrary file types.**
9. **Не включайте bucket website hosting для user uploads.**
10. **Не полагайтесь только на client-side limits.**
11. **Не считайте S3 “бесплатным” без мониторинга.**
12. **Не оставляйте незавершенные multipart uploads без cleanup.**
13. **Не храните EXIF/GPS без необходимости.**
14. **Не используйте один bucket для staging, quarantine и public media.**
15. **Не включайте versioning без lifecycle.**

---

## 20. Практический checklist

### Перед реализацией

- Определены допустимые форматы.
- Определены max file size.
- Определены max duration/resolution/bitrate.
- Определены квоты на пользователя/IP/global.
- Определена retention policy.
- Определены bucket-ы.
- Определены IAM roles.
- Определены lifecycle rules.
- Определен CDN.
- Определен budget/alerting.
- Определен moderation policy.

### Backend

- upload ticket;
- quota service;
- rate limiting;
- file validation;
- hash calculation;
- DB status tracking;
- upload reservation;
- cleanup jobs.

### Storage

- staging private;
- media public-read only if needed;
- no public write;
- no public listing;
- no website hosting;
- lifecycle rules;
- access logs;
- correct object keys;
- metadata tags.

### Processing

- isolated worker;
- timeout;
- CPU/memory limits;
- max concurrent jobs;
- safe ffmpeg/image tools;
- metadata stripping;
- AV scan;
- quarantine on failure.

### CDN

- cache headers;
- immutable URLs;
- origin protection;
- egress monitoring;
- cache hit ratio monitoring.

### Monitoring

- storage usage;
- object count;
- upload bytes;
- rejected uploads;
- processing queue;
- egress;
- budget alerts;
- abuse alerts.

---

## 21. Итоговая рекомендация

Для вашей задачи безопасная схема должна быть такой:

1. Пользователь получает upload ticket только после проверки квот и лимитов.
2. Файл загружается в private staging bucket.
3. Backend/worker проверяет файл: magic bytes, размер, разрешение, длительность, битрейт, AV.
4. Файл переупаковывается в безопасный формат, metadata удаляется.
5. Обработанный файл кладется в media bucket.
6. Оригиналы удаляются или имеют короткий TTL.
7. Доступ к медиа идет через CDN или signed URLs.
8. Все upload quota, storage quota, processing quota и budget alerts контролируются.
9. При превышении лимитов загрузка автоматически останавливается или ограничивается.

Ключевая защита от DOS и “огромных счетов” — это не только S3, а **backend quotas + lifecycle + processing limits + CDN + monitoring + budget alerts**.