Да, конечно — вот версия **без `/var/log/containers` полностью** (только `kubelet`, `containerd` и `/var/log/pods`).

```yaml
---
- name: Move kubelet/containerd/pod logs to larger disk and bind-mount back
  hosts: k8s_nodes
  become: true
  gather_facts: true
  serial: 1

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

    # Если true — попробует выполнить cordon/drain/uncordon через kubectl с control host
    # (по умолчанию выключено, чтобы не ломать, если kubectl не настроен)
    k8s_manage_node_scheduling: false

  pre_tasks:
    - name: Show selected mounts
      ansible.builtin.debug:
        var: k8s_bind_mounts

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
      loop: "{{ k8s_bind_mounts }}"

    - name: Ensure destination directories exist before rsync
      ansible.builtin.file:
        path: "{{ item.dst }}"
        state: directory
        mode: "0755"
      loop: "{{ k8s_bind_mounts }}"

    - name: Check migration marker for each mount
      ansible.builtin.stat:
        path: "{{ item.src }}/.migrated_by_ansible"
      register: migration_markers
      loop: "{{ k8s_bind_mounts }}"

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
      loop: "{{ k8s_bind_mounts }}"

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
    - name: Uncordon node (optional)
      ansible.builtin.command: "kubectl uncordon {{ inventory_hostname }}"
      delegate_to: localhost
      become: false
      changed_when: true
      when: k8s_manage_node_scheduling | bool
```

Если хотите, могу ещё добавить:

* проверку, что на `{{ k8s_data_base_path }}` достаточно места перед миграцией,
* `rollback`-блок (на случай ошибки после остановки сервисов),
* поддержку `crio` вместо `containerd`.

