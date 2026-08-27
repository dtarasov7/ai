Да. Для вашего случая — **Kubernetes 1.24, kubeadm, 3 control-plane, stacked etcd по одному члену на каждом master** — обновление можно провести **без общего простоя кластера**, если делать rolling: `master1 → master2 → master3` и не переходить к следующему, пока предыдущий полностью не вернулся.

`kubeadm certs renew all` необходимо выполнять на **каждом control-plane узле отдельно**. В kubeadm 1.24 команда `certs check-expiration` уже штатно поддерживается. ([Gist][1])

### Что будет с доступностью

При перезапуске одного master вы временно теряете:

* 1 из 3 `kube-apiserver`;
* 1 из 3 членов `etcd`;
* один `controller-manager`;
* один `scheduler`.

Для etcd остаётся **2 из 3**, то есть quorum сохраняется. Stacked topology как раз предполагает локальный etcd на каждом control-plane; Kubernetes рекомендует минимум три таких узла для HA. ([Kubernetes][2])

Поэтому приложения и существующие Pod'ы продолжат работать. API также останется доступен через два других master, **если перед ними есть корректно настроенный LB с health-check**.

Возможны краткие эффекты: при рестарте текущего leader `kube-controller-manager` или `kube-scheduler` произойдёт перевыбор лидера, поэтому создание/перепланирование Pod'ов может на несколько секунд задержаться. Если клиент подключён непосредственно к конкретному master, а не через LB, он получит ошибку во время рестарта этого master.

---

## 1. Предварительная проверка

Сначала с любого master:

```bash
kubectl get nodes -o wide
kubectl get pods -n kube-system -o wide
```

Убедитесь, что все три control-plane узла `Ready`, а все три etcd:

```bash
kubectl get pods -n kube-system -l component=etcd -o wide
```

находятся в `Running`.

На **каждом master**:

```bash
sudo kubeadm certs check-expiration
```

Особенно смотрите две секции.

Первая — обычные сертификаты:

```text
admin.conf
apiserver
apiserver-etcd-client
apiserver-kubelet-client
controller-manager.conf
etcd-healthcheck-client
etcd-peer
etcd-server
front-proxy-client
scheduler.conf
```

Вторая — CA:

```text
ca
etcd-ca
front-proxy-ca
```

Это важно: `kubeadm certs renew all` — обычная ежегодная ротация сертификатов, но **ротацию CA kubeadm штатно не выполняет**. Если у `ca`, `etcd-ca` или `front-proxy-ca` тоже заканчивается срок, это уже другая процедура. ([Kubernetes][3])

По умолчанию CA живут значительно дольше обычных сертификатов, поэтому при ежегодном обслуживании обычно проблема именно в leaf-сертификатах.

---

## 2. Сделайте backup

Перед началом я бы обязательно сделал snapshot etcd.

Например, на одном из master:

```bash
kubectl -n kube-system exec etcd-$(hostname) -- \
  sh -c 'ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
  --key=/etc/kubernetes/pki/etcd/healthcheck-client.key \
  snapshot save /var/lib/etcd/pre-cert-renew.db'
```

etcd официально рекомендует snapshot как point-in-time backup перед подобными операциями. ([etcd][4])

И на **каждом master** сохраните `/etc/kubernetes`:

```bash
sudo tar czf /root/kubernetes-before-cert-renew-$(date +%F-%H%M).tgz \
  /etc/kubernetes/pki \
  /etc/kubernetes/*.conf \
  /etc/kubernetes/manifests
```

Не надо копировать новые `apiserver.crt`, `etcd/server.crt`, `etcd/peer.crt` между master'ами — часть сертификатов содержит SAN/IP конкретного узла.

---

# 3. Обновляем master1

### 3.1 Проверить сертификаты ещё раз

```bash
sudo kubeadm certs check-expiration
```

### 3.2 Обновить

```bash
sudo kubeadm certs renew all
```

Команда обновляет известные kubeadm сертификаты независимо от того, сколько времени им осталось. SAN/CN берутся из существующих сертификатов, поэтому заново перечислять IP/DNS обычно не нужно. ([Kubernetes][5])

После неё:

```bash
sudo kubeadm certs check-expiration
```

Должно появиться примерно ещё 1 год для обновлённых сертификатов.

---

## 4. Перезапустить control-plane на master1

Это обязательный этап.

Просто выполнить `renew all` недостаточно: Kubernetes документация требует перезапустить control-plane Pod'ы, потому что динамическая перечитка сертификатов гарантирована не для всех компонентов. ([Kubernetes][3])

У вас это static Pods:

```text
/etc/kubernetes/manifests/
    etcd.yaml
    kube-apiserver.yaml
    kube-controller-manager.yaml
    kube-scheduler.yaml
```

Документированный способ:

```bash
sudo mkdir -p /etc/kubernetes/manifests.backup
```

Сначала перенести manifest'ы:

```bash
sudo mv /etc/kubernetes/manifests/*.yaml \
        /etc/kubernetes/manifests.backup/
```

Подождать примерно 20–30 секунд:

```bash
sleep 30
```

Kubelet увидит исчезновение static manifests и остановит компоненты. Официальная документация указывает примерно 20 секунд, в зависимости от `fileCheckFrequency`. ([Kubernetes][3])

Вернуть:

```bash
sudo mv /etc/kubernetes/manifests.backup/*.yaml \
        /etc/kubernetes/manifests/
```

И ждать их запуска.

**В этот момент master1 целиком выпадает из control plane, включая его etcd. Это нормально — но только один master одновременно.**

---

## 5. Проверка master1

Не переходите к `master2`, пока `master1` полностью не восстановился.

Проверить локально:

```bash
sudo crictl ps | grep -E 'etcd|kube-apiserver|kube-controller-manager|kube-scheduler'
```

Должны быть четыре новых running-container.

Через API:

```bash
kubectl get pods -n kube-system -o wide | grep "$(hostname)"
```

Проверить API:

```bash
kubectl get --raw='/readyz?verbose'
```

И etcd:

```bash
kubectl -n kube-system exec etcd-$(hostname) -- \
  sh -c 'ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
  --key=/etc/kubernetes/pki/etcd/healthcheck-client.key \
  endpoint health'
```

Я бы ещё посмотрел:

```bash
kubectl get nodes
kubectl get pods -A | grep -v Running
```

Если всё нормально — только тогда переходить дальше.

---

# 6. Обновить master2

На `master2` повторить:

```bash
sudo kubeadm certs check-expiration

sudo kubeadm certs renew all

sudo kubeadm certs check-expiration
```

Затем:

```bash
sudo mkdir -p /etc/kubernetes/manifests.backup

sudo mv /etc/kubernetes/manifests/*.yaml \
        /etc/kubernetes/manifests.backup/

sleep 30

sudo mv /etc/kubernetes/manifests.backup/*.yaml \
        /etc/kubernetes/manifests/
```

Дождаться полного восстановления `etcd + apiserver + controller-manager + scheduler`.

Проверить etcd/API.

---

# 7. Затем master3

Абсолютно та же операция.

Получается порядок:

```text
                  etcd available       API available

начало             3/3                  3/3

renew/restart M1   2/3                  2/3
M1 восстановлен    3/3                  3/3

renew/restart M2   2/3                  2/3
M2 восстановлен    3/3                  3/3

renew/restart M3   2/3                  2/3
M3 восстановлен    3/3                  3/3
```

**Никогда не останавливайте etcd одновременно на двух master'ах.** У 3-членного etcd для работы нужны два участника.

---

# 8. Обновить kubeconfig администратора

`kubeadm certs renew all` также обновит сертификат внутри:

```text
/etc/kubernetes/admin.conf
```

Но если у вас `kubectl` использует копию:

```text
/root/.kube/config
```

или

```text
/home/user/.kube/config
```

она **сама не обновится**.

После ротации надо заменить её:

```bash
mkdir -p $HOME/.kube

sudo cp /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
```

Это прямо предусмотрено документацией kubeadm. ([Kubernetes][3])

Если `admin.conf` скопирован на bastion/рабочую машину — обновите копию и там.

---

# Нужно ли трогать kubelet-сертификаты?

Обычно **нет**.

`kubelet.conf` не входит в обычный список `kubeadm certs renew`, потому что kubelet использует автоматическую ротацию client certificate через:

```text
/var/lib/kubelet/pki/
```

Это отдельный механизм. ([Kubernetes][3])

---

## Будет ли downtime?

**Для workload — нет.**

**Для Kubernetes API — при нормальном HA/LB тоже нет.**

Но есть несколько оговорок:

| Компонент                      | Что произойдёт                         |
| ------------------------------ | -------------------------------------- |
| Уже работающие приложения      | продолжают работать                    |
| Service/Ingress traffic        | обычно без изменений                   |
| kube-apiserver                 | остаются 2 из 3                        |
| etcd                           | остаются 2 из 3, quorum есть           |
| scheduler                      | возможна краткая leader election       |
| controller-manager             | возможна краткая leader election       |
| `kubectl` через HA endpoint    | должен продолжать работать             |
| `kubectl https://master1:6443` | на время рестарта master1 не работает  |
| LB без нормальных health-check | возможны краткие 502/connection errors |

То есть с точки зрения пользователя **zero-downtime вполне достижим**.

Главное правило здесь:

```text
MASTER1
  renew
  restart
  verify API
  verify etcd
  ↓
MASTER2
  renew
  restart
  verify API
  verify etcd
  ↓
MASTER3
  renew
  restart
  verify API
  verify etcd
```

А не:

```text
renew master1
renew master2
renew master3
restart всех
```

Последний вариант особенно опасен: если одновременно убрать `etcd.yaml` на двух/трёх узлах, потеряете quorum.

И ещё один важный момент: **Kubernetes 1.24 давно EOL**, поэтому после ротации сертификатов я бы отдельно запланировал последовательный upgrade к поддерживаемой версии. Само обновление сертификатов, однако, не требует одновременно обновлять Kubernetes.

[1]: https://gist.github.com/superbrothers/eb1cb72be8f89b871d225b1e27b7fe90?utm_source=chatgpt.com "Kubernetes v1.24.0 CHANGELOG with SIG information (Original https://github.com/kubernetes/kubernetes/blob/master/CHANGELOG/CHANGELOG-1.24.md) · GitHub"
[2]: https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/ha-topology/?trk=article-ssr-frontend-pulse_little-text-block&utm_source=chatgpt.com "Options for Highly Available Topology | Kubernetes"
[3]: https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-certs/?source=post_page-----5edc60e53c31-------------------------------- "Certificate Management with kubeadm | Kubernetes"
[4]: https://etcd.io/docs/v3.5/tutorials/how-to-save-database/?utm_source=chatgpt.com "How to save the database | etcd"
[5]: https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-certs/?utm_source=chatgpt.com "kubeadm certs | Kubernetes"
