#### **Пример конфигурации keepalived для трех ЦОД**

В данной архитектуре:
- **ЦОД1** и **ЦОД2** содержат реальные серверы, на которые идет полезный трафик.
- **ЦОД3** используется только для арбитража (quorum), чтобы избежать split-brain, но не обслуживает реальный трафик.

##### **Общие принципы**
- Используем unicast-режим VRRP, чтобы корректно работать между разными площадками.
- В каждом конфиге указываем уникальный `unicast_src_ip` и список всех участников в `unicast_peer`.
- В каждом ЦОД назначаем приоритеты: основной (MASTER) — самый высокий, резервный — ниже, арбитр — самый низкий.
- Один и тот же `virtual_router_id` и VIP на всех площадках.

---

### **Конфигурация для ЦОД1 (MASTER)**

```
vrrp_instance VI_1 {
    state MASTER
    interface eth0
    virtual_router_id 51
    priority 150
    advert_int 1
    authentication {
        auth_type PASS
        auth_pass mysecret
    }
    unicast_src_ip 10.0.1.1
    unicast_peer {
        10.0.2.1    # IP keepalived во 2-м ЦОД
        10.0.3.1    # IP keepalived в 3-м ЦОД (арбитр)
    }
    virtual_ipaddress {
        10.0.0.100
    }
}
```

---

### **Конфигурация для ЦОД2 (BACKUP)**

```
vrrp_instance VI_1 {
    state BACKUP
    interface eth0
    virtual_router_id 51
    priority 140
    advert_int 1
    authentication {
        auth_type PASS
        auth_pass mysecret
    }
    unicast_src_ip 10.0.2.1
    unicast_peer {
        10.0.1.1    # IP keepalived в 1-м ЦОД
        10.0.3.1    # IP keepalived в 3-м ЦОД (арбитр)
    }
    virtual_ipaddress {
        10.0.0.100
    }
}
```

---

### **Конфигурация для ЦОД3 (АРБИТР)**

```
vrrp_instance VI_1 {
    state BACKUP
    interface eth0
    virtual_router_id 51
    priority 50
    advert_int 1
    authentication {
        auth_type PASS
        auth_pass mysecret
    }
    unicast_src_ip 10.0.3.1
    unicast_peer {
        10.0.1.1    # IP keepalived в 1-м ЦОД
        10.0.2.1    # IP keepalived во 2-м ЦОД
    }
    virtual_ipaddress {
        10.0.0.100
    }
    # На этом узле не поднимается VIP на интерфейсе (можно использовать nopreempt или скрипты для блокировки)
}
```

---

#### **Комментарии**
- **priority**: определяет, кто будет MASTER. Арбитр всегда с самым низким приоритетом.
- **unicast_src_ip** и **unicast_peer**: позволяют keepalived работать между разными площадками без multicast.
- **virtual_ipaddress**: один и тот же VIP на всех площадках, но реально поднимается только на активном.
- На арбитре (ЦОД3) можно добавить скрипт, который не позволит поднимать VIP, чтобы он участвовал только в голосовании.

---

#### **Рекомендации**
- Убедитесь, что между всеми тремя площадками есть L2/L3-связь для VRRP-пакетов.
- Используйте одинаковый `virtual_router_id` и пароль на всех узлах.
- Для арбитра используйте опцию `nopreempt` или скрипт, чтобы VIP не поднимался даже при получении MASTER-статуса.

---

**Такой подход обеспечивает отказоустойчивость и предотвращает split-brain при потере связи между двумя основными ЦОД.**