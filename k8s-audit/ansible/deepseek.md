Вот несколько вариантов с использованием только shell-команд в Ansible:

## Вариант 1: Экспорт всех ресурсов через kubectl get

```yaml
- name: Сохранить все манифесты из кластера
  hosts: master_nodes  # или all для всех узлов
  tasks:
    - name: Создать директорию для сохранения
      shell: mkdir -p /tmp/k8s-manifests/
      when: inventory_hostname in groups['master_nodes'][0]  # Только на первом мастере

    - name: Получить все namespaces
      shell: |
        kubectl get ns -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n'
      register: namespaces
      when: inventory_hostname in groups['master_nodes'][0]
      changed_when: false

    - name: Экспорт ресурсов из каждого namespace
      shell: |
        for ns in {{ namespaces.stdout_lines | join(' ') }}; do
          mkdir -p /tmp/k8s-manifests/$ns
          for resource in $(kubectl api-resources --namespaced=true -o name); do
            kubectl get $resource -n $ns -o yaml > /tmp/k8s-manifests/$ns/${resource}.yaml 2>/dev/null || true
          done
        done
      when: inventory_hostname in groups['master_nodes'][0]

    - name: Экспорт кластерных ресурсов (без namespace)
      shell: |
        mkdir -p /tmp/k8s-manifests/cluster
        for resource in $(kubectl api-resources --namespaced=false -o name); do
          kubectl get $resource -o yaml > /tmp/k8s-manifests/cluster/${resource}.yaml 2>/dev/null || true
        done
      when: inventory_hostname in groups['master_nodes'][0]
```

## Вариант 2: Используя kubectl get all и дополнительные ресурсы

```yaml
- name: Полный экспорт ресурсов
  hosts: master_nodes
  tasks:
    - name: Создать структуру директорий
      shell: |
        BASE_DIR="/tmp/k8s-backup-$(date +%Y%m%d-%H%M%S)"
        mkdir -p $BASE_DIR/{cluster,namespaces}
        echo $BASE_DIR
      register: backup_dir
      changed_when: false

    - name: Экспортировать все ресурсы с детализацией
      shell: |
        BASE_DIR={{ backup_dir.stdout }}
        
        # Все ресурсы в namespaces
        kubectl get namespaces -o jsonpath='{.items[*].metadata.name}' | \
        while read ns; do
          mkdir -p $BASE_DIR/namespaces/$ns
          
          # Получить все типы ресурсов для namespace
          kubectl api-resources --namespaced=true -o name | \
          while read resource; do
            kubectl get "$resource" -n "$ns" -o yaml > \
            "$BASE_DIR/namespaces/$ns/${resource//\//_}.yaml" 2>/dev/null || true
          done
        done

        # Кластерные ресурсы
        kubectl api-resources --namespaced=false -o name | \
        while read resource; do
          kubectl get "$resource" -o yaml > \
          "$BASE_DIR/cluster/${resource//\//_}.yaml" 2>/dev/null || true
        done

        # Дополнительно: события и логи
        kubectl get events --all-namespaces -o yaml > $BASE_DIR/all-events.yaml
        kubectl describe nodes > $BASE_DIR/nodes-description.txt
        
        echo "Экспорт завершен в: $BASE_DIR"
      when: inventory_hostname in groups['master_nodes'][0]
```

## Вариант 3: Сжатый архив с выборочными ресурсами

```yaml
- name: Экспорт и архивация манифестов
  hosts: master_nodes
  tasks:
    - name: Экспорт основных ресурсов
      shell: |
        BACKUP_DIR="/opt/k8s-backup"
        mkdir -p $BACKUP_DIR
        
        # Основные ресурсы по категориям
        declare -A resources=(
          ["workloads"]="deployments,statefulsets,daemonsets,jobs,cronjobs"
          ["networking"]="services,ingresses,endpoints,networkpolicies"
          ["config"]="configmaps,secrets"
          ["storage"]="persistentvolumes,persistentvolumeclaims,storageclasses"
          ["rbac"]="roles,rolebindings,clusterroles,clusterrolebindings,serviceaccounts"
        )
        
        for category in "${!resources[@]}"; do
          mkdir -p $BACKUP_DIR/$category
          IFS=',' read -ra res_array <<< "${resources[$category]}"
          for res in "${res_array[@]}"; do
            # Для ресурсов с namespace
            if kubectl api-resources | grep -wq "$res"; then
              kubectl get $res --all-namespaces -o yaml > \
                $BACKUP_DIR/$category/${res}-all-namespaces.yaml 2>/dev/null || true
            fi
          done
        done
        
        # Custom Resources (CRD)
        mkdir -p $BACKUP_DIR/custom
        kubectl get crd -o jsonpath='{.items[*].metadata.name}' | \
        while read crd; do
          kubectl get "$crd" --all-namespaces -o yaml > \
            $BACKUP_DIR/custom/${crd}.yaml 2>/dev/null || true
        done
        
        # Создать архив
        tar -czf /tmp/k8s-manifests-$(date +%Y%m%d).tar.gz -C $BACKUP_DIR .
        echo "/tmp/k8s-manifests-$(date +%Y%m%d).tar.gz"
      register: backup_result
      when: inventory_hostname in groups['master_nodes'][0]

    - name: Скачать архив на control node
      fetch:
        src: "{{ backup_result.stdout_lines[-1] }}"
        dest: "./"
        flat: yes
      when: inventory_hostname in groups['master_nodes'][0]
```

## Вариант 4: Для кластеров с ограниченными правами

```yaml
- name: Безопасный экспорт с проверками
  hosts: master_nodes
  vars:
    excluded_resources:
      - events
      - events.events.k8s.io
      - controllerrevisions
  tasks:
    - name: Экспорт с пропуском некоторых ресурсов
      shell: |
        OUTPUT_DIR="/tmp/k8s-export"
        mkdir -p $OUTPUT_DIR
        
        # Функция для проверки исключений
        is_excluded() {
          local resource="$1"
          for excluded in {{ excluded_resources | join(' ') }}; do
            if [[ "$resource" == "$excluded" ]]; then
              return 0
            fi
          done
          return 1
        }
        
        # Экспорт
        kubectl api-resources --verbs=list -o name | \
        while read resource; do
          if ! is_excluded "$resource"; then
            if kubectl api-resources | grep "^$resource\s" | grep -q "true"; then
              # Namespaced resources
              kubectl get "$resource" --all-namespaces -o yaml 2>/dev/null | \
              awk '/^---$/ {count++} count>1 {print} {if(count>1) print}' > \
                $OUTPUT_DIR/${resource//\//_}.yaml
            else
              # Cluster resources
              kubectl get "$resource" -o yaml 2>/dev/null > \
                $OUTPUT_DIR/${resource//\//_}.yaml
            fi
          fi
        done
        
        # Проверить размер файлов
        find $OUTPUT_DIR -name "*.yaml" -size +1M -exec ls -lh {} \;
        
        echo "Экспорт в: $OUTPUT_DIR"
      when: inventory_hostname in groups['master_nodes'][0]
```

## Важные замечания:

1. **Secrets**: Манифесты с секретами будут содержать base64-encoded данные. Будьте осторожны при хранении.

2. **Производительность**: Для больших кластеров лучше экспортировать ресурсы постепенно.

3. **Права доступа**: Убедитесь, что у сервисного аккаунта есть права на чтение всех ресурсов.

4. **Хранение**: Рассмотрите возможность шифрования архива перед сохранением.

5. **Версионность**: Добавьте дату в имя директории для отслеживания версий.

Эти подходы сохранят все манифесты в YAML-формате на локальном диске мастер-узла, откуда их можно будет скачать или обработать дальше.
