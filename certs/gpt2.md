Да, **можете**. В вашем случае после `kubeadm certs renew all` обычная перезагрузка master-узла вполне заменяет ручной рестарт static Pod'ов.

После reboot kubelet заново запустит static Pods `etcd`, `kube-apiserver`, `kube-controller-manager` и `kube-scheduler`, и они уже прочитают обновлённые сертификаты. Kubernetes требует именно рестарт control-plane компонентов после renew; reboot узла это условие выполняет. ([Kubernetes][1])

Я бы делал так **строго по одному master**:

```bash
# master1
sudo kubeadm certs check-expiration
sudo kubeadm certs renew all
sudo reboot
```

После загрузки **не переходить сразу к master2**, а сначала убедиться, что master1 полностью вернулся:

```bash
kubectl get nodes
kubectl get pods -n kube-system -o wide
```

Проверить, что на `master1` снова работают:

```text
etcd-master1
kube-apiserver-master1
kube-controller-manager-master1
kube-scheduler-master1
```

И желательно проверить etcd:

```bash
kubectl -n kube-system exec etcd-master1 -- \
  sh -c 'ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
  --key=/etc/kubernetes/pki/etcd/healthcheck-client.key \
  endpoint health'
```

После успешной проверки:

```text
master1: renew → reboot → verify
                      ↓
master2: renew → reboot → verify
                      ↓
master3: renew → reboot → verify
```

### Будет ли простой

При вашей схеме **общего простоя быть не должно**:

```text
          etcd        apiserver
M1 down    2/3           2/3
M2 down    2/3           2/3
M3 down    2/3           2/3
```

Для 3-member etcd два оставшихся узла сохраняют quorum. А kubeadm действительно запускает `etcd` и компоненты control plane как static Pods, которыми управляет локальный kubelet. ([Kubernetes][2])

Есть только важные условия:

* **никогда не перезагружать два master одновременно**;
* после каждого reboot дождаться, пока etcd снова станет healthy;
* API-клиенты должны ходить через HA/LB endpoint, а не напрямую на конкретный master;
* если на master'ах запущены обычные workload Pod'ы, reboot, естественно, затронет и их.

Я бы даже предпочёл **reboot** ручному перемещению файлов из `/etc/kubernetes/manifests`: процедура чуть дольше, зато проще и меньше шансов ошибиться с отдельным static Pod.

И ещё после `renew all` не забудьте про `$HOME/.kube/config`: если это копия `/etc/kubernetes/admin.conf`, reboot её **не обновит**. После ротации нужно скопировать новый `admin.conf`. ([Kubernetes][3])

[1]: https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-certs/?utm_source=chatgpt.com "kubeadm certs | Kubernetes"
[2]: https://kubernetes.io/docs/concepts/workloads/pods/static-pods/?utm_source=chatgpt.com "Static Pods | Kubernetes"
[3]: https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-certs/?source=post_page-----5edc60e53c31--------------------------------&utm_source=chatgpt.com "Certificate Management with kubeadm | Kubernetes"
