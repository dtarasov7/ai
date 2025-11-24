Ниже — рабочая схема для air‑gapped сети с Notation и Nexus, когда вендоры привозят «тярболы» (tar). Ключевая идея: хранить и переносить не «docker save»-тар, а OCI Image Layout, где рядом с образом лежат и подписи Notation. Тогда вы переносите образ и подписи одной командой, проверяете локально политикой доверия и уже затем публикуете в Nexus.

Что попросить у поставщиков
- Формат поставки: один архив OCI Image Layout (каталог с oci-layout, index.json, blobs/*), упакованный в tar/zip.
  - Как подготовить у поставщика: oras cp -r REGISTRY/REPO:TAG --to-oci-layout ./bundle:TAG && tar -czf bundle.tgz ./bundle
  - Ключ — флаг -r: он кладёт вместе с образом все referrers, в т.ч. подписи Notation. 
- Подпись X.509 (Notation), а открытые корневые/выдающие сертификаты вы уже получили заранее — они пойдут в trust store.

Как проверять офлайн и импортировать в Nexus
Вариант A. Проверка до попадания в Nexus (через локальный «карманный» реестр):
1) Разворачиваем временный локальный реестр (изолированный от прод-сегмента), например registry:2 на 127.0.0.1:5000.
2) Переносим из архива OCI layout в локальный реестр, включая подписи:
   oras cp -r --from-oci-layout ./bundle.tar:TAG localhost:5000/vendor/image:TAG
   Если понадобится, можно указать режим совместимости referrers API/Tag Schema. 
3) Готовим trust store и политику Notation:
   - Добавляем сертификат(ы) вендора:
     notation cert add --type ca --store vendor-a /keys/vendor-a.pem
     (структура trust store: $XDG_CONFIG_HOME/notation/truststore/x509/ca/<store>/*.pem). 
   - Описываем политику доверия (trustpolicy.json/ trustpolicy.oci.json) — какие Subject/Issuers допускаются и на какие реестры/репозитории политика распространяется. Пример:
     {
       "version":"1.0",
       "trustPolicies":[
         {
           "name":"vendor-a",
           "registryScopes":["localhost:5000/*"],
           "signatureVerification":{"level":"strict"},
           "trustStores":["ca:vendor-a"],
           "trustedIdentities":["x509.subject: CN=Vendor A, O=Example Inc"]
         }
       ]
     }
     (Уровни проверки: strict/permissive/audit/skip.) 
4) Проверяем подпись:
   notation verify localhost:5000/vendor/image:TAG
   Начиная с v1.2 verify сам сначала пробует Referrers API и при необходимости откатывается к «referrers tag schema» — это важно для несовместимых реестров. 
5) При успехе копируем в «боевой» Nexus:
   oras cp -r localhost:5000/vendor/image:TAG nexus.internal/project/image:TAG
   При проблемах совместимости с referrers API у Nexus можно принудительно писать «tag schema»:
   oras cp -r --to-distribution-spec v1.1-referrers-tag localhost:5000/vendor/image:TAG nexus.internal/project/image:TAG. 

Вариант B. Проверка в Nexus на «карантинном» репозитории (минимум движений)
- Создайте в Nexus отдельный закрытый staging-репозиторий.
- Импортируйте туда пакет из OCI layout:
  oras cp -r --from-oci-layout ./bundle.tar:TAG nexus.internal/staging/vendor/image:TAG
- Запустите notation verify против staging-URL. Если всё ОК — «промоутите» (копия тегом/репо) в прод-репозиторий тем же oras cp -r. Благодаря fallback в Notation verify и в ORAS cp это будет работать и с реестрами без полноценного Referrers API. 

Если поставщик прислал «простой» docker save tar без подписей
- Попросите дополнительно «пакет подписей» в виде OCI layout (самый надёжный и простой для вас путь), либо сразу целиком bundle с образом и подписями, как описано выше.
- Альтернатива (более хлопотно): загрузить docker-archive в локальный реестр и отдельно импортировать артефакты подписи. Загрузить можно так:
  skopeo copy docker-archive:/path/image.tar docker://localhost:5000/vendor/image:TAG
  Но для подписи вам всё равно нужен артефакт подписи Notation, привязанный к digest манифеста; проще договориться про OCI layout bundle у поставщика. 

Как минимизировать ручные операции (шаблон «импортёра»)
- Триггер: появление *.tgz в входном каталоге (например, по inotify/cron).
- Шаги пайплайна:
  1) Распаковать во временный каталог или работать с tar напрямую (--from-oci-layout ./bundle.tar:TAG).
  2) oras cp -r в staging (локальный или Nexus).
  3) notation verify с вашей trust‑policy (strict). Логируем результат (JSON).
  4) При успехе oras cp -r в прод‑репозиторий; при ошибке — в «отклонено».
- Почему это надёжно: ORAS cp переносит и сам образ, и все referrers (подписи, SBOM и т. п.); Notation verify в v1.2+ автоматически совместим с реестрами без Referrers API, используя «referrers tag schema». 

Пара замечаний для air‑gapped
- CRL/ревокация и timestamping: в v1.3 добавили улучшения проверки CRL и timestamp chain; в «воздушной» зоне либо не проверяйте отзыв (permissive/audit), либо периодически офлайн‑обновляйте CRL/корни TSA, чтобы strict‑политика не «ложно» падала. 
- Дальше можно включить runtime‑валидацию в кластере (Ratify/Kyverno) — это второй рубеж, независимый от импортного пайплайна. 

Готов набросать небольшой bash‑скрипт «импортёра» под ваш путь/имена репозиториев Nexus. Скажите:
- вы готовы попросить у поставщиков именно OCI layout tar с подписями?
- у вашего Nexus включён/доступен staging‑репозиторий, или предпочитаете проверку в локальном временном реестре?
