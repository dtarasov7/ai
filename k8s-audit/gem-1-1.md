Для работы в изолированном окружении Nexus Repository Manager выступает в роли "Registry Mirror" (для Docker) и "Proxy Repo" (для пакетов OS).

Однако **Nexus не является прозрачным HTTP-прокси** (как Squid или Tinyproxy). Он работает как *хранилище*. Поэтому инструменты вроде `kubectl krew`, которые пытаются скачать файлы напрямую с GitHub, **не будут работать через Nexus "из коробки"**, просто указав прокси. Для них используется другой подход (Raw Proxy или ручная загрузка), описанный ниже.

### 1. Настройка Nexus Repository Manager

Вам нужно создать несколько репозиториев типа **Proxy**.

#### А. Docker Registry Proxy (для образов контейнеров)
Kubernetes v1.24 критически зависит от реестра `registry.k8s.io` (старый `k8s.gcr.io` заморожен).

1.  Создайте **Docker (proxy)** репозиторий:
    *   **Name:** `k8s-registry-proxy`
    *   **Remote storage:** `https://registry.k8s.io`
    *   **Docker Index:** `Use Docker Hub` (или `Use proxy registry` если доступно) — для k8s.io это обычно не требуется, но для `docker.io` нужно выбрать `Use Docker Hub`.
2.  Создайте **Docker (proxy)** для DockerHub:
    *   **Name:** `docker-hub-proxy`
    *   **Remote storage:** `https://registry-1.docker.io`
    *   **Docker Index:** `Use Docker Hub`
3.  Создайте **Docker (group)** репозиторий (опционально):
    *   Объединяет оба вышеуказанных в один URL (удобно для настройки `mirrors` на клиентах).

#### Б. Apt/Yum Proxy (для системных пакетов)
*Внимание: старые репозитории Google (`apt.kubernetes.io`) устарели. Для v1.24 и выше сейчас используется `pkgs.k8s.io`, но архивные версии могут лежать по старым путям. Для v1.24 лучше проксировать новый Community-репозиторий.*

1.  Создайте **Apt (proxy)** (для Debian/Ubuntu):
    *   **Name:** `kubernetes-apt-proxy`
    *   **Remote storage:** `https://pkgs.k8s.io/core:/stable:/v1.24/deb/` (Это замороженный репозиторий именно для ветки 1.24).
    *   **Distribution:** `/`
    *   **Flat:** (Обычно нет, но `pkgs.k8s.io` имеет специфичную структуру, лучше указывать прямой URL до нужной ветки).

#### В. "Raw" Repository (для бинарников типа kubectl-neat)
Инструменты вроде `krew` качают плагины с GitHub releases. Проксировать GitHub через Nexus сложно из-за редиректов. Лучший путь для изолированного контура (Air-Gap) — **Hosted Raw Repository**.

1.  Создайте **Raw (hosted)** репозиторий:
    *   **Name:** `tools-raw`
2.  **Алгоритм действий (вместо прокси):**
    *   На машине с интернетом скачайте `kubectl-neat_linux_amd64.tar.gz`.
    *   Загрузите его в этот репозиторий через curl или UI Nexus.
    *   На изолированных хостах скачивайте файл по прямой ссылке из Nexus: `wget http://nexus-internal/repository/tools-raw/kubectl-neat`.

***

### 2. Настройка клиентов (хостов)

#### А. Containerd (Критически важно для k8s 1.24)
В v1.24 удален dockershim, используется containerd. Его нужно научить ходить в Nexus вместо интернета.
Отредактируйте `/etc/containerd/config.toml` (секция `plugins."io.containerd.grpc.v1.cri".registry`):

```toml
[plugins."io.containerd.grpc.v1.cri".registry]
  config_path = "/etc/containerd/certs.d"

  [plugins."io.containerd.grpc.v1.cri".registry.mirrors]
    # Перенаправляем запросы к docker.io в ваш Nexus
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]
      endpoint = ["http://nexus.internal:8081/repository/docker-hub-proxy"]
    

    # Перенаправляем запросы к registry.k8s.io в ваш Nexus
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."registry.k8s.io"]
      endpoint = ["http://nexus.internal:8081/repository/k8s-registry-proxy"]
    
    # Для старых манифестов (k8s.gcr.io)
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."k8s.gcr.io"]
      endpoint = ["http://nexus.internal:8081/repository/k8s-registry-proxy"]
```
*После изменения: `systemctl restart containerd`.*

#### Б. Системный пакетный менеджер (apt)
В `/etc/apt/sources.list.d/kubernetes.list`:
```bash
# Вместо https://pkgs.k8s.io/...
deb http://nexus.internal:8081/repository/kubernetes-apt-proxy/ /
```

#### В. Установка плагинов kubectl (kubectl-neat) без Krew
Поскольку `krew` требует git-доступа к GitHub, в закрытом контуре проще ставить плагины вручную как бинарные файлы.
1.  Скачайте бинарник `kubectl-neat` из вашего Nexus (куда вы его положили в п.1.В).
2.  Сделайте его исполняемым и переместите в PATH:
    ```bash
    chmod +x kubectl-neat
    mv kubectl-neat /usr/local/bin/
    ```
3.  Теперь команда `kubectl neat` заработает (k8s автоматически подхватывает бинарники с префиксом `kubectl-` из PATH).

***

### 3. Таблица совместимости ПО для Kubernetes v1.24

Kubernetes v1.24 вышел в мае 2022 года. Поддержка закончилась в июле 2023. Для стабильной работы используйте следующие версии: [github](https://github.com/kubernetes/ingress-nginx)

| Компонент | Рекомендуемая версия | Примечание |
| :--- | :--- | :--- |
| **Kubernetes (kubelet/kubeadm)** | **v1.24.17** | Последний патч-релиз в ветке 1.24. |
| **Containerd** | **v1.6.28** | Ветка 1.6.x является основной для k8s 1.24. Версии 1.7+ тоже работают, но 1.6 "роднее". |
| **Etcd** | **3.5.3 - 3.5.6** | K8s 1.24 по умолчанию поставлялся с etcd 3.5.3. |
| **Ingress NGINX** | **v1.3.0** или **v1.3.1** | Версия v1.3.x официально поддерживает k8s 1.24. Версии ниже v1.0.0 работать не будут. Более новые (v1.8+) могут требовать более свежий k8s. |
| **Helm** | **v3.9.x** | Helm v3.9 вышел одновременно с k8s 1.24. Также подойдут v3.8.x - v3.12.x. |
| **Calico (CNI)** | **v3.23 - v3.25** | Версии этого периода (2022 год). |
| **Cert-Manager** | **v1.8.0 - v1.10.0** | v1.8.0 добавил полную поддержку k8s 1.24. |

**Важное замечание по v1.24:**
Это первая версия, где **dockershim отключен полностью**. Убедитесь, что в аргументах kubelet **нет** флагов `--network-plugin=cni` (устарело) и `--container-runtime=docker`. Должен быть настроен `--container-runtime-endpoint=unix:///run/containerd/containerd.sock`.