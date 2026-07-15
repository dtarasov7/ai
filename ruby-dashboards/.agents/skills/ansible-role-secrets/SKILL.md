---
name: ansible-role-secrets
description: Use when creating or modifying Ansible roles that handle passwords, TLS certificates, HashiCorp Vault, or local certificate files.
---

# Skill: Ansible role secrets and certificates pattern

When generating an Ansible role, implement passwords and certificates so that the same role can work both with HashiCorp Vault and without Vault.

Use the current role name as the variable prefix:

<role_prefix>_...

## Passwords

Passwords must be defined through variables and be overrideable from inventory, `group_vars`, `host_vars`, or `defaults`.

Provide a Vault-based form and a non-Vault form:

```yaml
<role_prefix>_hashi_vault_path_password: "secret=opensource-{{ project_name }}/data/{{ host_land }}/<role_prefix>"

# Use when password is stored in Vault:
# <role_prefix>_password_<user_name>: "{{ lookup('hashi_vault', <role_prefix>_hashi_vault_path_password + ':<user_name>') }}"

# Use when password is stored in inventory or vars:
<role_prefix>_password_<user_name>: "xxxxx"
```

Do not put password lookup logic directly into task files.

## Certificates

Certificates must support two sources:

```yaml
<role_prefix>_hashi_vault_path: ""
```

means certificates are read from local files.

```yaml
<role_prefix>_hashi_vault_path: "secret=..."
```

means certificates are read from Vault.

The source-selection logic must be implemented in variables, not in tasks.

Use this structure in `defaults/main.yml`:

```yaml
<role_prefix>_hashi_vault_path: ""
# <role_prefix>_hashi_vault_path: "secret=opensource-{{ project_name }}/data/cert/{{ inventory_hostname_short | lower }}:"
# <role_prefix>_hashi_vault_path_root: "secret=opensource-{{ project_name }}/data/cert/root:"

<role_prefix>_hashi_vault_path_certificates: "{{ <role_prefix>_hashi_vault_path }}"

<role_prefix>_certfile: "{{ inventory_hostname_short | lower }}.cer"
<role_prefix>_cerkeyfile: "{{ inventory_hostname_short | lower }}.key"
<role_prefix>_cacertfile: "root.cer"

<role_prefix>_local_certs_path: "./certs/"

<role_prefix>_certificates:
  - name: "{{ <role_prefix>_cacertfile | basename }}"
    content: >-
      {% if <role_prefix>_hashi_vault_path_certificates | length > 0 %}
      {{ lookup('hashi_vault', <role_prefix>_hashi_vault_path_root + (<role_prefix>_cacertfile | basename)) }}
      {% else %}
      {{ lookup('file', <role_prefix>_local_certs_path + <role_prefix>_cacertfile) }}
      {% endif %}

  - name: "{{ <role_prefix>_certfile | basename }}"
    content: >-
      {% if <role_prefix>_hashi_vault_path_certificates | length > 0 %}
      {{ lookup('hashi_vault', <role_prefix>_hashi_vault_path_certificates + (<role_prefix>_certfile | basename)) }}
      {% else %}
      {{ lookup('file', <role_prefix>_local_certs_path + <role_prefix>_certfile) }}
      {% endif %}

  - name: "{{ <role_prefix>_cerkeyfile | basename }}"
    content: >-
      {% if <role_prefix>_hashi_vault_path_certificates | length > 0 %}
      {{ lookup('hashi_vault', <role_prefix>_hashi_vault_path_certificates + (<role_prefix>_cerkeyfile | basename)) }}
      {% else %}
      {{ lookup('file', <role_prefix>_local_certs_path + <role_prefix>_cerkeyfile) }}
      {% endif %}

<role_prefix>_https: true
<role_prefix>_no_log: true
```

## Tasks

Certificate installation must be placed in a separate task file, for example `tasks/ssl.yml`.

In `tasks/main.yml`:

```yaml
- name: main.yml - Import ssl tasks
  include_tasks:
    file: ssl.yml
    apply:
      tags:
        - certs
  when: 
    - <role_prefix>_https | bool
    - <role_prefix>_certificates | length > 0
  tags:
    - certs
```

In `tasks/ssl.yml`, tasks must use the already prepared list `<role_prefix>_certificates`.

Do not repeat Vault/local selection logic here.

```yaml
- name: "copying cert, key, cacert to {{ <role_prefix>_dir }}/ssl"
  copy:
    content: "{{ item.content }}"
    dest: "{{ <role_prefix>_dir }}/ssl/{{ item.name }}"
    owner: "{{ <role_prefix>_user }}"
    group: "{{ <role_prefix>_group }}"
    mode: "0600"
    backup: true
  loop: "{{ <role_prefix>_certificates }}"
  loop_control:
    label: "{{ item.name }}"
  notify: <role_prefix>_restart
  no_log: "{{ <role_prefix>_no_log }}"
  when: <role_prefix>_https
```

## Pre-checks

Before installing certificates, validate that certificate content is available In `tasks/pre-req.yml`

```yaml
- name: Check Hashicorp Vault Token
  assert:
    that:
      - <role_prefix>_certificates[0]
    fail_msg: "Invalid Vault token or path not found"
    success_msg: "OK"
  run_once: true
  no_log: "{{ <role_prefix>_no_log }}"
  when:
    - <role_prefix>_https | bool
    - <role_prefix>_hashi_vault_path_certificates | length > 0
  tags:
    - certs

- name: find cert files in path
  assert:
    that:
      - item.content | length > 0
    fail_msg: "File path not found"
    success_msg: "File path found"
    quiet: true
  loop: "{{ (<role_prefix>_https | bool) | ternary(<role_prefix>_certificates, []) }}"
  loop_control:
    label: "{{ item.name }}"
  no_log: "{{ <role_prefix>_no_log }}"
  when:
    - <role_prefix>_https | bool
    - <role_prefix>_certificates | length > 0
  tags:
    - certs
```

## Core rule

Switching between Vault and non-Vault modes must require only variable changes, not task changes.

