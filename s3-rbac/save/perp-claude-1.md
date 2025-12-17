## Требования к функционалу подсистемы RBAC для объектного хранилища S3

Подсистема управления доступом на основе ролей (RBAC) должна обеспечивать гранулированный контроль доступа к ресурсам объектного хранилища, совместимость с AWS S3 API и поддержку мультитенантной архитектуры.[1][2]

### Аутентификация и базовые механизмы доступа

Система должна поддерживать аутентификацию пользователей через AWS Signature-совместимый механизм с использованием access key и secret key. Необходима поддержка как аутентифицированных, так и анонимных запросов. Должна быть реализована интеграция с внешними системами аутентификации через OpenStack Keystone с возможностью генерации EC2-совместимых ключей доступа.[1]

### Списки контроля доступа (ACL)

Система должна поддерживать S3-совместимые списки контроля доступа с разграничением прав для бакетов и объектов. Необходима реализация следующих уровней разрешений: READ (чтение списка объектов для бакетов, чтение содержимого для объектов), WRITE (запись и удаление объектов в бакете), READ_ACP (чтение ACL бакета или объекта), WRITE_ACP (изменение ACL бакета или объекта), FULL_CONTROL (полный контроль над бакетом или объектом). Должна быть обеспечена поддержка предустановленных (canned) ACL для упрощенного управления разрешениями.[1]

### Политики доступа

Система должна поддерживать bucket policies в формате AWS IAM Policy Language с версией схемы "2012-10-17". Политики должны управляться через стандартные S3 API операции (PutBucketPolicy, GetBucketPolicy, DeleteBucketPolicy). В структуре политик необходима поддержка элементов: Effect (Allow/Deny), Principal (ARN пользователей и аккаунтов), Action (список разрешенных S3 операций), Resource (ARN ресурсов - бакетов и объектов).[3]

### Мультитенантность

**Критически важно**: система должна обеспечивать строгую изоляцию ресурсов между тенантами с возможностью использования одинаковых имен бакетов и пользователей в разных тенантах. Необходима поддержка явного указания тенанта при создании и доступе к ресурсам через синтаксис `<tenant>:<bucket>` для S3 API. Должна быть реализована возможность создания пользователей с привязкой к конкретному теnanту через параметр `--tenant` или синтаксис `<tenant>$<user>`.[2]

**Разделение по пулам хранения**: система должна поддерживать механизм placement targets, позволяющий назначать различные пулы хранения для разных бакетов на этапе их создания. Placement target определяет, в каких физических пулах будут размещены данные бакета (data pool), индексы (index pool) и дополнительные метаданные (extra pool). После создания бакета его placement target не может быть изменен. Необходима поддержка множественных placement targets в рамках одной зоны и зонной группы.[4][5]

Должна быть реализована возможность настройки default placement target на уровне зонной группы. Система должна поддерживать storage classes в рамках placement targets для дифференциации типов хранения (например, STANDARD, GLACIER) с маппингом на различные пулы.[5][4]

### Управление квотами

Система должна поддерживать установку квот на уровне пользователей и бакетов. Квоты должны включать: максимальное количество объектов в бакете, максимальный размер хранилища для бакета, ограничения на количество объектов для пользователя. Необходим механизм включения, отключения и мониторинга использования квот через административный API.[6]

### Роли и принципалы

Система должна поддерживать концепцию IAM-подобных ролей для делегирования доступа. В ARN (Amazon Resource Name) принципалов должна быть поддержка идентификации пользователей, ролей и аккаунтов в формате `arn:aws:iam::<account>:user/<username>`. Необходима поддержка механизма Assume Role для временного получения прав доступа.[7][8][3]

[1](https://docs.ceph.com/en/latest/radosgw/s3/authentication/)
[2](https://docs.ceph.com/en/reef/radosgw/multitenancy/)
[3](https://docs.ceph.com/en/quincy/radosgw/bucketpolicy/)
[4](https://www.croit.io/blog/optimize-storage-allocation-with-ceph-s3)
[5](https://docs.ceph.com/en/latest/radosgw/placement/)
[6](https://docs.ceph.com/en/quincy/radosgw/admin/)
[7](https://community.ibm.com/community/user/storage/blogs/daniel-alexander-parkes/2024/03/09/ceph-object-iam-sts-abac)
[8](https://ceph.io/en/news/blog/2025/enhancing-ceph-multitenancy-with-iam-accounts/)
[9](https://ceph.io/en/news/blog/2023/v17-2-7-quincy-released/)
[10](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/7/html/developer_guide/ceph-object-gateway-and-the-s3-api)
[11](https://ceph.io/en/news/blog/2025/rgw-deep-dive-1/)
[12](https://data.guix.gnu.org/revision/c985075db3e6682d8a5a231c01c770aa5a147f72/package/ceph/17.2.7?locale=en_US.UTF-8)
[13](https://ceph.io/en/news/blog/2025/user-accounts-dashboard/)
[14](https://docs.ceph.com/en/latest/releases/quincy)
[15](https://ceph.io/en/news/blog/2024/v17-2-8-quincy-released/)
[16](https://stackoverflow.com/questions/65028407/group-based-access-to-s3-buckets)
[17](https://people.redhat.com/bhubbard/nature/default/radosgw/bucketpolicy/)
[18](https://github.com/rook/rook/issues/14441)
[19](https://docs.netapp.com/us-en/ontap/s3-config/create-modifyi-object-store-server-policy-task.html)
