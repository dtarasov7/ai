Да. Для такой функции я бы рассматривал защиту не как «безопасно настроить S3», а как отдельный **контур приема недоверенного пользовательского контента**. Главные риски здесь — не только утечка данных, но и **финансовый DoS**: заполнение Object Storage, миллионы мелких объектов, незавершенные multipart-загрузки, дорогое перекодирование видео и генерация большого исходящего трафика.

Ниже — схема, которую я бы рекомендовал для production.

## 1. Целевая архитектура

```text
                        ┌──────────────────┐
                        │   Web Browser    │
                        └────────┬─────────┘
                                 │
                    POST /media/upload-init
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │ Backend / API          │
                    │                        │
                    │ • Authentication       │
                    │ • User quota           │
                    │ • Rate limit           │
                    │ • Reserve bytes        │
                    │ • Generate object_id   │
                    └───────────┬────────────┘
                                │
                   short-lived signed POST
                   + max size + exact key
                                │
                                ▼
                ┌──────────────────────────────┐
                │ S3 quarantine bucket        │
                │ PRIVATE                     │
                │ max_size = HARD LIMIT       │
                └──────────────┬───────────────┘
                               │ object-created
                               ▼
                        Queue / Trigger
                               │
                               ▼
                ┌──────────────────────────────┐
                │ Media processor             │
                │ isolated / limited          │
                │                              │
                │ • validate real format      │
                │ • dimensions/duration       │
                │ • AV scan (optional)        │
                │ • decode                    │
                │ • re-encode                 │
                │ • strip metadata            │
                └───────┬─────────────┬────────┘
                        │ OK          │ Reject
                        ▼             ▼
              ┌────────────────┐    delete/
              │ published      │    quarantine
              │ PRIVATE        │
              └───────┬────────┘
                      │
                 CDN / controlled
                   download
                      │
                      ▼
                    User
```

Yandex Object Storage поддерживает прямую загрузку из браузера с подписанной POST policy, причем в policy можно задать `content-length-range`, срок действия, имя/префикс объекта и другие ограничения. Это как раз подходит для данного сценария. :chatgpt-content-reference{index="0"}

### Очень важное следствие

**Не делайте поток**

`Browser → Backend → S3`

для самих гигабайтов медиа, если в этом нет специальной необходимости. Backend будет зря принимать трафик и станет дополнительной точкой DoS.

Но и поток

`Browser → S3 с постоянными credentials`

категорически не нужен.

Правильнее:

`Browser → backend за разрешением → S3 по короткоживущему ограниченному upload policy`.

---

# 2. Основная защита от переполнения хранилища

Здесь должно быть несколько независимых барьеров.

| Уровень | Ограничение | Для чего |
|---|---|---|
| Файл | максимальный размер одного изображения/видео | Один upload не может съесть огромный объем |
| Upload session | один `object_id`, один пользователь, короткий TTL | Нельзя использовать разрешение произвольно |
| Пользователь | байт/час, байт/сутки, файлов/сутки | Скомпрометированный аккаунт не заполнит S3 |
| Аккаунт/tenant | общий объем хранения | Защита multi-tenant системы |
| Сервис | uploads/sec и processing/sec | Защита backend/encoder |
| Bucket | `max_size` | Последний hard stop |
| Billing | budgets + alerts + automation | Финансовый emergency stop |

Особенно полезна возможность Yandex Object Storage задать **максимальный размер бакета**. При достижении ограничения Object Storage не позволит добавить объект, если после загрузки размер бакета превысил бы заданное значение. В документации Yandex этот механизм прямо приводится как способ защиты сервиса, позволяющего пользователям загружать данные, от лишних расходов. :chatgpt-content-reference{index="1"}

Я бы считал `max_size` обязательным.

Например, если нормальный рабочий объем системы — около 2 TB, не оставлять бакет безлимитным, а поставить осмысленный аварийный предел — допустим 3–4 TB, в зависимости от бизнес-требований.

Это **последняя линия обороны**, а не основной механизм quota management.

---

# 3. Очень важный момент: резервировать объем ДО выдачи upload URL

Представим quota пользователя:

> не более 500 MB в сутки.

Наивная реализация:

1. проверить `used_today`;
2. если меньше 500 MB — выдать ссылку;
3. после загрузки увеличить счетчик.

Это обходится параллельными запросами:

```text
100 одновременных запросов
        ↓
каждый видит used_today = 0
        ↓
100 разрешений × 200 MB
        ↓
20 GB вместо 500 MB
```

Нужно делать атомарное резервирование:

```text
BEGIN TRANSACTION

quota.used       = 200 MB
quota.reserved   = 100 MB

пользователь просит еще 50 MB

проверяем:
used + reserved + requested <= daily_limit

если OK:
    reserved += 50 MB
    создаем upload_session

COMMIT
```

После успешной загрузки:

```text
reserved -= actual_size
used     += actual_size
```

Если upload не произошел, reservation освобождается по TTL.

Например:

```text
upload_session:
    id
    user_id
    object_key
    max_bytes
    created_at
    expires_at
    status:
        ISSUED
        UPLOADED
        PROCESSING
        READY
        REJECTED
        EXPIRED
```

Это одна из наиболее важных защит от cost-exhaustion attack.

---

# 4. Я бы использовал именно signed POST policy

Например backend принимает:

```http
POST /api/media/uploads
Authorization: ...
```

с параметрами:

```json
{
  "kind": "image",
  "declared_size": 7348291,
  "content_type": "image/jpeg"
}
```

Backend проверяет quota и возвращает **не credentials**, а одноразовое разрешение примерно такого смысла:

```text
bucket = media-quarantine
key = incoming/8f/8f6c...random_uuid...
expires = now + 5 min
size = 1 ... 20 MB
```

Yandex поддерживает `content-length-range` непосредственно в policy. Например официальный пример ограничивает объект пятью мегабайтами. :chatgpt-content-reference{index="2"}

Это значительно лучше, чем просто сказать JavaScript-клиенту: «не загружай больше 20 MB». Клиент контролируется атакующим.

### Срок действия

Я бы выдавал upload authorization примерно на **5–15 минут**, а не на часы/дни.

Кроме прочего это уменьшает окно атаки после включения emergency kill switch.

---

# 5. Не доверять Content-Type и расширению

Вот это:

```text
picture.jpg
Content-Type: image/jpeg
```

ничего не доказывает.

После загрузки processing service должен определить реальный формат файла по содержимому и попытаться его корректно декодировать.

Например:

| Проверка | Изображение | Видео |
|---|---:|---:|
| Максимальный размер файла | ✓ | ✓ |
| Magic bytes / контейнер | ✓ | ✓ |
| Реальный codec |  | ✓ |
| Width × height | ✓ | ✓ |
| Число пикселей | ✓ | |
| Duration | | ✓ |
| Количество streams | | ✓ |
| FPS | | ✓ |
| Bitrate | | ✓ |
| Успешное полное декодирование | ✓ | ✓ |
| Повторное кодирование | ✓ | ✓ |

---

# 6. Защита именно media processor

Это второй крупный DoS-вектор.

Например файл может весить всего несколько мегабайт, но при декодировании оказаться изображением:

```text
300000 × 300000 pixels
```

или специально сконструированным видео, которое заставит decoder расходовать огромное количество CPU/RAM.

Поэтому ограничение:

```text
file_size <= 20 MB
```

недостаточно.

Нужны одновременно ограничения на:

```text
compressed bytes
pixel count
width / height
video duration
frame count / fps
number of streams
codec
processing time
CPU
RAM
temporary disk space
output size
```

Сам обработчик FFmpeg/ImageMagick/libvips и т. п. я бы запускал в **изолированном контейнере без доверия к входным данным**.

У него должны быть CPU/RAM/time/disk limits и желательно отсутствовать произвольный outbound-доступ в интернет. Даже если обнаружится уязвимость в декодере, результат не должен превращаться в компрометацию основной сети предприятия.

---

# 7. Оригинал и опубликованный файл — разные объекты

Не рекомендую после проверки просто менять флаг:

```text
original.jpg → approved
```

Лучше:

```text
incoming/a812...
       ↓ decoder
       ↓ re-encode
published/e741....webp
```

То есть опубликованный файл создается **заново из декодированного изображения/видео**.

Для картинок это, например:

```text
JPEG/PNG/WebP
        ↓
decode
        ↓
новое raster image
        ↓
encode JPEG/WebP
```

Это одновременно решает несколько проблем:

- удаляет неизвестные chunks;
- уничтожает большую часть polyglot-содержимого;
- удаляет EXIF;
- удаляет GPS;
- нормализует формат;
- позволяет ограничить размеры;
- уменьшает объем хранения.

Оригинал после успешной обработки обычно имеет смысл удалить, если нет бизнес-требования его хранить.

---

# 8. SVG я бы не принимал как обычную «картинку»

SVG — фактически XML/активный web content, а не просто bitmap.

Если приложение не нуждается именно в SVG, проще разрешить:

```text
JPEG
PNG
WebP
```

а SVG запретить.

Если SVG нужен — отдельная sanitization policy и отдельная обработка.

Аналогично лучше иметь **allowlist форматов**, а не blacklist.

---

# 9. Quarantine bucket должен быть private

Для него:

```text
anonymous READ  — deny
anonymous WRITE — deny
LIST            — deny
public ACL       — deny
```

Пользователь получает право только на загрузку конкретного заранее сформированного object key.

Yandex Object Storage имеет IAM, bucket policies, ACL, временные credentials и pre-signed URLs для разграничения доступа. :chatgpt-content-reference{index="3"}

CORS тоже стоит ограничить только вашими web origins, например:

```text
https://app.company.ru
https://www.company.ru
```

Но важно понимать:

> **CORS не является защитой от злоумышленника.**

Он ограничивает поведение браузеров. `curl`, бот или собственный HTTP-клиент атакующего CORS не остановит.

Yandex Object Storage поддерживает отдельную CORS-конфигурацию бакета. :chatgpt-content-reference{index="4"}

---

# 10. Отдельные service accounts

Я бы разделил полномочия минимум на:

```text
upload-signer
media-processor
delivery
administration
```

Например processor:

```text
quarantine:
    GET
    DELETE

published:
    PUT

но:
    никаких прав изменения bucket policy
    никаких прав создания бакетов
```

Backend вообще не должен иметь `storage.admin`, если это не требуется.

И никогда:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
```

в JavaScript frontend.

---

# 11. Multipart — потенциальная ловушка для денег

Для комментариев я бы вообще постарался **не использовать multipart upload**, если допустимые видео укладываются в ваши лимиты.

Причина: части незавершенной multipart upload остаются в бакете и тарифицируются. Yandex отдельно предупреждает об этом. :chatgpt-content-reference{index="5"}

Если multipart все же нужен, обязательно lifecycle:

```text
AbortIncompleteMultipartUpload
DaysAfterInitiation = 1
```

Yandex Object Storage позволяет автоматически удалять такие загрузки; минимальное значение для правила — один день. :chatgpt-content-reference{index="6"}

Это особенно важно против атаки:

```text
InitiateMultipartUpload
PUT part
PUT part
PUT part
...
никогда Complete
```

---

# 12. Lifecycle для quarantine

Для `quarantine` я бы установил жесткий TTL независимо от логики приложения.

Например:

```text
incoming/*
    delete after 1 day

failed/*
    delete after 3–7 days

incomplete multipart
    abort after 1 day
```

Тогда даже ошибка в вашей БД или processor не превращает бакет в вечную свалку.

Yandex Object Storage поддерживает lifecycle как для удаления объектов, так и для удаления незавершенных multipart-загрузок. :chatgpt-content-reference{index="7"}

---

# 13. DOS через количество файлов

Часто считают только гигабайты:

```text
User quota = 1 GB
```

Но атакующий может создать, например:

```text
1 000 000 объектов по 1 KB
```

Поэтому quota должна учитывать одновременно:

```text
bytes
objects
upload requests
processing jobs
```

Например концептуально:

```text
max_uploads_per_minute
max_uploads_per_hour
max_objects_per_day
max_bytes_per_day
max_active_upload_sessions
max_processing_jobs
max_stored_bytes
```

Это должны быть независимые лимиты.

---

# 14. DOS через перекодирование

Это даже опаснее S3.

Предположим видео:

```text
вход: 150 MB
транскодирование: 90 секунд CPU
```

Атакующий может создать тысячи допустимых загрузок и превратить ваш media cluster в майнер счетов.

Поэтому очередь обработки должна иметь свой budget:

```text
User A:
  ≤ N pending jobs
  ≤ X processing-seconds/day

Global:
  ≤ N simultaneous encoders
  ≤ Q jobs/minute
```

И должна существовать backpressure:

```text
queue > threshold
       ↓
backend временно перестает выдавать
новые upload authorizations
```

То есть система должна **деградировать отказом в новых загрузках**, а не бесконечным autoscaling.

Это принципиально важно для финансовой безопасности.

---

# 15. Не давать autoscaling бесконечно лечить DDoS

Это типичная ошибка облачных систем:

```text
атака
 ↓
нагрузка растет
 ↓
autoscaling
 ↓
еще VM
 ↓
еще processing
 ↓
огромный счет
```

С точки зрения availability система вроде бы защищена.

С точки зрения бюджета — атакующий победил.

Поэтому для media workers нужен:

```text
max instances = N
```

и ограниченный concurrency.

После этого очередь может расти, но расходы имеют верхнюю границу.

---

# 16. Защита API, который выдает разрешения на upload

Endpoint вроде:

```text
POST /media/upload-init
POST /media/upload-complete
```

нужно защищать сильнее обычного API.

Минимум:

```text
authenticated user
per-user rate limiting
per-IP limiting
global limiting
new-account limits
bot/risk controls
```

Yandex Smart Web Security поддерживает L7-защиту, WAF, SmartCaptcha и Advanced Rate Limiter. ARL позволяет ограничивать количество HTTP-запросов за период и группировать их по различным параметрам. :chatgpt-content-reference{index="8"}

Но здесь есть существенная деталь:

**Smart Web Security защищает ваш API, но после выдачи signed POST фактический upload идет напрямую в Object Storage.**

Поэтому WAF не заменяет:

```text
signed policy
+ content-length-range
+ user quota
+ bucket max_size
```

---

# 17. Новым и подозрительным пользователям — меньшие квоты

Полезная модель:

| Категория | Фото | Видео | Суточный объем |
|---|---:|---:|---:|
| Anonymous | запрет | запрет | 0 |
| Новый аккаунт | небольшой лимит | ограниченно/нет | низкий |
| Обычный пользователь | штатный | штатный | средний |
| Trusted/employee/etc. | выше | выше | выше |

Особенно важно не рассчитывать только на IP.

Атакующий может иметь тысячи IP, но стоимость создания большого количества качественных аккаунтов можно дополнительно увеличить CAPTCHA/anti-bot механизмом.

---

# 18. Защита от download/cost amplification

Есть обратный DOS:

```text
пользователь загрузил файл один раз
        ↓
бот скачал его 10 миллионов раз
        ↓
огромный исходящий трафик
```

То есть защищать нужно не только upload.

Я бы не делал основной S3 bucket напрямую публичным.

Для публичных медиа разумно рассмотреть:

```text
Client
  ↓
CDN
  ↓
published bucket
```

Yandex Cloud CDN умеет использовать Object Storage как source и кешировать файлы, уменьшая обращения к origin. :chatgpt-content-reference{index="9"}

Если контент доступен не всем, Cloud CDN поддерживает access по короткоживущим защищенным токенам/подписанным ссылкам. :chatgpt-content-reference{index="10"}

И отдельно надо мониторить:

```text
BytesDownloaded
GET requests
CDN traffic
```

---

# 19. Billing budget — полезен, но это НЕ hard limit

Это очень важная особенность Yandex Cloud.

Budget позволяет посылать уведомления при достижении заданных расходов, **но достижение budget threshold само по себе не прекращает потребление ресурсов**. :chatgpt-content-reference{index="11"}

Поэтому конструкция:

```text
Budget = 100 000 ₽
```

не означает:

```text
счет никогда не станет >100 000 ₽
```

Я бы сделал несколько уровней:

```text
50% → notification

70% → security/operations alert

85% → automatically restrict uploads

95% → emergency mode:
       stop issuing upload authorizations
       reduce processing concurrency

100% → hard kill-switch according to company policy
```

Yandex позволяет привязать к budget threshold триггер, вызывающий Cloud Functions/Serverless Containers, то есть часть реакции можно автоматизировать. :chatgpt-content-reference{index="12"}

При этом настоящий hard stop на объем данных обеспечивает именно `max_size` бакета, а не Billing Budget.

---

# 20. Мониторинг именно для обнаружения атаки

Yandex Object Storage отдает в Monitoring, в частности:

```text
space_usage
object_count
rps
traffic / BytesUploaded
traffic / BytesDownloaded
max_size
```

причем multipart-объекты и их части тоже можно видеть отдельно. :chatgpt-content-reference{index="13"}

Я бы построил alarms примерно на:

| Сигнал | Возможная проблема |
|---|---|
| резкий рост `PutRequests` | upload flood |
| резкий рост object count | small-object attack |
| `space_usage` растет аномально | storage exhaustion |
| много multipart Parts | incomplete upload abuse |
| высокий `BytesDownloaded` | egress attack / hotlink |
| много rejected media | malicious uploader |
| media queue растет | processing DoS |
| transcoding CPU резко вырос | crafted media / attack |
| много upload-session creation | abuse backend |
| много истекших upload sessions | bot/script attack |

Не следует принимать решения по quota непосредственно по `space_usage`: статистика Object Storage может обновляться с задержкой в несколько минут. Поэтому пользовательские quotas лучше вести транзакционно в вашей БД через механизм reservation. :chatgpt-content-reference{index="14"}

---

# 21. Audit

Изменение:

```text
bucket ACL
bucket policy
encryption
lifecycle
public access
```

само по себе является security-sensitive событием.

Yandex Audit Trails поддерживает события Object Storage как control plane, так и data plane; среди событий есть, например, изменения ACL, CORS, encryption, versioning и lifecycle бакета. :chatgpt-content-reference{index="15"}

На такие события имеет смысл настроить alert:

> «Published bucket стал public»  
> «Изменена lifecycle policy»  
> «Убран max-size»  
> «Изменились IAM permissions».

---

# 22. Шифрование

Для обоих бакетов:

```text
HTTPS in transit
+
server-side encryption
```

Для корпоративной системы имеет смысл использовать KMS-managed encryption и отдельные права на KMS key. Yandex Object Storage поддерживает шифрование объектов ключом Yandex KMS по умолчанию для бакета. :chatgpt-content-reference{index="16"}

Но шифрование не решает проблему пользовательского malicious content — это отдельный слой.

---

# 23. EXIF и приватность

При перепаковке фотографий я бы по умолчанию удалял:

```text
GPS coordinates
camera serial
author
software
timestamps, если не нужны
EXIF thumbnails
прочие metadata
```

То есть пользователь загружает фотографию с телефона, но посетители сайта получают уже нормализованный файл без геолокации.

Это одновременно security/privacy measure.

---

# 24. Практический первоначальный baseline

Для приложения с сообщениями/комментариями я бы на первом этапе поставил примерно такие **не универсальные, а стартовые** ограничения:

| Параметр | Пример |
|---|---:|
| Фото | ≤ 20 MB |
| Фото, количество пикселей | ≤ 40–50 MP |
| Видео | ≤ 100–250 MB |
| Длительность видео | ≤ 2–5 минут |
| Вложения в сообщение | ≤ 5–10 |
| Active uploads/user | ≤ 2–3 |
| Upload URL lifetime | 5–10 мин |
| Quarantine retention | ≤ 24 часа |
| Incomplete multipart | abort через 1 день |
| Processing timeout | несколько минут, жестко |
| Processor autoscale | имеет верхний предел |
| Bucket size | обязательный hard cap |

Конкретные цифры уже стоит вывести из требований продукта.

---

# 25. Что я считаю обязательным минимумом перед запуском

1. **Два бакета:** `quarantine` и `published`; оба private.
2. Browser получает только короткоживущий signed POST, причем с `content-length-range` и заранее определенным random object key.
3. Quota хранится на уровне приложения: bytes + objects + request rate + processing rate; объем резервируется **до** выдачи ссылки.
4. На quarantine/published устанавливается осмысленный `max_size`.
5. Включается lifecycle удаления старого quarantine и незавершенных multipart.
6. Медиа проходит decode → validation → полное re-encode; original напрямую никогда не публикуется.
7. Media processor изолируется и получает CPU/RAM/disk/time/concurrency limits.
8. API выдачи signed URL защищается authentication + per-user/IP/global rate limits; при необходимости SWS/ARL/CAPTCHA.
9. Вводятся Billing budgets с несколькими thresholds и автоматическим emergency kill switch; отдельно помнить, что сам budget расходы не останавливает. :chatgpt-content-reference{index="17"}
10. Настраиваются Monitoring/Audit Trails и alarms на storage, object count, PUT/GET, ingress/egress, multipart, media queue и изменение security settings. Object Storage автоматически поставляет метрики бакетов в Monitoring. :chatgpt-content-reference{index="18"}

**Самые важные три защиты именно от сценария «атакующий выставил нам огромный счет» — это:** приложение резервирует quota перед выдачей upload permission; S3 POST технически ограничивает размер каждого файла; у самого бакета есть жесткий `max_size`. Поверх этого processor имеет ограниченный autoscaling, а Billing threshold автоматически способен отключить выдачу новых upload permissions.

Если проектировать именно так, даже при компрометации пользовательского аккаунта или массированной регистрации ботов ущерб становится **ограниченным заранее заданными пределами**, а не зависит от того, как быстро дежурный заметит график расходов.