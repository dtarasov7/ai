Учитывая строгие ограничения (обновлять нельзя, артефакты утеряны, следы "ручного вмешательства"), ваша задача — зафиксировать текущее состояние "как есть" (snapshot), чтобы иметь возможность аварийного восстановления. Поскольку это версия 1.24, средой запуска скорее всего является `containerd` (Docker shim был удален в 1.24), что меняет подход к работе с образами.

Ниже представлен детальный план аудита, бэкапа и тюнинга.

***

## Часть 1: Аудит и Экспорт (Reverse Engineering)

Ваша цель — восстановить "исходный код" инфраструктуры (манифесты и чарты) из живого кластера.

### 1. Сохранение "чистых" манифестов
Команда `kubectl get -o yaml` выгружает много системного шума (`managedFields`, `status`, `uid`). Используйте плагин `kubectl-neat` или фильтрацию `yq` для получения чистых манифестов, пригодных для повторного применения.

*   **Установка kubectl-neat:**
    ```bash
    kubectl krew install neat
    ```
*   **Экспорт всех ресурсов:**
    ```bash
    # Экспорт всего кластера в один файл (для disaster recovery)
    kubectl get all,cm,secret,ing,pvc,sc,sa,role,rolebinding -A -o yaml | kubectl neat > full-cluster-backup.yaml
    ```

### 2. Восстановление Helm чартов
Helm 3 хранит свои релизы (и сами чарты!) в секретах Kubernetes. Вы можете вытащить **оригинальный чарт** и **values.yaml**, которые использовались при установке.

*   **Найдите секреты релизов:**
    ```bash
    kubectl get secrets -A -l owner=helm
    ```
*   **Извлеките исходный код чарта:**
    Helm хранит данные в base64 + gzip. Скрипт ниже восстановит `.tgz` архив чарта и пользовательские `values.yaml` для конкретного релиза (например, `my-release` в неймспейсе `default`):
    ```bash
    # Декодируем Release объект
    kubectl get secret sh.helm.release.v1.my-release.v1 -n default -o jsonpath='{.data.release}' | base64 -d | base64 -d | gzip -d > release.json
    
    # Извлекаем Chart (исходники)
    cat release.json | jq -r '.chart' > chart-dump.json 
    # (структура сложная, проще использовать плагин helm-reverse)
    ```
    **Рекомендация:** Используйте готовый инструмент **helm-mapkubeapis** или простые команды helm для извлечения values:
    ```bash
    helm get values <release-name> -n <namespace> > current-values.yaml
    helm get manifest <release-name> -n <namespace> > current-manifest.yaml
    ```

### 3. Экспорт модифицированных образов (Самое важное)
Поскольку вы подозреваете, что контейнеры были "правлены по месту" (in-place modifications), вам нельзя доверять тегам из Docker Hub. Если кто-то сделал `docker build` и запушил его как `etcd:v2.6.7`, но с другим кодом, официальный образ сломает ваш кластер при восстановлении.

В k8s 1.24 используется **containerd**. Команды `docker save` здесь не сработают (если только вы явно не ставили docker-engine). Используйте `ctr` или `nerdctl`.

*   **Шаг 3.1: Найти ID запущенного образа**
    Зайдите на ноду, где бежит подозрительный под:
    ```bash
    crictl ps --name etcd # найдите ID контейнера
    crictl inspect <container-id> | grep image # найдите sha256 образа
    ```
*   **Шаг 3.2: Выгрузить образ в tar-архив**
    Вам нужно пространство имен `k8s.io` (стандарт для containerd в k8s).
    ```bash
    # Листинг образов
    ctr -n k8s.io images ls | grep etcd
    
    # Экспорт образа в файл (включая все слои "как есть" на диске)
    ctr -n k8s.io images export etcd-custom-dump.tar <image-name-with-tag>
    ```
    *Сохраните этот tar-файл в надежное хранилище (S3/Backup Server). Это ваш единственный способ запустить именно "ту самую" версию etcd.*

*   **Шаг 3.3: Проверка целостности (Drift Detection)**
    Чтобы понять, отличается ли образ от официального, сравните их дайджесты:
    1.  Получите дайджест локального образа: `crictl inspecti <image> | grep digest`.
    2.  Посмотрите дайджест в официальном репо (через skopeo или docker hub).
    3.  Если дайджесты не совпадают — это кастомная сборка.

***

## Часть 2: План аудита

Создайте таблицу-инвентаризацию со следующими колонками:

| Component | Install Method | Version | Image Status | Drift Notes |
| :--- | :--- | :--- | :--- | :--- |
| etcd | Static Pod | 3.5.x | **Custom** (SHA mismatch) | Конфиг отличается от upstream |
| nginx-ingress | Helm | 4.1.0 | Official | Values.yaml восстановлен |
| custom-app | Manifest | v1.2 | Local Registry | Манифест восстановлен через kubectl-neat |

**Критические места для проверки:**
1.  **Static Pods:** Проверьте `/etc/kubernetes/manifests` на нодах. Эти поды не управляются через API k8s напрямую. Бэкапить нужно сами файлы `.yaml` с дисков мастер-нод.
2.  **Сертификаты:** Проверьте срок действия сертификатов `/etc/kubernetes/pki`. В старых кластерах они часто истекают через год.
    ```bash
    kubeadm certs check-expiration
    ```

***

## Часть 3: Рекомендации по тюнингу для High Load (k8s 1.24)

Для нагруженных систем (High Load) настройки "по умолчанию" в kubespray/kubeadm часто недостаточны.

### 1. Etcd (Сердце кластера)
Etcd критичен к задержкам диска. Если `fsync` длится дольше 100мс, кластер может развалиться.
*   **Mounts:** Перенесите `/var/lib/etcd` на отдельный быстрый NVMe диск, чтобы логи приложений не забивали IO.
*   **Nice priority:** Дайте процессу etcd высший приоритет IO.
    ```bash
    ionice -c2 -n0 -p $(pgrep etcd)
    ```
*   **Tuning:** Увеличьте таймауты, если сеть нестабильна (в аргументах запуска etcd):
    *   `--heartbeat-interval=500` (default 100ms)
    *   `--election-timeout=5000` (default 1000ms)

### 2. Kube-API Server
При большом количестве запросов (High Load, много watch-запросов от контроллеров):
*   **Max in-flight:** Увеличьте лимиты параллельных запросов (аргументы apiserver):
    *   `--max-mutating-requests-inflight=1000` (default 200)
    *   `--max-requests-inflight=3000` (default 400)

### 3. Sysctl (Kernel Tuning)
Примените через DaemonSet ко всем нодам (или через `/etc/sysctl.d/`):
```bash
# Увеличение очереди соединений (критично для Ingress/Proxy)
net.core.somaxconn = 32768
net.netfilter.nf_conntrack_max = 1048576

# Расширение диапазона портов для исходящих соединений
net.ipv4.ip_local_port_range = 1024 65535

# Отключение swap (обязательно для k8s, но проверьте)
vm.swappiness = 0

# Увеличение лимита открытых файлов
fs.file-max = 2097152
```

### 4. Networking (IPVS)
Убедитесь, что `kube-proxy` работает в режиме **IPVS**, а не iptables. При большом количестве сервисов (>1000) iptables начинает тормозить процессор.
*   Проверка: `kubectl logs -n kube-system -l k8s-app=kube-proxy | grep "Using ipvs Proxier"`

### 5. Ресурсы Node Allocatable
Защитите демоны системы (ssh, docker/containerd, kubelet) от OOM Kill, зарезервировав ресурсы. В конфиге Kubelet (`/var/lib/kubelet/config.yaml`):
```yaml
systemReserved:
  cpu: "500m"
  memory: "1Gi"
kubeReserved:
  cpu: "500m"
  memory: "1Gi"
evictionHard:
  memory.available: "500Mi"
```
Это предотвратит зависание ноды при 100% загрузке приложениями. [etcd](https://etcd.io/docs/v3.6/tuning/)
