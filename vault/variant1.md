Да. Если под «ЕЩЕЗ» вы имели в виду **TOTP**, то сделать схему без pipeline можно, но есть важная граница:

**Vault OSS умеет потребовать TOTP при логине, но не умеет нативно потребовать подтверждение второго пользователя для конкретной операции `write policy` или `write LDAP mapping`.** Login MFA, включая TOTP, доступен в Community Edition; step-up MFA и Control Groups для согласования конкретных операций — Enterprise. ([HashiCorp Developer][1])

Поэтому я вижу два варианта без pipeline.

## Вариант Б1 — два разных администратора с разделением полномочий

Создаём в AD:

```text
GG_VAULT_POLICY_ADMINS
GG_VAULT_MAPPING_ADMINS

GG_VAULT_PLATFORM_ADMINS

GG_VAULT_APP1_SECRET_ADMINS
GG_VAULT_APP1_SECRET_READERS

GG_VAULT_APP2_SECRET_ADMINS
GG_VAULT_APP2_SECRET_READERS
```

Получается такая модель:

| AD-группа                     | Что может                                                    |
| ----------------------------- | ------------------------------------------------------------ |
| `GG_VAULT_POLICY_ADMINS`      | создавать/изменять `secret-*` policies                       |
| `GG_VAULT_MAPPING_ADMINS`     | делать mapping AD-групп `GG_VAULT_*_SECRET_*` → Vault policy |
| `GG_VAULT_PLATFORM_ADMINS`    | эксплуатация Vault, без KV и ACL                             |
| `GG_VAULT_APP1_SECRET_ADMINS` | читать/менять только App1                                    |
| `GG_VAULT_APP2_SECRET_ADMINS` | читать/менять только App2                                    |

Например сотрудник **Alice** состоит только в:

```text
GG_VAULT_POLICY_ADMINS
```

а **Bob**:

```text
GG_VAULT_MAPPING_ADMINS
```

Alice получает примерно:

```hcl
path "sys/policies/acl/secret-*" {
    capabilities = ["create", "read", "update"]
}

path "kv/*" {
    capabilities = ["deny"]
}

path "auth/ldap/groups/*" {
    capabilities = ["deny"]
}
```

Vault поддерживает glob/prefix matching в ACL path, поэтому такую область можно ограничивать по naming convention. ([HashiCorp Developer][2])

Bob получает:

```hcl
path "auth/ldap/groups/GG_VAULT_*" {
    capabilities = ["create", "read", "update"]
}

path "sys/policies/acl/*" {
    capabilities = ["deny"]
}

path "kv/*" {
    capabilities = ["deny"]
}
```

При создании новой области:

```text
Нужно создать:

kv/app3/*
```

Alice создаёт:

```text
secret-app3-admin
secret-app3-reader
```

Например:

```hcl
# secret-app3-admin

path "kv/data/app3/*" {
    capabilities = [
        "create",
        "read",
        "update",
        "patch",
        "delete"
    ]
}
```

Но Alice **не может назначить эту policy никому**.

После этого Bob создаёт:

```text
GG_VAULT_APP3_SECRET_ADMINS
        ↓
secret-app3-admin

GG_VAULT_APP3_SECRET_READERS
        ↓
secret-app3-reader
```

LDAP group → policy mapping является штатным механизмом Vault. ([HashiCorp Developer][3])

То есть для первоначального создания доступа действительно нужны:

```text
Alice                     Bob
Policy Admin             Mapping Admin
   │                          │
   │ создаёт policy           │
   └──────────────┐           │
                  ▼           │
          secret-app3-admin   │
                  │           │
                  └───────────┤ назначает
                              ▼
                  GG_VAULT_APP3_SECRET_ADMINS
```

### Но у этой схемы есть недостаток

Она **не обеспечивает строгое правило “каждое изменение требует двоих”**.

После того как:

```text
secret-app3-admin
       ↓
GG_VAULT_APP3_SECRET_ADMINS
```

уже существует, Alice может одна изменить содержимое `secret-app3-admin`.

Причём Vault применит обновлённую policy сразу ко всем пользователям, которым она назначена. Endpoint создания и изменения policy один и тот же — `POST /sys/policies/acl/:name`. ([HashiCorp Developer][4])

Например Alice сможет заменить:

```hcl
path "kv/data/app3/*" {
    capabilities = ["read"]
}
```

на:

```hcl
path "kv/data/*" {
    capabilities = ["read"]
}
```

Сама Alice этот доступ не получит, если она **не входит ни в одну SECRET-группу**, но она сможет расширить доступ владельцам App3.

Поэтому это хорошее **Separation of Duties**, но не настоящий криптографический принцип «четырёх глаз».

---

# Вариант Б2 — два человека должны присутствовать для получения privileged session

Если принципиально нужен OSS и нет pipeline, я бы рассматривал именно этот вариант.

Создаём отдельную привилегированную AD-учётную запись:

```text
vault-acl-change
```

и AD-группу:

```text
GG_VAULT_SECURITY_CHANGE
```

Обычные сотрудники **не получают эту policy на свои персональные учётки**.

Схема:

```text
             AD account
          vault-acl-change
                 │
          password required
                 │
                 ▼
            Vault LDAP
                 │
          + TOTP required
                 │
                 ▼
       short-lived Vault token
                 │
        ┌────────┴─────────┐
        ▼                  ▼
sys/policies/acl/       auth/ldap/groups/
secret-*                GG_VAULT_SECRET_*
```

А теперь credential физически разделяется.

```text
Employee A
    │
    └── знает/вводит AD password

Employee B
    │
    └── хранит TOTP token
          ↓

только A + B вместе
          ↓
Vault login
          ↓
Security Change session
```

Vault Community поддерживает Login MFA с TOTP. ([HashiCorp Developer][1])

То есть:

```text
Alice вводит:

username: vault-acl-change
password: ***********

Vault:
"Введите TOTP"

Bob:
123456

            ↓

Vault выдаёт token
```

Это уже практически реализует двухчеловеческую процедуру.

## Я бы сделал для этого отдельный LDAP mount

Например обычные пользователи:

```text
auth/ldap/
```

а Security Change:

```text
auth/security-ldap/
```

Оба смотрят в один Active Directory.

Но у `security-ldap` задаём очень жёсткие token settings, например:

```text
token_ttl          = 5m
token_max_ttl      = 5m
token_num_uses     = 2
token_bound_cidrs  = <адрес admin workstation>
```

LDAP auth действительно позволяет задавать `token_ttl`, `token_max_ttl`, `token_num_uses` и привязку полученного token к CIDR. ([HashiCorp Developer][5])

Например один session-token разрешает всего две операции:

```text
операция #1:
POST /sys/policies/acl/secret-app3-admin

операция #2:
POST /auth/ldap/groups/GG_VAULT_APP3_SECRET_ADMINS
```

После этого token больше использовать нельзя.

Это уже довольно сильная конструкция:

```text
             Hardened Admin Workstation
                        │
                  Alice + Bob
                        │
            AD password + TOTP
                        │
                        ▼
              security-ldap/login
                        │
               5 minute token
                  max 2 uses
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
        create policy          create mapping
             │                     │
             └──────────┬──────────┘
                        ▼
                     finished
```

## Что разрешить этой специальной учётке

Например:

```hcl
# security-change.hcl

# Только policies для secret areas
path "sys/policies/acl/secret-*" {
    capabilities = ["create", "read", "update"]
}

# Только mappings для secret AD groups
path "auth/ldap/groups/GG_VAULT_SECRET_*" {
    capabilities = ["create", "read", "update"]
}

# Никакого чтения secrets
path "kv/*" {
    capabilities = ["deny"]
}

# Нельзя менять собственную security policy
path "sys/policies/acl/security-change" {
    capabilities = ["deny"]
}

# Нельзя менять mapping собственной AD-группы
path "auth/ldap/groups/GG_VAULT_SECURITY_CHANGE" {
    capabilities = ["deny"]
}
```

Я бы naming немного поменял, чтобы ACL проще ограничивались:

```text
GG_VAULT_SECRET_APP1_ADMINS
GG_VAULT_SECRET_APP1_READERS

GG_VAULT_SECRET_APP2_ADMINS
GG_VAULT_SECRET_APP2_READERS
```

Тогда privileged account получает доступ исключительно к:

```text
auth/ldap/groups/GG_VAULT_SECRET_*
```

и не может изменить:

```text
GG_VAULT_PLATFORM_ADMINS
GG_VAULT_POLICY_ADMINS
GG_VAULT_SECURITY_CHANGE
```

---

## Но TOTP — всё-таки не настоящий Four-Eyes Control

Это существенное различие.

Bob своим TOTP фактически подтверждает:

> «Разрешаю Alice войти в privileged session».

Но он **не подписывает конкретную операцию**:

```text
Создать именно такую policy:

path "kv/data/app3/*" {
    capabilities = ["read"]
}
```

После выдачи token Alice технически может отправить другой запрос.

То есть TOTP обеспечивает:

```text
Два человека нужны для получения administrative session
```

но не обеспечивает криптографически:

```text
Два человека независимо подтвердили
ИМЕННО ЭТОТ policy document.
```

Кроме того, в Vault audit trail основным субъектом будет `vault-acl-change`; Vault не сможет доказать, что TOTP ввёл именно Bob.

---

## Если требуется именно настоящее «2 approvals на каждое изменение»

Тогда **Vault OSS сам этого не умеет**.

В Vault Enterprise для этого существует **Control Group Authorization**: запрос блокируется, возвращается wrapping token, а заданное число авторизаторов должно подтвердить запрос; документация прямо приводит примеры, где для операции требуется несколько контролёров. ([HashiCorp Developer][6])

То есть концептуально:

```text
Alice:
   PUT policy
       │
       ▼
Vault: pending approval
       │
       ├──── Bob approves
       │
       └──── Charlie approves
                 │
                 ▼
             operation
              executes
```

Это именно то, что вы описываете.

### Что я бы выбрал для вашего OSS

Если **pipeline исключён**, а Enterprise покупать не планируется, я бы использовал комбинацию:

```text
Обычная эксплуатация:

GG_VAULT_PLATFORM_ADMINS
        ↓
Vault infrastructure
NO secrets
NO policies


Управление конкретными secrets:

GG_VAULT_SECRET_APP1_ADMINS
        ↓
kv/app1/*

GG_VAULT_SECRET_APP2_ADMINS
        ↓
kv/app2/*


Изменение ACL:

отдельная AD account
vault-acl-change

password → сотрудник A
TOTP     → сотрудник B

token TTL       = 5 min
token num uses  = 2
source IP       = hardened workstation

       ↓

sys/policies/acl/secret-*
auth/ldap/groups/GG_VAULT_SECRET_*

       ↓

NO ACCESS kv/*
```

И обязательно правило в AD:

> сотрудники, имеющие доступ к `vault-acl-change`, **не могут состоять в `GG_VAULT_SECRET_*` и не имеют права самостоятельно менять membership этих групп**.

Тогда даже security-конфигураторы смогут создавать права доступа, но **не смогут сами стать потребителями секретов** без участия ещё одного независимого администратора AD.

Если требование «два человека» у вас является именно compliance-требованием, а не просто защитой от случайной ошибки, я бы считал схему с разделённым password+TOTP **компенсирующим контролем**, но не полноценным Four-Eyes Authorization. Для настоящего технического enforcement нужен либо Vault Enterprise Control Groups, либо внешний PAM/approval-механизм.

[1]: https://developer.hashicorp.com/vault/docs/auth/login-mfa?utm_source=chatgpt.com "Set up login MFA | Vault | HashiCorp Developer"
[2]: https://developer.hashicorp.com/vault/docs/concepts/policies?utm_source=chatgpt.com "Policies | Vault | HashiCorp Developer"
[3]: https://developer.hashicorp.com/vault/docs/auth/ldap?utm_source=chatgpt.com "LDAP - Auth Methods | Vault | HashiCorp Developer"
[4]: https://developer.hashicorp.com/vault/api-docs/system/policies?utm_source=chatgpt.com "/sys/policies/ - HTTP API | Vault | HashiCorp Developer"
[5]: https://developer.hashicorp.com/vault/api-docs/auth/ldap?utm_source=chatgpt.com "LDAP - Auth Methods - HTTP API | Vault | HashiCorp Developer"
[6]: https://developer.hashicorp.com/vault/docs/enterprise/control-groups?utm_source=chatgpt.com "Use control groups for authorization | Vault | HashiCorp Developer"
