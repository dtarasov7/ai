Ниже приведён набор требований к RBAC‑подсистеме S3‑совместимого объектного хранилища, соответствующий по возможностям уровню версии 17.2.7 (без включения более поздних функций).[1][2][3]

## Аутентификация и субъекты
- Система должна поддерживать аутентификацию S3‑запросов на основе AWS Signature, вычисляемой из пары access key / secret key.[4]
- Система должна обрабатывать неаутентифицированные запросы как запросы **анонимного** субъекта и применять к ним те же механизмы авторизации (ACL/policy), что и к аутентифицированным.[4]
- (Опционально, если требуется интеграция) Система должна поддерживать сценарий аутентификации S3 через внешний IAM/Keystone‑совместимый сервис с получением AWS‑style ключей (EC2 credentials) для доступа к S3 API.[5]

## ACL и bucket policy
- Система должна поддерживать S3‑совместимые ACL для бакетов и объектов, включая права READ, WRITE, READ_ACP, WRITE_ACP, FULL_CONTROL и их различную семантику для bucket vs object.[4]
- Система должна поддерживать canned ACL (предопределённые наборы ACL) и их применение при создании/изменении бакета и объекта.[4]
- Система должна поддерживать bucket policy (JSON‑политики для бакета) и операции управления ими стандартными S3‑вызовами PutBucketPolicy/GetBucketPolicy/DeleteBucketPolicy.[1]
- При интерпретации условий в bucket policy система должна поддерживать набор ключей условий: aws:CurrentTime, aws:EpochTime, aws:PrincipalType, aws:Referer, aws:SecureTransport, aws:SourceIp, aws:UserAgent, aws:username.[1]

## Роли и временный доступ (STS)
- Система должна поддерживать сущность «роль» с (1) trust policy (кто может принять роль) и (2) permission policy (что разрешено после принятия роли).[2]
- Система должна предоставлять STS‑совместимые операции AssumeRole и AssumeRoleWithWebIdentity с выдачей временных учётных данных (temporary credentials) для доступа к S3.[3]
- Система должна поддерживать ограничение длительности сессии через DurationSeconds, значение по умолчанию 3600 секунд и настраиваемый максимальный срок сессии на уровне роли.[2][3]

## Мультитенантность и placement/pool
- Система должна поддерживать мультитенантность через сущность tenant, обеспечивая возможность существования пользователей и бакетов с одинаковыми именами в разных tenant за счёт их логического разделения.[6]
- Система должна поддерживать неявный tenant «по умолчанию» (контекст tenant берётся из учётных данных вызывающего субъекта, если tenant явно не указан).[6]
- Система должна поддерживать доступ к бакетам другого tenant в S3 через синтаксис tenant:bucket (с разделителем “:”) при обращении в path‑style.[6]
- Система должна поддерживать механизм placement‑целей (placement targets), где выбранная для бакета placement‑цель фиксируется при создании бакета и далее не изменяется.[7]
- Каждая placement‑цель должна сопоставляться как минимум с раздельными пулами хранения для: (a) индексных данных бакета (index pool), (b) данных объектов (data pool по storage class), (c) служебных данных незавершённых multipart‑загрузок (data extra pool), чтобы обеспечить мультитенантность через изоляцию по пулам.[7]
- Система должна позволять ограничивать, какие placement‑цели доступны пользователю/tenant, через механизм меток placement‑цели (tags) и разрешённых меток у пользователя (placement_tags), запрещая создание бакетов в placement‑целях без совпадающих меток.[7]
- Система должна позволять явно указывать placement‑цель при создании бакета через S3 LocationConstraint в формате “<region_api_name>:<placement-id>”.[7]

## Администрирование RBAC
- Система должна предоставлять административные операции управления ролями (создание/удаление, получение/перечисление, управление trust policy и permission policy) через административный API и/или CLI.[2]
- Система должна обеспечивать разграничение прав на административные операции (управление ролями/политиками/placement‑параметрами) отдельно от прав доступа к данным через S3.[2][7]

Нужны ли требования в формате ЧТЗ с идентификаторами (RBAC‑001…), критериями приёмки и набором проверок (S3 API calls), чтобы их можно было сразу включить в закупочную документацию?

[1](https://docs.ceph.com/en/quincy/radosgw/bucketpolicy/)
[2](https://docs.ceph.com/en/quincy/radosgw/role/)
[3](https://docs.ceph.com/en/quincy/radosgw/STS/)
[4](https://downloads.fcio.net/ceph-jewel-doc/radosgw/s3/authentication.html)
[5](https://docs.ceph.com/en/latest/radosgw/s3/authentication/)
[6](https://docs.ceph.com/en/squid/radosgw/multitenancy/)
[7](https://docs.ceph.com/en/reef/radosgw/placement/)
[8](https://docs.ceph.com/en/latest/rados/operations/pools/)
[9](https://docs.ceph.com/en/latest/radosgw/placement/)
[10](https://cephdocs.readthedocs.io/en/stable/rados/operations/placement-groups/)
[11](https://ets.docs.euro-linux.com/ceph/nautilus/rados/operations/placement-groups.html)
[12](https://github.com/ceph/ceph/blob/main/doc/rados/operations/pools.rst)
[13](https://docs.ceph.com/en/mimic/radosgw/placement/)
[14](https://downloads.fcio.net/ceph-jewel-doc/radosgw/multisite.html)
[15](https://people.redhat.com/bhubbard/nature/default/rados/operations/placement-groups/)
[16](https://docs.mirantis.com/mosk/latest/ops/ceph-operations/ceph-calculate-target-ratio.html)
[17](https://github.com/ceph/ceph/blob/main/doc/radosgw/multisite.rst)
[18](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/3/html/storage_strategies_guide/pools-1)
[19](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/5/html/object_gateway_guide/administration)
[20](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/3/html/object_gateway_guide_for_red_hat_enterprise_linux/rgw-administration-rgw)
[21](https://ceph.io/en/news/blog/2014/placement_pools-on-rados-gw/)
[22](https://knowledgebase.45drives.com/kb/kb450422-configuring-ceph-object-storage-to-use-multiple-data-pools/)
[23](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/6/html/object_gateway_guide/administration)
[24](https://documentation.suse.com/ses/7.1/html/ses-all/ceph-pools.html)
[25](https://downloads.fcio.net/ceph-luminous-doc/rados/operations/pools/)
[26](https://www.ibm.com/docs/en/storage-ceph/7.1.0?topic=usage-zone-groups)
[27](https://docs.huihoo.com/ceph/v9.0.0/rados/operations/pools/index.html)
[28](https://docs.ceph.com/en/nautilus/radosgw/placement/)
[29](https://docs.ceph.com/en/quincy/radosgw/multisite/)
[30](https://docs.ceph.com/en/quincy/radosgw/admin/)
[31](https://docs.ceph.com/en/latest/releases/quincy)
[32](https://docs.ceph.com/en/reef/radosgw/multitenancy/)
[33](https://people.redhat.com/bhubbard/nature/default/radosgw/placement/)
[34](https://docs.ceph.com/en/reef/radosgw)
[35](https://abayard.com/ceph-keystone-multitenancy/)
[36](https://docs.ceph.com/en/latest/radosgw/admin/)
[37](https://forum.proxmox.com/threads/ceph-dashboard-rados-gw-management-problem.123104/)
[38](https://ceph.io/en/news/blog/2025/enhancing-ceph-multitenancy-with-iam-accounts/)
[39](https://docs.ceph.com/en/pacific/radosgw/admin/)
[40](https://github.com/rook/rook/discussions/10431)
[41](https://docs.ceph.com/en/mimic/radosgw/multitenancy/)
[42](https://docs.ceph.com/en/nautilus/radosgw/multisite/)
[43](https://ceph.io/en/news/blog/2022/v17-2-0-quincy-released/)
[44](https://downloads.fcio.net/ceph-luminous-doc/radosgw/multitenancy/)
[45](https://docs.ceph.com/en/latest/radosgw/cloud-transition/)
[46](https://docs.ceph.com/en/quincy/radosgw/sync-modules)
[47](https://downloads.fcio.net/ceph-jewel-doc/radosgw/multitenancy.html)
[48](https://qdrant.tech/documentation/guides/multitenancy/)
[49](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/4/html/object_gateway_configuration_and_administration_guide/rgw-administration-rgw)
[50](https://qwc-services.github.io/master/topics/MultiTenancy/)
[51](https://blog.csdn.net/u010317005/article/details/79275527)
[52](https://downloads.fcio.net/ceph-luminous-doc/radosgw/admin/)
[53](https://www.reddit.com/r/vectordatabase/comments/1csz7l8/multitenancy_for_vectordbs/)
[54](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/4/html/object_gateway_configuration_and_administration_guide/rgw-multisite-rgw)
[55](https://www.ibm.com/docs/en/storage-ceph/7.1.0?topic=gateway-user-management)
[56](https://www.pogolinux.com/blog/secure-multi-tenancy-architecture-object-storage/)
[57](https://abayard.com/ceph-rgw-multitenancy-s3-kolla-ansible/)
[58](https://docs.ceph.com/en/latest/man/8/radosgw/)
[59](https://docs.ceph.com/en/reef/rados/operations/placement-groups/)
[60](https://docs.ceph.com/en/quincy/radosgw/layout/)
[61](https://docs.ceph.com/en/reef/architecture)
[62](https://people.redhat.com/bhubbard/nature/default/rados/operations/pools/)
[63](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/4/html/configuration_guide/pools-placement-groups-and-crush-configuration)
[64](https://docs.ceph.com/en/quincy/dev/radosgw/)
[65](https://docs.scs.community/docs/iaas/guides/operations-guide/ceph/)
[66](https://docs.ceph.com/en/latest/radosgw/config-ref/)
[67](https://docs.ceph.com/en/reef/radosgw/s3/authentication/)
[68](https://github.com/ceph/ceph/blob/main/doc/radosgw/s3/authentication.rst)
[69](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/4/html/developer_guide/ceph-object-gateway-and-the-s3-api)
[70](https://knowledgebase.45drives.com/kb/kb0450256-creating-using-ceph-s3-buckets/)
[71](https://docs.huihoo.com/ceph/v9.0.0/radosgw/s3/authentication/index.html)
[72](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/6/html/developer_guide/ceph-object-gateway-and-the-s3-api)
[73](https://pypi.fcio.net/ceph-jewel-doc/radosgw/s3/bucketops.html)
[74](https://docs.redhat.com/es/documentation/red_hat_ceph_storage/3/epub/developer_guide/authentication-and-acls)
[75](https://documentation.suse.com/ses/7.1/html/ses-all/cha-ceph-gw.html)
[76](https://resinfo.org/IMG/pdf/gtceph-20240523-ceph-implementing-s3.pdf)
[77](https://github.com/ceph/ceph/blob/main/doc/radosgw/s3.rst)
[78](https://docs.ceph.com/en/latest/radosgw/s3/)
[79](https://ceph-users.ceph.narkive.com/GBEmG6oT/bucket-owner-vs-s3-acl)
[80](https://docs.huihoo.com/ceph/v9.0.0/radosgw/s3/index.html)
[81](https://docs.huihoo.com/ceph/v0.80.5/radosgw/s3/authentication/index.html)
[82](https://www.ibm.com/docs/en/storage-ceph/7.1.0?topic=api-s3-authentication)
[83](https://github.com/ceph/ceph/blob/main/doc/radosgw/s3/ruby.rst)
