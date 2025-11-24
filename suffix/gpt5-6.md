Да. В Ansible есть “магические” переменные, которые дают путь к инвентарю и к проекту. Их можно использовать в любом месте, где работает Jinja2-шаблонизация (lookup, include_vars, vars_files, copy/src, template/src и т.д.).

Самые полезные:
- playbook_dir — абсолютный путь к каталогу, где лежит текущий плейбук.
- inventory_file — путь к файлу (или источнику) инвентаря, из которого пришёл текущий хост.
- inventory_dir — каталог, в котором находится inventory_file.
- ansible_inventory_sources — список всех источников инвентаря, если их несколько.

Примеры использования

- Надёжнее, чем относительные пути от CWD:
  - lookup:
    - "{{ lookup('ansible.builtin.file', playbook_dir ~ '/group_vars/group1/dev.yml') }}"
  - vars_files в плейбуке:
    - vars_files:
      - "{{ inventory_dir }}/group_vars/dev.yml"
  - include_vars:
    - - name: Load env vars
        ansible.builtin.include_vars:
          file: "{{ inventory_dir }}/envs/{{ env }}/vars.yml"
  - copy из каталога рядом с инвентарём:
    - - name: Ship config
        ansible.builtin.copy:
          src: "{{ inventory_dir }}/files/{{ inventory_hostname }}/app.conf"
          dest: /etc/app.conf

Полезные замечания
- Если инвентарь динамический или у вас несколько источников, inventory_file/inventory_dir могут отличаться по хостам. В таких случаях есть ansible_inventory_sources (список). Часто достаточно взять первый источник:
  - set_fact:
      inv_root: "{{ (inventory_file is defined) | ternary(inventory_dir, (ansible_inventory_sources | first | dirname)) }}"
- Для кода внутри роли удобнее role_path:
  - src: "{{ role_path }}/files/default.cfg"
- Чтобы не ловить “зависимость от того, откуда запущен ansible-playbook”, предпочитайте playbook_dir/inventory_dir вместо относительных путей.
- Файлы group_vars/host_vars автоматически подхватываются, если они лежат рядом с плейбуком или внутри каталога инвентаря. lookup('file', ...) нужен только когда вы осознанно читаете произвольный файл.

Если расскажете, как у вас устроена структура проекта (где лежит inventory, где файлы), подскажу более конкретный шаблон путей.
