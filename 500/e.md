Да, это как раз типичный кейс: **/var маленький, а весь “мусор” Kubernetes/CRI живёт под /var**.
Если расширить `/var` нельзя, самый рабочий путь — **перенести данные kubelet/containerd на `/srv`**.

## Что именно можно унести на `/srv`

### 1) kubelet

У kubelet базовый каталог по умолчанию — **`/var/lib/kubelet`**, и он **настраивается через `--root-dir`**. Это официальный параметр kubelet. ([Kubernetes][1])

### 2) containerd

У containerd каталог данных по умолчанию — **`/var/lib/containerd`**, и он задаётся в `config.toml` через параметр **`root`**. Конфиг обычно в `/etc/containerd/config.toml`. ([Debian Manpages][2])

---

## Самый практичный вариант (рекомендую)

Чтобы не ломать плагины/CSI, которые иногда ожидают пути под `/var/lib/kubelet`, лучше сделать так:

* **реальные данные хранить на `/srv/...`**
* а в `/var/...` оставить **bind mount** (или symlink, но bind mount надёжнее)

### Схема

* `/srv/kubelet`  → bind в `/var/lib/kubelet`
* `/srv/containerd` → настроить как `root` в containerd (или тоже bind в `/var/lib/containerd`)

---

## Вариант A (минимум изменений, самый безопасный)

### Перенос через bind mount (без смены kubelet `--root-dir`)

Так вы оставляете путь `/var/lib/kubelet`, но физически данные лежат на `/srv`.

### Шаги

> Делать в maintenance window, ноду лучше cordon/drain.

```bash
# 0) На контрол-плейне (или с любой машины с kubectl)
kubectl cordon <node>
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data
```

На ноде:

```bash
sudo systemctl stop kubelet
sudo systemctl stop containerd

sudo mkdir -p /srv/kubelet /srv/containerd

# Переносим данные
sudo rsync -aHAX --numeric-ids /var/lib/kubelet/   /srv/kubelet/
sudo rsync -aHAX --numeric-ids /var/lib/containerd/ /srv/containerd/
```

Сделайте bind mounts:

```bash
sudo mount --bind /srv/kubelet /var/lib/kubelet
sudo mount --bind /srv/containerd /var/lib/containerd
```

Добавьте в `/etc/fstab`, чтобы пережило перезагрузку:

```fstab
/srv/kubelet    /var/lib/kubelet    none    bind    0 0
/srv/containerd /var/lib/containerd none    bind    0 0
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl start containerd
sudo systemctl start kubelet
```

Потом:

```bash
kubectl uncordon <node>
```

✅ Плюс этого варианта: **для kubelet/CSI путь остаётся `/var/lib/kubelet`**, меньше шансов на сюрпризы.

---

## Вариант B (чистый, но требует аккуратности)

### Перенастроить containerd и kubelet на `/srv/...`

### containerd

В `/etc/containerd/config.toml`:

```toml
root = "/srv/containerd"
state = "/run/containerd"
```

`root` — это постоянные данные (по умолчанию `/var/lib/containerd`). `state` обычно оставляют в `/run/containerd`. ([Debian Manpages][2])

### kubelet

Для kubelet можно задать `--root-dir=/srv/kubelet` (или через kubelet config/systemd drop-in). Параметр официальный. ([Kubernetes][1])

⚠️ Но тут есть нюанс: многие компоненты/плагины (device plugins/CSI) привязаны к путям внутри kubelet root и нередко ожидают `/var/lib/kubelet/...`, поэтому при смене root-dir иногда приходится править манифесты плагинов. Это связано с тем, что kubelet держит сокеты/плагины именно в своём base dir. ([Kubernetes][3])

---

## Что ещё очень желательно вынести/почистить

Даже после переноса root-каталогов `/var` может забиваться логами:

* `/var/log/pods`
* `/var/log/containers` (часто symlink’и)
* системные логи (`journald`)

### Быстрая проверка

```bash
sudo du -xh /var | sort -h | tail -50
sudo du -sh /var/lib/kubelet /var/lib/containerd /var/log/pods /var/log/containers 2>/dev/null
df -h /var /srv
```

Если много ест `journald`:

```bash
journalctl --disk-usage
sudo journalctl --vacuum-size=500M
```

---

## И отдельно: в манифесты Pod’ов

Обязательно задайте `ephemeral-storage requests/limits`, иначе kubelet продолжит эвиктить “кого попало” при давлении по диску (и будет писать `request=0`).

```yaml
resources:
  requests:
    ephemeral-storage: "256Mi"
  limits:
    ephemeral-storage: "1Gi"
```

---

## Что бы я сделал на вашем месте

1. **Вариант A (bind mount)** для `/var/lib/kubelet` и `/var/lib/containerd` на `/srv`
2. Поставил `ephemeral-storage` requests/limits у проблемных Pod’ов
3. Проверил/ограничил логи (`journald` + контейнерные логи)

Если хотите, могу дать **готовый пошаговый план именно под вашу ОС** (Ubuntu/CentOS/RHEL) и формат systemd unit для kubelet/containerd.

[1]: https://kubernetes.io/docs/reference/command-line-tools-reference/kubelet/ "kubelet | Kubernetes"
[2]: https://manpages.debian.org/trixie/containerd/containerd-config.toml.5.en.html "containerd-config.toml(5) — containerd — Debian trixie — Debian Manpages"
[3]: https://kubernetes.io/docs/reference/node/kubelet-files/ "Local Files And Paths Used By The Kubelet | Kubernetes"



Ниже готовый **Ansible playbook** для **варианта A (bind mount)**:

* переносит данные в базовый каталог (`/srv` по умолчанию, можно `/free`)
* делает bind-mount обратно в:

  * `/var/lib/kubelet`
  * `/var/lib/containerd`
  * `/var/log/pods`
  * `/var/log/containers` (если это не symlink)
* добавляет записи в `fstab`
* останавливает/запускает `kubelet` и `containerd`

> Базовый путь вынесен в переменную `k8s_data_base_path` — как вы просили.

```yaml
---
- name: Move kubelet/containerd/logs to larger disk and bind-mount back
  hosts: k8s_nodes
  become: true
  gather_facts: true

  vars:
    # Базовый путь для новых каталогов.
    # Переопределяйте в inventory/group_vars/host_vars:
    # k8s_data_base_path: /free
    k8s_data_base_path: /srv

    # Что переносим и куда бинд-монтируем обратно
    k8s_bind_mounts:
      - name: kubelet
        src: "{{ k8s_data_base_path }}/kubelet"
        dst: /var/lib/kubelet
      - name: containerd
        src: "{{ k8s_data_base_path }}/containerd"
        dst: /var/lib/containerd
      - name: pods_logs
        src: "{{ k8s_data_base_path }}/log/pods"
        dst: /var/log/pods
      - name: containers_logs
        src: "{{ k8s_data_base_path }}/log/containers"
        dst: /var/log/containers

    # Если true — попробует выполнить cordon/drain/uncordon через kubectl с control host
    # (по умолчанию выключено, чтобы не ломать, если kubectl не настроен)
    k8s_manage_node_scheduling: false

  pre_tasks:
    - name: Check whether /var/log/containers is a symlink
      ansible.builtin.stat:
        path: /var/log/containers
        follow: false
      register: var_log_containers_stat

    - name: Build effective mount list (skip /var/log/containers if it is a symlink)
      ansible.builtin.set_fact:
        effective_bind_mounts: >-
          {{
            k8s_bind_mounts
            | rejectattr('dst', 'equalto', '/var/log/containers')
            | list
            +
            (
              [] if (var_log_containers_stat.stat.islnk | default(false))
              else [k8s_bind_mounts | selectattr('dst','equalto','/var/log/containers') | first]
            )
          }}

    - name: Show selected mounts
      ansible.builtin.debug:
        var: effective_bind_mounts

    # Опционально: cordon/drain (выполняется с control machine)
    - name: Cordon node (optional)
      ansible.builtin.command: "kubectl cordon {{ inventory_hostname }}"
      delegate_to: localhost
      become: false
      changed_when: true
      when: k8s_manage_node_scheduling | bool

    - name: Drain node (optional)
      ansible.builtin.command: >-
        kubectl drain {{ inventory_hostname }}
        --ignore-daemonsets
        --delete-emptydir-data
        --force
      delegate_to: localhost
      become: false
      changed_when: true
      when: k8s_manage_node_scheduling | bool

  tasks:
    - name: Stop kubelet
      ansible.builtin.service:
        name: kubelet
        state: stopped
      ignore_errors: true

    - name: Stop containerd
      ansible.builtin.service:
        name: containerd
        state: stopped
      ignore_errors: true

    - name: Ensure base path exists
      ansible.builtin.file:
        path: "{{ k8s_data_base_path }}"
        state: directory
        mode: "0755"

    - name: Ensure target directories under base path exist
      ansible.builtin.file:
        path: "{{ item.src }}"
        state: directory
        mode: "0755"
      loop: "{{ effective_bind_mounts }}"

    - name: Ensure destination directories exist before rsync
      ansible.builtin.file:
        path: "{{ item.dst }}"
        state: directory
        mode: "0755"
      loop: "{{ effective_bind_mounts }}"
      when: not (item.dst == '/var/log/containers' and (var_log_containers_stat.stat.islnk | default(false)))

    - name: Check migration marker for each mount
      ansible.builtin.stat:
        path: "{{ item.src }}/.migrated_by_ansible"
      register: migration_markers
      loop: "{{ effective_bind_mounts }}"

    - name: Rsync data from /var to new location (first run only)
      ansible.builtin.command: >
        rsync -aHAX --numeric-ids {{ item.item.dst }}/ {{ item.item.src }}/
      loop: "{{ migration_markers.results }}"
      when: not item.stat.exists
      changed_when: true

    - name: Create migration marker
      ansible.builtin.file:
        path: "{{ item.item.src }}/.migrated_by_ansible"
        state: touch
        mode: "0644"
      loop: "{{ migration_markers.results }}"
      when: not item.stat.exists

    - name: Bind mount directories (and persist in fstab)
      ansible.posix.mount:
        src: "{{ item.src }}"
        path: "{{ item.dst }}"
        fstype: none
        opts: bind
        state: mounted
      loop: "{{ effective_bind_mounts }}"

    - name: Start containerd
      ansible.builtin.service:
        name: containerd
        state: started
        enabled: true
      ignore_errors: true

    - name: Start kubelet
      ansible.builtin.service:
        name: kubelet
        state: started
        enabled: true
      ignore_errors: true

  post_tasks:
    # Опционально: uncordon
    - name: Uncordon node (optional)
      ansible.builtin.command: "kubectl uncordon {{ inventory_hostname }}"
      delegate_to: localhost
      become: false
      changed_when: true
      when: k8s_manage_node_scheduling | bool
```

## Как использовать

### 1) Inventory (пример)

```ini
[k8s_nodes]
node1
node2

[k8s_nodes:vars]
k8s_data_base_path=/free
```

Или для части узлов:

* одним узлам `/srv`
* другим `/free` через `host_vars`.

---

## Что важно учесть

* Если `/var/log/containers` у вас **symlink** (часто так и есть), playbook **не будет bind-mount’ить его отдельно** (иначе можно словить конфликт). Достаточно bind на `/var/log/pods`.
* Playbook предполагает, что `containerd` и `kubelet` уже используют стандартные пути (`/var/lib/...`) — мы их не меняем, только переносим хранилище физически.
* Для безопасного применения лучше запускать по одной ноде (`serial: 1`), если это production-кластер.

---

## Рекомендация для production

Добавьте в playbook:

```yaml
serial: 1
```

на уровне play, чтобы ноды обслуживались по очереди.

---

Если хотите, могу сразу дать **версию с `serial: 1`, проверкой свободного места на `/free|/srv` и rollback-задачами** (на случай неудачного запуска).

