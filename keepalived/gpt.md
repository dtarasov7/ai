Да, конечно. IPVS (LVS) поддерживает три основных режима пересылки пакетов. DR (Direct Routing) — самый популярный из-за производительности, но не единственный.

Основные альтернативы:

### 1. NAT (Network Address Translation)
В этом режиме балансировщик (Master) работает как настоящий шлюз (NAT-роутер).

*   **Как это работает:**
    1. Клиент посылает запрос на VIP.
    2. Балансировщик принимает пакет, **меняет Destination IP** на IP одного из реальных серверов и отправляет ему.
    3. Реальный сервер обрабатывает запрос и отправляет ответ **обратно балансировщику** (шлюзом по умолчанию на серверах должен быть балансировщик!).
    4. Балансировщик меняет Source IP с адреса реального сервера на VIP и отдает ответ клиенту.

*   **Плюсы:**
    *   Реальные сервера могут быть в любой подсети (не обязательно в одном L2-сегменте с VIP).
    *   Не нужно настраивать подавление ARP и `lo` интерфейсы на серверах.
    *   Можно делать проброс портов (VIP:80 -> Server:8080).

*   **Минусы:**
    *   **Узкое место:** Вся нагрузка (и входящая, и **исходящая**) проходит через CPU балансировщика. Для тяжелого контента (видео, большие файлы) это станет проблемой.

*   **Конфиг (`lb_kind NAT`):**
    ```nginx
    virtual_server 10.0.0.100 80 {
        lb_kind NAT
        ...
    }
    ```
    *Важно:* На реальных серверах Default Gateway должен указывать на внутренний IP балансировщика.

### 2. TUN (IP Tunneling / IPIP)
Используется для гео-распределенных кластеров, когда сервера находятся в разных дата-центрах или разных сетях, где L2-связность невозможна.

*   **Как это работает:**
    Балансировщик инкапсулирует исходный IP-пакет внутри другого IP-пакета (туннель) и отправляет его реальному серверу. Сервер распаковывает пакет и отвечает клиенту напрямую (как в DR).

*   **Плюсы:**
    *   Сервера могут быть где угодно в интернете.
    *   Ответ уходит напрямую клиенту (высокая скорость отдачи).

*   **Минусы:**
    *   Все участники должны поддерживать IP-туннелирование.
    *   Меньший MTU из-за заголовков туннеля (возможна фрагментация).
    *   Сложная настройка сети.

*   **Конфиг (`lb_kind TUN`):**
    ```nginx
    virtual_server 10.0.0.100 80 {
        lb_kind TUN
        ...
    }
    ```

### Сравнение режимов

| Характеристика | DR (Direct Routing) | NAT (Masquerading) | TUN (Tunneling) |
| :--- | :--- | :--- | :--- |
| **Производительность** | **Очень высокая** | Средняя / Низкая | Высокая |
| **Узкое место** | Нет (ответы идут мимо Master) | **CPU Master** (весь трафик через него) | Нет |
| **Требования к сети** | Все в одной L2-сети | Можно разные сети | Любая IP-связность (интернет) |
| **Сложность настройки** | Средняя (ARP-проблемы) | Низкая (просто шлюз) | Высокая (туннели) |
| **Изменение порта** | Нет (80 -> 80) | **Да** (80 -> 8080) | Нет |

### Рекомендация
Оставайтесь на **DR (Direct Routing)**, если все 4 сервера стоят рядом (в одной локальной сети). Это стандарт де-факто для высоконагруженных систем.
Используйте **NAT** только если вам нужно менять порты (mapping) или если вы не можете менять настройки ARP/сети на серверах.

Проверка “живости” делается **двумя разными механизмами keepalived**, и важно их не путать: (1) VRRP решает, кто держит VIP (MASTER), (2) healthcheck’и IPVS решают, каким real server’ам можно отдавать трафик. [keepalived](https://www.keepalived.org/pdf/UserGuide.pdf)

## 1) Проверка real servers (192.168.2.11–14)
Это делается в блоках `real_server` внутри `virtual_server` с помощью встроенных healthchecker’ов keepalived: `TCP_CHECK`, `HTTP_GET` (и др.). [opentodo](https://opentodo.net/2012/04/load-balancing-with-ipvs-keepalived/)

- **Если узел выключен/порт недоступен**, проверка не сможет установить соединение, и keepalived уберет этот `real_server` из таблицы IPVS (перестанет назначать на него новые соединения). [access.redhat](https://access.redhat.com/solutions/4011251)
- **Если nginx “жив”, но вернул не то**, `HTTP_GET` позволяет проверять HTTP-статус (например, 200), т.е. контролировать не просто “порт слушает”, а “сервис отвечает корректно”. [manpages.ubuntu](https://manpages.ubuntu.com/manpages/xenial/man5/keepalived.conf.5.html)

Пример для порта 443 (просто проверить TCP-рукопожатие):
```conf
real_server 192.168.2.12 443 {
  weight 1
  TCP_CHECK {
    connect_timeout 2
  }
}
```
`TCP_CHECK` проверяет возможность TCP-соединения, а параметры вроде `connect_timeout`, `nb_get_retry`, `delay_before_retry` задают таймаут и поведение повторов. [keepalived](https://www.keepalived.org/pdf/UserGuide.pdf)

Пример для HTTP (80) с проверкой кода:
```conf
real_server 192.168.2.12 80 {
  weight 1
  HTTP_GET {
    url { path /healthz status_code 200 }
    connect_timeout 2
    nb_get_retry 2
    delay_before_retry 1
  }
}
```
`HTTP_GET` делает HTTP-запрос и считает real server “здоровым” при ожидаемом статусе (обычно 2xx). [manpages.ubuntu](https://manpages.ubuntu.com/manpages/xenial/man5/keepalived.conf.5.html)

Для нескольких портов (80/443/8443/6443) вы обычно описываете либо:
- один `virtual_server VIP 80` и в нем `real_server ... 80`, второй `virtual_server VIP 443` и т.д., либо
- используете несколько `virtual_server` блоков по портам. [manpages.ubuntu](https://manpages.ubuntu.com/manpages/xenial/man5/keepalived.conf.5.html)

## 2) Проверка “самого директора” (кто держит VIP)
Это уже VRRP-часть: если текущий MASTER умер/потерял интерфейс/скрипт “упал”, VIP переедет на другой узел. Для этого используют `track_interface` и/или `track_script`/`vrrp_script`, чтобы понижать приоритет MASTER при проблемах (например, если локальный nginx не работает, или нет маршрута). [forge.puppet](https://forge.puppet.com/modules/puppet/keepalived/readme)

Типовой паттерн: “если на MASTER упал nginx — отдай VIP другому”, делается через `track_script`, который проверяет локальный порт/процесс, и при неуспехе уменьшает `priority`. [redhat](https://www.redhat.com/en/blog/advanced-keepalived)

## Важный нюанс именно в вашей схеме (nginx на 192.168.2.11–14)
У вас 192.168.2.11–14 одновременно:
- real servers для IPVS (получают клиентский трафик на VIP),
- и HTTP-proxy до 192.168.3.31–33.

Поэтому часто делают **двухуровневую проверку**:
- IPVS healthcheck проверяет, что nginx на `lbN` принимает вход на нужный порт (80/443/8443/6443). [manpages.ubuntu](https://manpages.ubuntu.com/manpages/xenial/man5/keepalived.conf.5.html)
- Дополнительно можно сделать `HTTP_GET` на `lbN`, который внутри возвращает 200 только если upstream’ы 192.168.3.31–33 реально доступны (например, через `location /healthz { proxy_pass ...; }`). Это уже прикладная логика, но технически реализуется тем же `HTTP_GET`. [opentodo](https://opentodo.net/2012/04/load-balancing-with-ipvs-keepalived/)

Если хотите — напишу пример `keepalived.conf` именно под ваш набор портов (80/443/8443/6443) и с рекомендацией, какие проверки разумнее ставить на каждый порт (TCP_CHECK vs HTTP_GET/SSL_GET) и как быстро “выкидывать” упавший узел из ротации.





Ниже — рабочий “полный” пример `keepalived.conf` для **4 узлов** в схеме **LVS-DR (Direct Routing)** с проверкой доступности nginx на портах **80/443/8443/6443**. Важно: keepalived умеет проверять реальный сервер через `TCP_CHECK`, `HTTP_GET`, `SSL_GET`; для 443/8443/6443 обычно надежнее начинать с `TCP_CHECK` (порт слушает), а если нужно именно “nginx отвечает HTTP-кодом”, используйте `HTTP_GET`/`SSL_GET` (и отдавайте 200 на `/healthz`). Синтаксис блоков `virtual_server`, `real_server`, `TCP_CHECK`, `HTTP_GET`, `SSL_GET` описан в manpage keepalived.conf  и в примерах healthcheck’ов. [keepalived.readthedocs](http://keepalived.readthedocs.io/en/latest/case_study_healthcheck.html)

## Входные данные (ваши)
- VIP: `192.168.2.100/24`
- Узлы (они же real servers): `192.168.2.11-14`
- Интерфейс: `eth0` (переименуйте под себя)
- Алгоритм: `rr`
- Режим: `lb_kind DR`

***

## 0) Обязательная системная часть для DR (на ВСЕХ 4 узлах)
Это не часть keepalived.conf, но без этого DR обычно “стреляет себе в ногу” ARP-ом.

1) VIP на loopback:
```bash
ip addr add 192.168.2.100/32 dev lo label lo:vip
```

2) ARP suppression (пример через sysctl):
```bash
sysctl -w net.ipv4.conf.all.arp_ignore=1
sysctl -w net.ipv4.conf.all.arp_announce=2
sysctl -w net.ipv4.conf.default.arp_ignore=1
sysctl -w net.ipv4.conf.default.arp_announce=2
sysctl -w net.ipv4.conf.eth0.arp_ignore=1
sysctl -w net.ipv4.conf.eth0.arp_announce=2
```
(Зафиксируйте в `/etc/sysctl.conf`.)

***

## 1) Общий шаблон keepalived.conf (одинаковый на всех, кроме VRRP)
Файл: `/etc/keepalived/keepalived.conf`

### Вариант проверки портов
- Для **80**: `HTTP_GET` (проверяем, что nginx реально отдает 200).
- Для **443/8443/6443**: `TCP_CHECK` (проверяем, что порт слушает).
  - Если у вас на 443/8443 есть HTTPS с валидным ответом 200 на `/healthz`, можно заменить `TCP_CHECK` на `SSL_GET` (он делает HTTPS-проверку). [manpages.ubuntu](https://manpages.ubuntu.com/manpages/xenial/man5/keepalived.conf.5.html)

Ниже конфиг именно в таком, максимально “живучем” варианте.

***

## lb1: 192.168.2.11 (MASTER, priority 100)

```conf
global_defs {
  router_id LB1
}

vrrp_instance VI_1 {
  state MASTER
  interface eth0
  virtual_router_id 51
  priority 100
  advert_int 1

  authentication {
    auth_type PASS
    auth_pass supersecret
  }

  virtual_ipaddress {
    192.168.2.100/24 dev eth0 label eth0:vip
  }
}

# --- VIP:80 ---
virtual_server 192.168.2.100 80 {
  delay_loop 3
  lb_algo rr
  lb_kind DR
  protocol TCP

  real_server 192.168.2.11 80 {
    weight 1
    HTTP_GET {
      url { path /healthz status_code 200 }
      connect_timeout 2
      nb_get_retry 2
      delay_before_retry 1
    }
  }
  real_server 192.168.2.12 80 { weight 1 HTTP_GET { url { path /healthz status_code 200 } connect_timeout 2 nb_get_retry 2 delay_before_retry 1 } }
  real_server 192.168.2.13 80 { weight 1 HTTP_GET { url { path /healthz status_code 200 } connect_timeout 2 nb_get_retry 2 delay_before_retry 1 } }
  real_server 192.168.2.14 80 { weight 1 HTTP_GET { url { path /healthz status_code 200 } connect_timeout 2 nb_get_retry 2 delay_before_retry 1 } }
}

# --- VIP:443 ---
virtual_server 192.168.2.100 443 {
  delay_loop 3
  lb_algo rr
  lb_kind DR
  protocol TCP

  real_server 192.168.2.11 443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
  real_server 192.168.2.12 443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
  real_server 192.168.2.13 443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
  real_server 192.168.2.14 443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
}

# --- VIP:8443 ---
virtual_server 192.168.2.100 8443 {
  delay_loop 3
  lb_algo rr
  lb_kind DR
  protocol TCP

  real_server 192.168.2.11 8443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
  real_server 192.168.2.12 8443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
  real_server 192.168.2.13 8443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
  real_server 192.168.2.14 8443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
}

# --- VIP:6443 ---
virtual_server 192.168.2.100 6443 {
  delay_loop 3
  lb_algo rr
  lb_kind DR
  protocol TCP

  real_server 192.168.2.11 6443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
  real_server 192.168.2.12 6443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
  real_server 192.168.2.13 6443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
  real_server 192.168.2.14 6443 { weight 1 TCP_CHECK { connect_timeout 2 retry 2 delay_before_retry 1 } }
}
```

Параметры `connect_timeout`, `retry`, `delay_before_retry` и блоки `TCP_CHECK/HTTP_GET` — это штатные опции keepalived healthchecker’ов. [manpages.ubuntu](https://manpages.ubuntu.com/manpages/xenial/man5/keepalived.conf.5.html)

***

## lb2: 192.168.2.12 (BACKUP, priority 99)
Весь файл **один-в-один**, кроме `router_id/state/priority`:

```conf
global_defs { router_id LB2 }

vrrp_instance VI_1 {
  state BACKUP
  interface eth0
  virtual_router_id 51
  priority 99
  advert_int 1
  authentication { auth_type PASS auth_pass supersecret }
  virtual_ipaddress { 192.168.2.100/24 dev eth0 label eth0:vip }
}

# дальше все virtual_server блоки как на lb1 (80/443/8443/6443) без изменений
```

***

## lb3: 192.168.2.13 (BACKUP, priority 98)

```conf
global_defs { router_id LB3 }

vrrp_instance VI_1 {
  state BACKUP
  interface eth0
  virtual_router_id 51
  priority 98
  advert_int 1
  authentication { auth_type PASS auth_pass supersecret }
  virtual_ipaddress { 192.168.2.100/24 dev eth0 label eth0:vip }
}

# дальше все virtual_server блоки как на lb1
```

***

## lb4: 192.168.2.14 (BACKUP, priority 97)

```conf
global_defs { router_id LB4 }

vrrp_instance VI_1 {
  state BACKUP
  interface eth0
  virtual_router_id 51
  priority 97
  advert_int 1
  authentication { auth_type PASS auth_pass supersecret }
  virtual_ipaddress { 192.168.2.100/24 dev eth0 label eth0:vip }
}

# дальше все virtual_server блоки как на lb1
```

***

## Важные замечания (чтобы не было “почему 80 проверяется, а 443 нет”)
- `HTTP_GET` проверяет **HTTP** и ожидаемый `status_code`; для него нужен URL/путь, который реально отдает 200. [manpages.ubuntu](https://manpages.ubuntu.com/manpages/xenial/man5/keepalived.conf.5.html)
- Для HTTPS-уровня есть `SSL_GET` (проверка через TLS), он описан в примерах keepalived healthcheck  и в синопсисе/мане. [keepalived.readthedocs](http://keepalived.readthedocs.io/en/latest/case_study_healthcheck.html)
- Для 6443 часто это kube-apiserver (не nginx) и HTTP-статусы/путь могут быть специфичны; поэтому `TCP_CHECK` — самый универсальный “порт жив” вариант. [manpages.ubuntu](https://manpages.ubuntu.com/manpages/xenial/man5/keepalived.conf.5.html)

Если скажете, что именно слушает 6443/8443 (nginx stream? kube-apiserver? какое `/healthz` есть на 443/8443), я адаптирую проверки: сделаю `SSL_GET` на 443/8443 и (при желании) `HTTP_GET` на 6443 с правильным path/status.


Да, это **не сломает** доступ к серверам по их “основным” IP (например, SSH на `192.168.2.11–14`). Эти sysctl’ы меняют в основном поведение **ARP** (кто и как отвечает на ARP-запросы), а не маршрутизацию TCP/SSH как таковую. [kb.linuxvirtualserver](http://kb.linuxvirtualserver.org/wiki/Using_arp_announce/arp_ignore_to_disable_ARP)

## Что именно меняется
- `arp_ignore=1` заставляет ядро отвечать на ARP-запрос **только если запрашиваемый IP назначен на интерфейсе, на который пришел ARP-запрос** (это как раз уменьшает ARP-flux). [kb.linuxvirtualserver](http://kb.linuxvirtualserver.org/wiki/Using_arp_announce/arp_ignore_to_disable_ARP)
- `arp_announce=2` заставляет ядро “аккуратнее” выбирать исходный IP для ARP-объявлений/запросов и стараться использовать адрес, подходящий для подсети исходящего интерфейса. [kb.linuxvirtualserver](http://kb.linuxvirtualserver.org/wiki/Using_arp_announce/arp_ignore_to_disable_ARP)

Это нужно в LVS-DR, чтобы real servers **не отвечали ARP’ом за VIP** (VIP у вас на loopback), а отвечал только текущий MASTER с VIP на `eth0`. [docs.redhat](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/5/html/virtual_server_administration/s1-lvs-direct-vsa)

## Почему SSH останется рабочим
Когда вы подключаетесь по SSH на `192.168.2.11`, клиент сначала делает ARP “кто имеет 192.168.2.11?”, и сервер `192.168.2.11` ответит нормально, потому что этот IP действительно назначен на `eth0` (входящий интерфейс совпадает). [kb.linuxvirtualserver](http://kb.linuxvirtualserver.org/wiki/Using_arp_announce/arp_ignore_to_disable_ARP)
То есть правило “отвечать только за адреса этого интерфейса” как раз **помогает**, а не мешает, в типичной одноинтерфейсной схеме. [chrisdietri](https://chrisdietri.ch/post/preventing-arp-flux-on-linux/)

## Когда могут быть сюрпризы
Проблемы обычно возникают не с SSH, а если сервер **многоинтерфейсный** (eth0/eth1, bonding/VLAN, VRF) и ARP-запросы приходят не на тот интерфейс, где висит нужный IP — тогда `arp_ignore=1` может “вежливо промолчать”, и сосед не узнает MAC. [docs.huihoo](https://docs.huihoo.com/hpc-cluster/linux-virtual-server/HOWTO/LVS-HOWTO.arp_problem.html)
В таком случае обычно настраивают `arp_ignore/arp_announce` **на конкретном интерфейсе**, который смотрит в VIP-сеть (и/или приводят адресацию в порядок). [docs.huihoo](https://docs.huihoo.com/hpc-cluster/linux-virtual-server/HOWTO/LVS-HOWTO.arp_problem.html)

Если у вас у каждого `lbN` один интерфейс в `192.168.2.0/24`, то можно считать, что SSH и прочий доступ по `192.168.2.11–14` будет работать как раньше.


Если контейнеры работают в обычном Docker-режиме (bridge `docker0`, отдельные network namespaces), то эти `arp_ignore/arp_announce` **не мешают** ни SSH на хост (`192.168.2.11–14`), ни работе контейнеров “внутри” — потому что параметры настраиваются на **хостовом** сетевом стеке и в основном влияют на то, как хост отвечает на ARP за “чужие” адреса/интерфейсы. [kb.linuxvirtualserver](http://kb.linuxvirtualserver.org/wiki/Using_arp_announce/arp_ignore_to_disable_ARP)

## Что реально изменится при Docker
- Типичный эффект от `arp_ignore=1` на `eth0`: хост перестанет отвечать на ARP-запросы по адресам, которые принадлежат **другим интерфейсам** (например `docker0`), если запрос пришел на `eth0`. Это как раз “лечит” ситуации, когда `docker0`-адрес случайно начинает быть “виден” снаружи (ARP flux/weak host model). [github](https://github.com/moby/moby/issues/31448)
- Для SSH на `192.168.2.11` это не проблема: IP `192.168.2.11` висит на `eth0`, ARP-запрос приходит на `eth0`, хост ответит нормально. [kb.linuxvirtualserver](http://kb.linuxvirtualserver.org/wiki/Using_arp_announce/arp_ignore_to_disable_ARP)

## Когда Docker может стать проблемой
Проблемы возможны, если вы используете контейнеры, которые **выводятся в L2-сеть как отдельные хосты**, например:
- `macvlan/ipvlan` (контейнеры получают IP из `192.168.2.0/24` и “живут” рядом с хостом на одном физическом интерфейсе),
- контейнеры/VM через Linux bridge (br0), SR-IOV, сложные bonding/VLAN схемы.

В таких вариантах ARP-поведение становится тоньше: вы можете случайно добиться, что хост перестанет отвечать не только за VIP (что нужно), но и начнет иначе отвечать/анонсировать адреса на “соседних” интерфейсах, и это уже влияет на доступность “из LAN”. Общая логика `arp_ignore`: отвечать только если адрес действительно “на этом интерфейсе”, и это может быть неожиданно, если адреса/подсети пересекаются или интерфейсов много. [netbeez](https://netbeez.net/blog/avoiding-arp-flux-in-multi-interface-linux-hosts/)

## Практический совет для LVS-DR + Docker
Чтобы снизить риск побочных эффектов, часто делают так:
- ставят `arp_ignore/arp_announce` **точечно** только на интерфейсы, которые смотрят в VIP-сеть (например, `eth0` и `lo`), вместо `all/default`, или хотя бы проверяют после изменений `arping`/`ip neigh` с соседней машины. Поведение этих параметров именно такое: они управляют тем, на каких интерфейсах ядро отвечает на ARP и какие адреса использует в ARP-объявлениях. [chrisdietri](https://chrisdietri.ch/post/preventing-arp-flux-on-linux/)
- если используете `macvlan/ipvlan` и контейнеры с адресами из `192.168.2.0/24`, скажите — там можно дать более аккуратный набор sysctl (и проверить, что контейнеры не потеряют L2-доступ).

Уточните, пожалуйста: контейнеры у вас в стандартном `docker0` (172.x/10.x), или вы используете `macvlan/ipvlan`/bridge с IP из `192.168.2.0/24`?