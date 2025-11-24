Ниже — готовая схема, конфиги и команды, чтобы VM с OpenVPN‑клиентом стала «маршрутизатором по умолчанию» для всей подсети 192.168.1.0/24.

Идея:
- VM (Linux, например Ubuntu/Debian) с IP 192.168.1.250/24 в вашей LAN.
- На VM поднимается OpenVPN client, который делает дефолтный маршрут через туннель.
- На остальных хостах указываем шлюз по умолчанию 192.168.1.250.
- На VM включаем IP‑forwarding и NAT LAN→tun0.

Предпосылки/обозначения:
- LAN: 192.168.1.0/24
- VM: 192.168.1.250/24, интерфейс в LAN: eth0 (замените, если у вас ens18/enpXsY и т.п.)
- Роутер провайдера в LAN (если есть): 192.168.1.1
- Туннельный интерфейс OpenVPN: tun0
- Дистрибутив: Ubuntu 22.04+/Debian 11+ (systemd)
- Сетевой адаптер VM — в мост/bridge к реальной сети (НЕ NAT от гипервизора)

Шаг 1. Статический IP на VM (если ещё не сделано)
Netplan (Ubuntu). Файл /etc/netplan/01-lan.yaml:
```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: no
      addresses: [192.168.1.250/24]
      gateway4: 192.168.1.1
      nameservers:
        addresses: [1.1.1.1, 9.9.9.9]
```
Применить:
```bash
sudo netplan apply
```

Шаг 2. Установка пакетов
```bash
sudo apt update
sudo apt install -y openvpn iptables-persistent
```
В процессе iptables-persistent предложит «save current rules?» — можно ответить No (мы сохраним позже).

Шаг 3. Конфиг OpenVPN‑клиента
1) Создайте каталог и положите материалы:
```bash
sudo mkdir -p /etc/openvpn/client
```

2) Конфиг клиента /etc/openvpn/client/gw.conf (замените remote/сертификаты под ваш сервер):
```conf
client
dev tun
proto udp
remote vpn.example.com 1194
resolv-retry infinite
nobind
persist-key
persist-tun
verb 3
remote-cert-tls server

# Аутентификация: вариант с логином/паролем
auth-user-pass /etc/openvpn/client/credentials

# Если используете PKI - раскомментируйте и укажите свои файлы
# ca /etc/openvpn/client/ca.crt
# cert /etc/openvpn/client/client.crt
# key /etc/openvpn/client/client.key

# Сделать весь трафик через VPN (OpenVPN сам создаст исключение для IP сервера)
redirect-gateway def1

# Надёжность
keepalive 10 60
ping-timer-rem
explicit-exit-notify 1

# MTU/фрагментация (при необходимости подстройте)
mssfix 1450
tun-mtu 1500
```

3) Если используете логин/пароль, создайте файл:
```bash
sudo bash -c 'printf "%s\n%s\n" "VPN_LOGIN" "VPN_PASSWORD" > /etc/openvpn/client/credentials'
sudo chmod 600 /etc/openvpn/client/credentials
```
(Подставьте реальные значения. Если вместо user/pass у вас сертификаты — используйте ca/cert/key и уберите строку auth-user-pass.)

Шаг 4. Включить роутинг и корректный rp_filter
```bash
sudo bash -c 'cat >/etc/sysctl.d/99-vpn-gw.conf <<EOF
net.ipv4.ip_forward=1
# Нестрогая проверка обратного пути, чтобы не ломать асимметричный трафик
net.ipv4.conf.all.rp_filter=2
net.ipv4.conf.default.rp_filter=2
EOF'
sudo sysctl --system
```

Шаг 5. NAT и правила форвардинга (iptables)
Правила: разрешаем форвардинг LAN↔tun0 и делаем NAT наружу в туннель.
```bash
# Очистим таблицы (необязательно, но полезно на чистой системе)
sudo iptables -F
sudo iptables -t nat -F

# Разрешить пересылку установленных соединений обратно из туннеля в LAN
sudo iptables -A FORWARD -i tun0 -o eth0 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Разрешить новый трафик из LAN в туннель
sudo iptables -A FORWARD -i eth0 -o tun0 -j ACCEPT

# NAT (маскарадинг) для всего, что уходит в VPN
sudo iptables -t nat -A POSTROUTING -o tun0 -j MASQUERADE

# (необязательно) запретить остальной форвардинг «по умолчанию»
sudo iptables -P FORWARD DROP

# Сохранить правила для автозагрузки
sudo netfilter-persistent save
```

Шаг 6. Автозапуск OpenVPN‑клиента
На современных Ubuntu/Debian конфиги из /etc/openvpn/client/*.conf обслуживаются юнитом openvpn-client@.service:
```bash
sudo systemctl enable --now openvpn-client@gw
```
Проверка статуса:
```bash
systemctl status openvpn-client@gw
ip addr show tun0
ip route
```
Если в вашей системе юнит называется иначе (иногда openvpn@NAME), посмотрите:
```bash
systemctl list-unit-files | grep openvpn
```

Шаг 7. Настроить остальные хосты использовать 192.168.1.250 как default gateway
Варианты:
- Через DHCP (предпочтительно): на вашем DHCP‑сервере выставьте Option 3 (Router) = 192.168.1.250 для подсети 192.168.1.0/24. Перезапустите DHCP и обновите lease на клиентах (ipconfig /renew, dhclient -r; dhclient).
- Вручную на хостах:
  - Linux: sudo ip route replace default via 192.168.1.250
  - Windows (PowerShell адм.): New-NetRoute -DestinationPrefix "0.0.0.0/0" -InterfaceAlias "Ethernet" -NextHop 192.168.1.250

DNS у клиентов:
- Если хотите, чтобы DNS‑запросы также шли через VPN, просто раздайте клиентам публичные резолверы (например 1.1.1.1/9.9.9.9) через DHCP Option 6 — благодаря новому default gateway они уйдут в туннель. Либо используйте DNS сервера, которые провайдер VPN рекомендует.

Проверка
1) На VM:
```bash
curl -4 ifconfig.io
ip route | sed -n '1,5p'
```
Убедитесь, что default route указывает на tun0 (будут добавлены маршруты def1 через 0.0.0.0/1 и 128.0.0.0/1 в сторону туннеля).
2) На любом клиентском хосте LAN:
- traceroute/tracert 1.1.1.1 — первым хопом должен быть 192.168.1.250.
- curl ifconfig.io — внешний IP должен быть от VPN.

Полезные примечания
- Если VPN упадёт, клиенты могут потерять интернет (и это обычно желаемое поведение). Для авто‑восстановления у нас есть keepalive/ping‑restart; при необходимости реализуйте fallback‑маршрутизацию/политику.
- Если ваш OpenVPN‑сервер сам «пушит» redirect-gateway, строка redirect-gateway def1 в клиентском конфиге не обязательна (можно оставить обе — не конфликтуют).
- Если интерфейсы у вас называются не eth0/tun0 — поправьте в правилах iptables.
- Безопасность: держите VM обновлённой; по желанию ограничьте входящие на VM (ssh и пр.) ufw/iptables, это не мешает форвардингу, если правила выше сохранены.

Вариант на nftables (если хотите вместо iptables)
Файл /etc/nftables.conf:
```nft
flush ruleset
table inet filter {
  chain forward {
    type filter hook forward priority 0;
    policy drop;
    ct state established,related accept
    iifname "eth0" oifname "tun0" accept
  }
}
table ip nat {
  chain postrouting {
    type nat hook postrouting priority 100;
    oifname "tun0" masquerade
  }
}
```
Применить и включить автозапуск:
```bash
sudo nft -f /etc/nftables.conf
sudo systemctl enable --now nftables
```

Готово. Если под ваш сервер нужны конкретные параметры (cipher, auth, ca/cert/key, порт/proto), скажите — подгоню конфиг точно под него.
