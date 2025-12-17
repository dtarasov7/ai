Ниже добавлены (1) матрица трассируемости «требование → тест‑кейс → ожидаемый результат» для требований R‑001…R‑024 и (2) минимальные JSON‑шаблоны bucket policy, trust policy и permission policy, совместимые с целевым уровнем возможностей.[1][2][3][4][5][6]

## Матрица трассируемости

### Аутентификация и субъекты
| Требование | Тест‑кейс (S3/STS вызовы) | Ожидаемый результат |
|---|---|---|
| R-001 | **TC-001**: `aws s3api list-buckets` с корректными access/secret; затем повтор с неверным secret. [5] | 1) Успех с корректной подписью. 2) Отказ при неверной подписи. [5] |
| R-002 | **TC-002**: `aws s3api list-objects-v2 --bucket <B> --no-sign-request` при отсутствии публичных ACL/policy; затем разрешить чтение через ACL или bucket policy и повторить. [5][2] | 1) Отказ без разрешающих правил. 2) Успех только для разрешённых операций после настройки ACL/policy. [5][2] |
| R-003 (опц.) | **TC-003**: получить S3‑ключи у внешнего сервиса, затем `aws s3api head-bucket --bucket <B>`. [5] | Доступ определяется выданными правами, ключи работают как обычные S3‑ключи. [5] |

### ACL и bucket policy
| Требование | Тест‑кейс (S3/STS вызовы) | Ожидаемый результат |
|---|---|---|
| R-004 | **TC-004**: `put-bucket-acl`/`get-bucket-acl`, `put-object-acl`/`get-object-acl`; проверить доступ вторым пользователем на READ/WRITE/READ_ACP/WRITE_ACP. [5] | Права действуют согласно семантике ACL и разделению bucket/object. [5] |
| R-005 | **TC-005**: создать бакет/объект с `--acl <canned-acl>`; затем `get-*-acl` и проверить гранты. [5] | Canned ACL приводит к ожидаемому набору грантов. [5] |
| R-006 | **TC-006**: `put-bucket-policy`, `get-bucket-policy`, `delete-bucket-policy` на одном бакете. [2] | Политика ставится/читается/удаляется стандартными S3‑операциями. [2] |
| R-007 | **TC-007**: применить валидную policy с `Version/Statement/Effect/Principal/Action/Resource/Condition`; затем попытаться применить невалидную (битый JSON или без `Statement`). [2] | 1) Валидная policy принимается. 2) Невалидная отклоняется валидацией. [2] |
| R-008 | **TC-008**: (a) `aws:SecureTransport` — запретить `GetObject` при HTTP и разрешить при HTTPS; (b) `aws:SourceIp` — разрешить только из одной подсети; (c) `aws:username` — разрешить только одному пользователю; проверять фактическим доступом. [2] | Для каждого ключа условие реально влияет на решение авторизации. [2] |
| R-009 | **TC-009**: попытаться применить policy со string interpolation; затем проверить, что права не расширились и есть явная ошибка/неподдержка. [2] | Интерполяция не считается поддерживаемой и не должна давать «тихого» расширения прав. [2] |

### Роли и STS
| Требование | Тест‑кейс (S3/STS вызовы) | Ожидаемый результат |
|---|---|---|
| R-010 | **TC-010**: создать роль с trust policy, разрешающей AssumeRole только одному субъекту; попытаться AssumeRole “разрешённым” и “запрещённым”. [3][4] | “Запрещённый” не принимает роль; “разрешённый” принимает и получает временные креды. [3][4] |
| R-011 | **TC-011**: вызвать STS `AssumeRole`, экспортировать временные ключи и выполнить `aws s3api head-bucket`. [4] | Временные ключи работают до истечения срока и применяются для S3. [4] |
| R-012 | **TC-012**: получить OIDC web identity token и вызвать `AssumeRoleWithWebIdentity`; затем выполнить S3‑операцию с временными ключами. [4] | Временные ключи выдаются при валидном токене и подчиняются permission policy роли. [4] |
| R-013 | **TC-013**: запросить AssumeRole без DurationSeconds (проверить дефолт), затем с DurationSeconds больше max_session_duration роли (проверить ограничение). [3][4] | По умолчанию действует 3600; превышение ограничивается max_session_duration. [3][4] |
| R-014 | **TC-014**: роль разрешает `GetObject` и `PutObject`; при AssumeRole передать дополнительную Policy, оставляющую только `GetObject`; проверить чтение/запись. [4] | Дополнительная Policy только сужает права относительно permission policy роли. [4] |
| R-015 | **TC-015**: прогнать TC‑010…TC‑014 без session tags/ABAC и зафиксировать успешность. [1] | Все базовые сценарии ролей/STS проходят без требования session tags. [1] |

### Мультитенантность через placement и пулы
| Требование | Тест‑кейс (S3/STS вызовы) | Ожидаемый результат |
|---|---|---|
| R-016 | **TC-016**: создать два tenant; в каждом создать бакет с одинаковым именем (в рамках модели адресации tenant) и записать разные объекты; проверить `list-objects-v2`. [2][1] | Отсутствуют конфликты имён и пересечение данных между tenant. [2][1] |
| R-017 | **TC-017**: выполнить `aws s3api head-bucket --bucket <TENANT>:<BUCKET>` соответствующими ключами; затем ключами другого tenant. [2] | Доступ к `tenant:bucket` работает и подчиняется авторизации. [2] |
| R-018 | **TC-018**: создать бакет с placement A; попытаться изменить placement на B (через доступный интерфейс конфигурации поставщика). [6] | Изменение placement для существующего бакета невозможно/отклоняется. [6] |
| R-019 | **TC-019**: настроить placement A/B на разные пулы; создать бакеты/объекты/multipart в каждой placement; проверить административной диагностикой поставщика, что используются index/data/data-extra пулы. [6][1] | Фактическое размещение соответствует mapping’у пулов и обеспечивает изоляцию по пулам. [6][1] |
| R-020 | **TC-020**: пометить placement target tag=`tenant-a`; пользователю без `tenant-a` попытаться CreateBucket в этой placement (через LocationConstraint), затем пользователю с `tenant-a`. [6][1] | Без нужного placement_tag создание запрещено; с нужным — разрешено. [6][1] |
| R-021 | **TC-021**: `aws s3api create-bucket --create-bucket-configuration LocationConstraint=<region>:<placement-id>`; затем подтвердить привязку бакета к placement административно. [6][1] | Бакет создаётся в указанной placement; неверная/недоступная placement отклоняется. [6][1] |

### Администрирование и границы
| Требование | Тест‑кейс | Ожидаемый результат |
|---|---|---|
| R-022 | **TC-022**: через админ‑API/CLI выполнить жизненный цикл роли (create/get/list/delete, update trust policy, put/get/delete permission policy) и жизненный цикл placement (создать, сопоставить пулы, задать tags, выдать placement_tags). [3][6][1] | Управление выполняется без ручного вмешательства в внутренние данные; операции детерминированы и повторяемы. [3][6][1] |
| R-023 | **TC-023**: “data-user” с доступом к данным выполнить S3‑операции; затем попытаться админ‑операции управления ролями/placement. [1] | S3‑доступ работает; админ‑операции отклоняются без админ‑полномочий. [1] |
| R-024 | **TC-024**: в протокол приёмки включить только тесты TC‑001…TC‑023; не включать тесты «аккаунтной модели» (иерархии аккаунтов/самообслуживание аккаунтов). [1] | Соответствие RBAC подтверждается без требований функциональности вне целевого уровня. [1] |

## Минимальные JSON‑шаблоны политик

Ниже шаблоны соответствуют формату `Version: "2012-10-17"` и структуре `Statement/Effect/Principal/Action/Resource/Condition`, а также используют только перечисленные ключи условий и без string interpolation.[2][3]

### Bucket policy (пример: разрешить чтение объектов только по HTTPS и только одному пользователю)
Этот шаблон опирается на поддерживаемые условные ключи `aws:SecureTransport` и `aws:username`.[2]
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowGetObjectOnlyForUserOverTLS",
      "Effect": "Allow",
      "Principal": { "AWS": ["<USER_ARN>"] },
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::<BUCKET>/*"],
      "Condition": {
        "Bool": { "aws:SecureTransport": "true" },
        "StringEquals": { "aws:username": "<USERNAME>" }
      }
    }
  ]
}
```

### Bucket policy (пример: запретить доступ не по HTTPS для всех)
Этот шаблон демонстрирует использование Deny с `aws:SecureTransport`, чтобы запрет имел приоритет.[2]
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": ["s3:*"],
      "Resource": ["arn:aws:s3:::<BUCKET>", "arn:aws:s3:::<BUCKET>/*"],
      "Condition": {
        "Bool": { "aws:SecureTransport": "false" }
      }
    }
  ]
}
```

### Trust policy роли (assume role policy) — разрешить AssumeRole конкретному пользователю
Шаблон соответствует формату trust policy с `Action: sts:AssumeRole` и `Principal.AWS` как в примерах документации роли.[3]
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowAssumeRoleFromUser",
      "Effect": "Allow",
      "Principal": { "AWS": ["<USER_ARN>"] },
      "Action": ["sts:AssumeRole"]
    }
  ]
}
```

### Permission policy роли — минимальный доступ к одному бакету
Шаблон соответствует формату permission policy роли и допускает точечное перечисление действий S3 на ресурсах бакета/объектов.[3]
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowListBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": ["arn:aws:s3:::<BUCKET>"]
    },
    {
      "Sid": "AllowRWObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::<BUCKET>/*"]
    }
  ]
}
```

Нужен ли отдельный блок JSON для `AssumeRoleWithWebIdentity` (trust policy с условиями по claims), или в закупке достаточно зафиксировать сам факт поддержки операции и тест‑кейс TC‑012?

[1](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/154680809/30227eab-a7e2-4f17-b992-0e71358844ee/claude-1.md)
[2](https://docs.ceph.com/en/quincy/radosgw/bucketpolicy/)
[3](https://docs.ceph.com/en/quincy/radosgw/role/)
[4](https://docs.ceph.com/en/quincy/radosgw/STS/)
[5](https://docs.ceph.com/en/latest/radosgw/s3/authentication/)
[6](https://docs.ceph.com/en/latest/radosgw/placement/)
