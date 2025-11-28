Ниже — практичная, “боековая” стратегия PKI для Kubernetes в изолированном корпа окружении: как организовать корневые/промежуточные центры, какие сертификаты нужны кластеру, как их выпускать и как безопасно ротировать без даунтайма.

Цели и принципы
- Надежное доверие: отдельные корни/промежуточные, разделение CA по доменам (etcd, API, front‑proxy, сервис‑аккаунты).
- Автоматизация и короткоживущие сертификаты, чтобы не полагаться на отзыв.
- Безопасная ротация “без рубильника”: двухфазные обновления с trust‑bundle (старый+новый CA).
- Полная автономность: все выпускается/проверяется внутри периметра, образы/зависимости — из локальных репозиториев.

1) Архитектура PKI
- Офлайн Root CA (HSM/офлайн-хранилище), срок 10–15 лет.
- Онлайн Intermediate CA(ы) внутри периметра (3–5 лет), подписанные офлайн‑рутом.
- На каждый кластер — отдельный набор:
  - kubernetes-ca: подпись серверных/клиентских cert для kube-apiserver, kube-controller-manager, scheduler, админ‑клиентов (если нужны).
  - front-proxy-ca: для aggregation layer (front‑proxy‑client).
  - etcd-ca: для server/peer/client cert etcd.
  - service-account signing key(s): ключ(и) подписи токенов сервис‑аккаунтов (это не CA).
- Для приложений:
  - Внутрикластерные mTLS: либо выделенный “apps-ca” (через cert-manager/Vault/step-ca), либо SPIFFE/SPIRE.
  - Внешние/пользовательские точки (Ingress): сертификаты от корпоративного Intermediate CA (чтобы доверялись рабочим станциям).

Решите вопрос траста клиентов:
- Если разработчики/CI обращаются к API извне — подпишите kubernetes-ca корпоративным Intermediate, либо распространите kubernetes-ca во внутренние доверенные хранилища (GPO/Ansible/SCCM/образ ОС).
- Для людей лучше OIDC (корп SSO) вместо клиентских X.509; для роботов — краткоживущие клиентские cert или OIDC/Workload Identity.

2) Криптопрофили и сроки
- Алгоритмы: ECDSA P‑256 (предпочтительно) или RSA 3072. Ключи только на узлах, права 600.
- Сроки:
  - Root: 10–15y; Intermediate: 3–5y.
  - Cluster CAs (kubernetes-ca, front-proxy-ca, etcd-ca): 1–2y.
  - Листовые cert control-plane/etcd: 90–180d.
  - Kubelet client/server: 30–90d.
  - Service-account signing keys: 1–2y, с планом ротации по схеме “двойной ключ”.
- В kube-controller-manager установите:
  - --cluster-signing-cert-file/--cluster-signing-key-file на ваш kubernetes-ca.
  - --cluster-signing-duration=90d (или ваша политика) — срок для автоматической выдачи листовых cert через CSR API.
- Полагайтесь на короткие сроки вместо CRL/OCSP: Go‑TLS в компонентах K8s обычно не проверяет OCSP/CRL, а в изоляции OCSP затруднен.

3) Какие сертификаты нужны Kubernetes
- kube-apiserver (серверный): SAN должен включать:
  - kubernetes, kubernetes.default, kubernetes.default.svc, kubernetes.default.svc.<cluster-domain>
  - ClusterIP сервиса API (обычно 10.96.0.1), все VIP/адреса/имена балансировщика, FQDN master‑узлов.
- kube-apiserver-kubelet-client (mTLS к kubelet).
- kube-controller-manager, kube-scheduler (клиентские).
- front-proxy-client (от front-proxy-ca).
- etcd: server/peer/client на каждый узел, SAN = IP+FQDN ноды.
- kubelet: client/server сертификаты для каждой ноды (через CSR API).
- Админ‑клиенты, если используете mTLS для людей/CI (лучше OIDC).

4) Создание и первичная выдача
Вариант A (рекомендуется): внешний CA + kubeadm
- Снаружи (офлайн/защищенная CA) генерируете:
  - ca.crt/key (kubernetes-ca), front-proxy-ca.crt/key, etcd/ca.crt/key, sa.pub/sa.key.
- Копируете в /etc/kubernetes/pki/ на control-plane (минимальные права).
- kubeadm init --external-ca (или через ClusterConfiguration с external CA).
- Bootstrap kubelet через TLS Bootstrapping (bootstrap token); kubelet получит клиентский cert от kubernetes-ca автоматически.

Вариант B: cert-manager/Vault/step-ca для рабочих нагрузок
- Поднимите внутренний issuer (ClusterIssuer) и используйте Certificate объекты для сервисов/вебхуков/aggregated API.
- Задайте renewBefore ~30% срока.

5) Автоматическая ротация (листовых cert)
- kubelet: включите --rotate-certificates; контроллеры одобрения CSR включены в kube-controller-manager. Сроки определяются --cluster-signing-duration.
- Контрол-плейн (kubeadm): поставьте таймер/cron на каждом control-plane:
  - kubeadm certs check-expiration
  - kubeadm certs renew all
  - systemctl restart kubelet (перезапустит статические Pod’ы — API/CM/Sched/etcd по одному узлу)
- etcd: ротируйте по одному члену кворума:
  1) Разместите новый trust-bundle (oldCA+newCA) в --trusted-ca-file/--peer-trusted-ca-file.
  2) Выпустите новые server/peer cert, перезапустите 1 ноду, убедитесь в здоровье, переходите к следующей.
  3) После обновления всех — удалите старый CA из trust-bundle.
- Front-proxy: обновите front-proxy-client, затем компоненты, которые его используют.

Практический порядок для HA-кластера (без смены CA):
1) Подготовка: выпуск новых листовых cert с тем же CA.
2) Control-plane нода 1: обновить файлы, перезапустить kubelet, проверить готовность API/etcd.
3) Нода 2, затем 3 — по очереди.
4) Проверить kubelet rotation на воркерах (CSR одобряются автоматически).
5) Вебхуки/aggregated API/Ingress — через cert-manager/ваш issuer.

6) Двухфазная ротация CA (минимум даунтайма)
Применяйте, если меняете один из CAs (etcd-ca, kubernetes-ca, front-proxy-ca):
- Фаза 1 (расширение доверия):
  - Сгенерировать новый CA.
  - Разнести trust-bundle (old+new) во все места проверки:
    - kube-apiserver: --client-ca-file (bundle), а также bundle в etcd client trust.
    - etcd: --trusted-ca-file и --peer-trusted-ca-file (bundle).
  - Настроить issuer’ы (cert-manager/Vault) выдавать листовые от НОВОГО CA.
- Фаза 2 (перевыпуск листовых):
  - Ротируйте листовые cert компонент за компонентом/нодами (как выше).
- Фаза 3 (сужение доверия):
  - Когда все листовые перешли на новый CA и “макс TTL” прошел — удалите старый CA из bundle.
Примечание по сервис‑аккаунтам:
- Добавьте новый публичный ключ проверки через повтор флага --service-account-key-file (можно указать несколько).
- Установите --service-account-signing-key-file на НОВЫЙ ключ, чтобы новые токены подписывались им.
- После истечения максимального TTL токенов удалите старый ключ из --service-account-key-file.

7) Именование и SAN (чек‑лист)
- kube-apiserver SAN: все IP/FQDN точек, по которым его вызывают (VIP, LB, Node IP, сервис ClusterIP, имена kubernetes.*).
- etcd: для каждого узла server/peer SAN должны включать IP и FQDN этой ноды.
- kubelet server cert: IP/FQDN ноды.
- Следите за clusterDomain (обычно cluster.local) — добавляйте его во внутренние DNS‑имена.

8) Доступ людей/ботов к API
- Люди: OIDC против клиентских cert — проще ротация, меньше ключей на дисках. kubeconfig содержит короткоживущий токен/refresh-поток от вашего IdP.
- Боты/CI: либо OIDC, либо краткоживущие клиентские cert (30–90d) с автоматической перевыдачей.

9) Распространение доверия и секретов
- Корневые/промежуточные cert — через систему конфигураций (GPO/Ansible/Salt/SCCM/образ).
- Хранение приватных ключей CA — в HSM или, как минимум, в офлайн‑хранилище с M of N политикой доступа.
- Ключи в /etc/kubernetes/pki с 600, owner root.
- Шифрование Secret’ов в etcd (EncryptionConfiguration), бэкапы etcd шифруются.

10) Мониторинг и оповещения
- Плановые проверки: kubeadm certs check-expiration; openssl x509 -enddate -noout -in <file>.
- Prometheus:
  - От cert-manager: метрики истечения.
  - Собственные экспортеры/скрипты, алерт: “<30 дней до экспирации”.
- Kubernetes CSR:
  - kubectl get csr, следите за застрявшими CSR и отказами.
- Журналы etcd и kube-apiserver при неуспешном TLS handshake.

11) Плейбуки (сжатые)
- Протух API cert (нет внешнего доступа к API):
  1) На control-plane: kubeadm certs renew apiserver apiserver-kubelet-client front-proxy-client
  2) systemctl restart kubelet
  3) Проверить kubectl get nodes с локальной ноды.
- Ротация etcd cert (HA):
  1) Разнести bundle (old+new).
  2) Для узла i: выдать новые server/peer, рестарт, убедиться в кворуме.
  3) Повторить для остальных. Затем удалить old CA.
- Компрометация ноды:
  - cordon/drain, kubectl delete node <name>, отозвать/удалить секреты этой ноды, перевыпустить ее kubelet bootstrap.
- Компрометация service-account signing key:
  - Ввести новый ключ (signing+verify), оставить старый в verify до истечения max TTL токенов, затем удалить старый.

12) Рекомендованные сроки/план
- Ежедневно: алерты о <30 дней до экспирации.
- Еженедельно: автоперевыпуск kubelet через CSR API (если срок короткий).
- Ежеквартально: контрольная ротация листовых control-plane/etcd (если выбрали 90d).
- Ежегодно: тестовый DR‑прогон ротации CA на dev/стенде.
- За 60–90 дней до истечения Intermediate: двухфазная ротация CA (bundle → перевыпуск → вычищение старого).

Минимальный набор команд (пример, kubeadm)
- Проверка сроков:
  - kubeadm certs check-expiration
- Перевыпуск control-plane:
  - kubeadm certs renew all
  - systemctl restart kubelet
- CSR kubelet:
  - kubectl get csr
  - kubectl certificate approve <csr> (если автопроцедуры выключены)

Итог
- Стройте иерархию CA с офлайн‑рутом, разносите доверие централизованно.
- Делите CA: kubernetes-ca, front-proxy-ca, etcd-ca, + ключи SA.
- Включайте авто‑ротацию kubelet и листовых cert с короткими сроками.
- Для смены CA используйте двухфазный bundle‑подход.
- Для людей — OIDC; для приложений — cert-manager/Vault/step-ca.
- Документируйте плейбуки и регулярно тренируйте ротации на стендах.

Если подскажете ваш способ развёртывания (kubeadm/kops/анси́бл/самосбор), количество control‑plane узлов, и нужен ли SSO (OIDC), — дам точные команды, файлы конфигов и готовый runbook под вашу среду.
