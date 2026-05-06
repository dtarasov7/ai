Да. Варианты **4** и **7** — это keepalived как управляющий слой над **LVS/IPVS**: keepalived описывает virtual service, real servers, health-check’и, а ядро Linux через IPVS принимает решение, на какой real server отправить конкретный поток/пакет.

Keepalived в конфигурации `virtual_server` поддерживает `lb_algo`, `lb_kind NAT|DR|TUN`, `protocol TCP|UDP`, `persistence_timeout`, `sorry_server` и набор health-check’ов для `real_server`, включая `TCP_CHECK`, `HTTP_GET`, `SSL_GET`, `SMTP_CHECK`, `DNS_CHECK`, `MISC_CHECK`. ([keepalived.org][1])

---

# 4. Keepalived + LVS/IPVS как L4-балансировщик

Общая схема:

```text
client
  |
  v
VIP:PORT на LVS director
  |
  v
IPVS выбирает real_server
  |
  +--> node1:PORT
  +--> node2:PORT
  +--> node3:PORT
```

Keepalived здесь делает несколько вещей:

1. создаёт/обновляет правила IPVS;
2. проверяет состояние real server’ов;
3. удаляет backend из IPVS pool, если check failed;
4. возвращает backend обратно, если check снова успешен;
5. может держать VIP через VRRP, чтобы сам LVS director был отказоустойчивым.

Пример:

```conf
vrrp_instance VI_1 {
    state MASTER
    interface eth0
    virtual_router_id 51
    priority 100
    advert_int 1

    virtual_ipaddress {
        10.0.0.100/24
    }
}

virtual_server 10.0.0.100 443 {
    delay_loop 5
    lb_algo wlc
    lb_kind NAT
    protocol TCP

    real_server 10.0.1.11 443 {
        weight 10
        TCP_CHECK {
            connect_port 443
            connect_timeout 2
        }
    }

    real_server 10.0.1.12 443 {
        weight 20
        TCP_CHECK {
            connect_port 443
            connect_timeout 2
        }
    }
}
```

Здесь `delay_loop 5` означает периодичность health-check’а, `lb_algo wlc` — алгоритм выбора backend’а, `lb_kind NAT` — способ доставки трафика, а `weight` влияет на долю трафика.

---

# Как принимается решение, можно ли отправлять трафик на узел

Есть несколько уровней принятия решения.

## 1. Узел присутствует в IPVS pool или удалён из него

Это базовый уровень.

Если health-check успешен, keepalived держит real server в IPVS-таблице. Если check не проходит, keepalived удаляет этот real server из пула. Документация keepalived прямо описывает поведение health-check’ов: если проверка не проходит, сервер удаляется из server pool. ([keepalived.org][2])

То есть IPVS не “думает”, жив ли backend. Для IPVS backend либо есть в таблице, либо его нет.

Проверить можно так:

```bash
ipvsadm -Ln
```

Пример:

```text
TCP  10.0.0.100:443 wlc
  -> 10.0.1.11:443  Masq  10  0  123
  -> 10.0.1.12:443  Masq  20  0  240
```

Если `10.0.1.11` выпал из health-check’а, он исчезнет из списка.

---

## 2. Тип health-check’а

Keepalived поддерживает разные проверки. Выбор check’а — главный способ решить, “можно ли сюда слать трафик”.

### TCP_CHECK

Проверяет, что TCP-порт принимает соединение.

```conf
real_server 10.0.1.11 443 {
    weight 1
    TCP_CHECK {
        connect_port 443
        connect_timeout 2
        retry 3
        delay_before_retry 1
    }
}
```

Это проверяет только уровень:

```text
порт открыт / порт не открыт
```

Подходит для:

```text
PostgreSQL
Redis
Kafka
RabbitMQ
generic TCP service
TLS passthrough
```

Но важное ограничение: TCP-порт может быть открыт, а приложение внутри уже не готово обслуживать запросы.

Например:

```text
nginx слушает 443 → TCP_CHECK успешен
но upstream’ы внутри nginx мертвы → реальные запросы падают
```

---

### HTTP_GET / SSL_GET

Проверяет HTTP endpoint.

```conf
real_server 10.0.1.11 8443 {
    weight 1

    SSL_GET {
        url {
            path /health
            status_code 200
        }
        connect_port 8443
        connect_timeout 2
        nb_get_retry 3
        delay_before_retry 1
    }
}
```

Документация описывает `HTTP_GET` как проверку HTTP URL, а `SSL_GET` — аналогичную проверку через SSL/TLS. Также можно проверять `status_code` или digest ответа. ([keepalived.org][2])

Это уже лучше, потому что можно проверять не просто порт, а состояние приложения:

```text
GET /health → 200 OK
```

Примеры:

```text
/health
/ready
/livez
/api/system/lbstatus
```

Практически лучше использовать именно **readiness**, а не liveness.

То есть:

```text
/livez    — процесс жив
/ready    — процесс готов принимать трафик
```

Для балансировки нужен `/ready`.

---

### MISC_CHECK

Самый гибкий вариант. Keepalived запускает пользовательский скрипт на director’е. По документации, `MISC_CHECK` позволяет запускать user-defined script, результат которого используется как health-check. ([keepalived.org][2])

Пример:

```conf
real_server 10.0.1.11 5432 {
    weight 1

    MISC_CHECK {
        misc_path "/usr/local/bin/check_pg_primary.sh 10.0.1.11"
        misc_timeout 3
    }
}
```

Скрипт может проверять что угодно:

```bash
#!/bin/bash

HOST="$1"

pg_isready -h "$HOST" -p 5432 -t 2 >/dev/null 2>&1 || exit 1

ROLE=$(psql -h "$HOST" -U monitor -tAc "select pg_is_in_recovery()" 2>/dev/null)

# false = primary, true = replica
[ "$ROLE" = "f" ] && exit 0 || exit 1
```

Такой check отвечает не на вопрос “жив ли PostgreSQL”, а на вопрос:

```text
является ли этот узел primary и можно ли на него слать write-трафик
```

Это очень важное отличие.

---

## 3. Вес узла

Даже если узел healthy, на него можно слать разную долю трафика.

```conf
real_server 10.0.1.11 443 {
    weight 10
}

real_server 10.0.1.12 443 {
    weight 20
}
```

При `wrr` или `wlc` второй узел будет получать больше трафика.

Это полезно, если узлы разные:

```text
node1: 4 CPU, 8 GB RAM  → weight 10
node2: 8 CPU, 16 GB RAM → weight 20
```

Или при постепенном вводе узла:

```text
new node → weight 1
после проверки → weight 10
```

---

## 4. Алгоритм балансировки

После того как список eligible backend’ов определён, IPVS выбирает конкретный узел по `lb_algo`.

Частые варианты:

```text
rr    round robin
wrr   weighted round robin
lc    least connections
wlc   weighted least connections
sh    source hashing
dh    destination hashing
lblc  locality-based least connection
```

Примеры выбора:

```conf
lb_algo rr
```

Просто по кругу.

```conf
lb_algo wlc
```

С учётом веса и количества активных соединений. Это часто хороший default для TCP-сервисов.

```conf
lb_algo sh
```

Source hashing: один и тот же клиент чаще попадает на один и тот же backend. Полезно для stateful TCP/UDP-сценариев, но хуже распределяет трафик, если клиентов мало.

---

## 5. Persistence / session affinity

Можно включить sticky behavior:

```conf
virtual_server 10.0.0.100 443 {
    delay_loop 5
    lb_algo wlc
    lb_kind NAT
    persistence_timeout 300
    protocol TCP

    real_server 10.0.1.11 443 {
        weight 1
        TCP_CHECK {
            connect_port 443
        }
    }

    real_server 10.0.1.12 443 {
        weight 1
        TCP_CHECK {
            connect_port 443
        }
    }
}
```

`persistence_timeout 300` означает, что клиентский IP некоторое время будет привязан к выбранному backend’у.

Полезно для:

```text
stateful TCP-сессий
старых web-приложений без нормального shared session storage
UDP-сервисов
TLS passthrough, если backend держит состояние
```

Минусы:

```text
может ухудшить равномерность распределения
NAT-клиенты могут перегрузить один backend
при падении backend’а sticky mapping всё равно должен быть сброшен/обойдён
```

---

## 6. sorry_server

Можно указать fallback backend:

```conf
virtual_server 10.0.0.100 80 {
    delay_loop 5
    lb_algo rr
    lb_kind NAT
    protocol TCP

    sorry_server 10.0.1.99 80

    real_server 10.0.1.11 80 {
        weight 1
        HTTP_GET {
            url {
                path /ready
                status_code 200
            }
        }
    }
}
```

Если все реальные backend’ы недоступны, трафик можно отправить на `sorry_server`.

Примеры:

```text
maintenance page
заглушка API
static “service unavailable”
read-only fallback
```

---

# Важный момент: health-check принимает решение “можно ли слать новые подключения”, но не всегда убивает старые

Для TCP-сервисов поведение обычно такое:

```text
backend healthy → получает новые соединения
backend failed → удаляется из pool
новые соединения туда не идут
старые соединения могут жить до разрыва
```

Поэтому для stateful long-lived соединений нужно отдельно думать про draining:

```text
WebSocket
MQTT
PostgreSQL
Kafka
gRPC streaming
SIP
длинные TCP-сессии
```

Keepalived/IPVS — это не полноценный orchestrator draining’а. Он хорошо исключает узел из новых подключений, но graceful shutdown приложения лучше делать на стороне самого приложения или через отдельную логику.

---

# 7. LVS TUN mode

Теперь про вариант 7: `lb_kind TUN`.

Схема:

```text
client
  |
  v
VIP на LVS director
  |
  | IPIP tunnel
  v
real_server
  |
  v
ответ напрямую client
```

То есть входящий трафик идёт через director, а ответ возвращается клиенту напрямую от backend’а.

Сравнение:

```text
NAT:
client → director → backend → director → client

DR:
client → director → backend → client
но обычно backend’ы в той же L2-сети

TUN:
client → director → tunnel → backend → client
backend может быть в другой L3-сети
```

Keepalived конфигурационно поддерживает `lb_kind NAT|DR|TUN` внутри `virtual_server`. ([keepalived.org][1])

Пример:

```conf
virtual_server 203.0.113.10 443 {
    delay_loop 5
    lb_algo wlc
    lb_kind TUN
    protocol TCP

    real_server 10.10.1.11 443 {
        weight 1
        TCP_CHECK {
            connect_port 443
            connect_timeout 2
        }
    }

    real_server 10.20.1.12 443 {
        weight 1
        TCP_CHECK {
            connect_port 443
            connect_timeout 2
        }
    }
}
```

## Что должен уметь real_server в TUN mode

На real server обычно нужно:

1. IPIP tunnel support;
2. VIP на loopback/tunnel-интерфейсе;
3. приложение должно слушать VIP или `0.0.0.0`;
4. корректная обратная маршрутизация к клиентам;
5. отключение/настройка ARP-поведения, если VIP где-то виден на L2;
6. firewall должен пропускать IPIP, protocol 4.

Упрощённый пример на backend:

```bash
modprobe ipip

ip tunnel add tunl0 mode ipip
ip link set tunl0 up

ip addr add 203.0.113.10/32 dev tunl0
```

И часто sysctl:

```bash
sysctl -w net.ipv4.ip_forward=0
sysctl -w net.ipv4.conf.all.rp_filter=0
sysctl -w net.ipv4.conf.tunl0.rp_filter=0
```

Для некоторых схем также настраивают ARP-параметры:

```bash
sysctl -w net.ipv4.conf.all.arp_ignore=1
sysctl -w net.ipv4.conf.all.arp_announce=2
```

Но для TUN это зависит от того, где и как объявлен VIP. В DR ARP-настройки почти всегда критичны; в TUN — зависят от топологии.

---

# Как в TUN mode решается, можно ли отправлять трафик на узел

Логика eligibility такая же, как в обычном LVS:

```text
health-check ok → real_server есть в IPVS table
health-check failed → real_server удалён из IPVS table
```

Но есть дополнительная проблема: health-check может проходить, а реальный dataplane через tunnel — нет.

Например:

```text
TCP_CHECK на 10.10.1.11:443 успешен
но IPIP tunnel до backend’а сломан
или backend не принял VIP на tunl0
или rp_filter дропает пакеты
или firewall режет protocol 4
```

Поэтому в TUN mode health-check лучше делать таким образом, чтобы он максимально проверял именно реальный путь обслуживания.

---

# Варианты принятия решения о доступности узла

## Вариант A. Простая проверка порта

```conf
TCP_CHECK {
    connect_port 443
    connect_timeout 2
}
```

Проверяет:

```text
узел доступен по сети
порт открыт
процесс слушает
```

Не проверяет:

```text
приложение готово
есть ли зависимости
работает ли tunnel dataplane
является ли узел нужной ролью
```

Подходит для простых stateless TCP-сервисов.

---

## Вариант B. HTTP readiness endpoint

```conf
HTTP_GET {
    url {
        path /ready
        status_code 200
    }
    connect_port 8080
    connect_timeout 2
    nb_get_retry 3
    delay_before_retry 1
}
```

Проверяет:

```text
приложение отвечает
оно само считает себя ready
```

В `/ready` приложение может включить проверки:

```text
подключение к БД
миграции применены
кэш доступен
очереди доступны
локальный overload flag не выставлен
узел не в drain mode
```

Это самый практичный вариант для web/API.

---

## Вариант C. Отдельный health-port

Иногда сервис слушает публичный порт `443`, а health-check — на `8080`.

```conf
real_server 10.0.1.11 443 {
    weight 1

    HTTP_GET {
        connect_port 8080
        url {
            path /ready
            status_code 200
        }
    }
}
```

То есть трафик клиентов идёт на:

```text
10.0.1.11:443
```

А проверка идёт на:

```text
10.0.1.11:8080/ready
```

Плюсы:

```text
можно не светить health endpoint наружу
можно отдавать более подробный статус
можно проверять admin/readiness интерфейс
```

Минус: можно получить ложноположительный результат, если health-port жив, а основной dataplane порт сломан.

---

## Вариант D. MISC_CHECK с бизнес-логикой

Для сложных систем лучше всего.

Пример сценариев:

```text
отправлять write-трафик только на PostgreSQL primary
отправлять read-трафик только на replica с lag < 5s
исключать узел при CPU steal > N%
исключать узел при disk full
исключать узел при active drain flag
исключать узел, если локальный sidecar не готов
проверять, что IPIP tunnel поднят
проверять, что VIP есть на tunl0
```

Пример для TUN:

```conf
real_server 10.10.1.11 443 {
    weight 1

    MISC_CHECK {
        misc_path "/usr/local/bin/check_tun_backend.sh 10.10.1.11 203.0.113.10 443"
        misc_timeout 3
    }
}
```

Скрипт может делать, например:

```bash
#!/bin/bash
HOST="$1"
VIP="$2"
PORT="$3"

# 1. Проверяем management endpoint
curl -fsS --max-time 2 "http://$HOST:8080/ready" >/dev/null || exit 1

# 2. Проверяем, что основной порт открыт
nc -z -w2 "$HOST" "$PORT" || exit 1

# 3. Дополнительная логика:
# например, проверка drain-флага из Consul/etcd/local file

exit 0
```

Важно: `MISC_CHECK` исполняется на LVS director’е, не на backend’е. Поэтому скрипт проверяет backend удалённо или через внешнюю систему.

---

## Вариант E. Внешний control plane меняет weight

Иногда решение “можно ли слать трафик” принимает не keepalived, а внешняя система:

```text
Prometheus/Alertmanager
Consul
etcd
Nomad/Kubernetes controller
свой deployment-controller
```

Она может:

```text
менять конфиг keepalived
перезапускать/reload’ить keepalived
управлять IPVS напрямую через ipvsadm
ставить drain-флаг, который читает MISC_CHECK
```

Например, перед деплоем:

```text
touch /var/run/drain
MISC_CHECK начинает возвращать fail
keepalived убирает node из pool
ждём завершения старых соединений
останавливаем сервис
```

Для keepalived обычно безопаснее делать не прямое хаотичное изменение IPVS, а управлять через health endpoint или MISC_CHECK.

---

## Вариант F. Проверка через реальный VIP-путь

Самый строгий вариант — проверять не только backend IP, а именно способность backend обслужить запрос, пришедший на VIP.

Для TUN это особенно важно.

Идея:

```text
director должен убедиться:
backend получил encapsulated traffic
backend обработал пакет на VIP
ответ ушёл корректно
```

Сделать это простым `TCP_CHECK` сложно, потому что check обычно идёт напрямую на real server IP, а не через IPVS dataplane.

Возможные подходы:

```text
1. отдельный synthetic probe с внешней точки;
2. MISC_CHECK, который запускает проверку через внешний monitoring endpoint;
3. blackbox exporter снаружи + drain-флаг;
4. локальный агент на backend сообщает ready только если VIP/tunl0/route/firewall корректны;
5. периодические end-to-end тесты через сам VIP.
```

Для production TUN я бы не полагался только на `TCP_CHECK`.

---

# Какой health decision выбрать на практике

## Для обычного HTTP/API

Лучший вариант:

```text
HTTP_GET /ready
```

Пример:

```conf
virtual_server 10.0.0.100 443 {
    delay_loop 3
    lb_algo wlc
    lb_kind NAT
    protocol TCP

    real_server 10.0.1.11 443 {
        weight 10
        SSL_GET {
            connect_port 443
            connect_timeout 2
            nb_get_retry 2
            delay_before_retry 1
            url {
                path /ready
                status_code 200
            }
        }
    }
}
```

---

## Для TCP-сервиса без HTTP

Минимум:

```text
TCP_CHECK
```

Лучше:

```text
MISC_CHECK со специализированной проверкой протокола
```

Например для PostgreSQL:

```text
не просто “порт 5432 открыт”
а “это primary” или “replica lag < 5s”
```

---

## Для UDP

UDP сложнее, потому что “соединения” нет. Для UDP-сервисов часто используют:

```text
MISC_CHECK
DNS_CHECK
проверку отдельного TCP/HTTP health endpoint
```

Например, балансировать UDP syslog, но health проверять через HTTP endpoint приложения:

```conf
virtual_server 10.0.0.100 514 {
    delay_loop 3
    lb_algo sh
    lb_kind NAT
    protocol UDP

    real_server 10.0.1.11 514 {
        weight 1
        HTTP_GET {
            connect_port 9000
            url {
                path /api/system/lbstatus
                status_code 200
            }
        }
    }
}
```

---

## Для TUN mode

Я бы делал так:

```text
1. MISC_CHECK или HTTP_GET /ready
2. readiness endpoint проверяет:
   - приложение ready
   - VIP установлен на tunl0/loopback
   - tunnel interface up
   - rp_filter/firewall не ломают путь
   - node не в drain mode
3. внешний blackbox-monitor дополнительно проверяет VIP end-to-end
```

Пример backend readiness:

```bash
#!/bin/bash

VIP="203.0.113.10"
PORT="443"

ip addr show tunl0 | grep -q "$VIP" || exit 1
ss -lnt | grep -q ":$PORT" || exit 1
test ! -f /var/run/drain || exit 1

curl -fsS --max-time 1 http://127.0.0.1:8080/internal-ready >/dev/null || exit 1

exit 0
```

А keepalived проверяет этот readiness:

```conf
real_server 10.10.1.11 443 {
    weight 10

    HTTP_GET {
        connect_port 8080
        connect_timeout 2
        nb_get_retry 2
        delay_before_retry 1

        url {
            path /ready
            status_code 200
        }
    }
}
```

---

# NAT vs TUN с точки зрения health decision

| Критерий                                    |        NAT |       TUN |
| ------------------------------------------- | ---------: | --------: |
| Простота                                    |       выше |      ниже |
| Backend в другой сети                       |         да |        да |
| Ответ идёт через director                   |         да |       нет |
| Нагрузка на director                        |       выше |      ниже |
| Нужно настраивать VIP на backend            | обычно нет |        да |
| Нужно думать про IPIP/firewall/rp_filter    | нет/меньше |        да |
| Health-check напрямую на backend достаточен |   часто да | не всегда |
| Риск “check ok, трафик не ходит”            |       ниже |      выше |

---

# Самая важная практическая рекомендация

Не делай health-check вида:

```text
порт открыт → узел healthy
```

если тебе важно качество обслуживания.

Лучше модель такая:

```text
узел получает трафик только если:
1. процесс жив;
2. порт слушает;
3. приложение готово;
4. зависимости доступны;
5. роль узла правильная;
6. узел не в drain/maintenance;
7. для TUN/DR — dataplane настроен корректно;
8. recent error rate/overload не превышает порог.
```

В keepalived это обычно реализуется одним из трёх способов:

```text
HTTP_GET /ready       — для приложений с HTTP health endpoint
TCP_CHECK             — для простых TCP-сервисов
MISC_CHECK            — для сложной логики и stateful-сервисов
```

Для production я бы выбирал так:

```text
HTTP/API             → HTTP_GET или SSL_GET /ready
PostgreSQL write     → MISC_CHECK: primary only
PostgreSQL read      → MISC_CHECK: replica + lag threshold
Redis primary        → MISC_CHECK: role:master
UDP service          → MISC_CHECK или отдельный HTTP health-port
TUN mode             → HTTP_GET/MISC_CHECK + внешний end-to-end probe
```

То есть в вариантах **4** и **7** главное решение “слать или не слать трафик” принимает не сам алгоритм балансировки. Алгоритм выбирает только среди уже допущенных backend’ов. А допуск backend’а в пул определяется health-check’ами keepalived и, при необходимости, внешней логикой вокруг них.

[1]: https://www.keepalived.org/doc/configuration_synopsis.html?utm_source=chatgpt.com "Keepalived configuration synopsis — Keepalived 1.4.3 documentation"
[2]: https://www.keepalived.org/doc/software_design.html?utm_source=chatgpt.com "Software Design — Keepalived 1.4.3 documentation"

