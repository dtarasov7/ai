Создам для вас полную конфигурацию VM как VPN-шлюза. Вот пошаговая инструкция со всеми необходимыми конфигами и командами.

## 1. Настройка сети на VM

### Для Ubuntu/Debian с Netplan:
```yaml
# /etc/netplan/01-netcfg.yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:  # замените на имя вашего интерфейса (ens18, enp0s3 и т.д.)
      dhcp4: no
      addresses:
        - 192.168.1.250/24
      gateway4: 192.168.1.1
      nameservers:
        addresses:
          - 8.8.8.8
          - 1.1.1.1
```

Применить конфигурацию:
```bash
sudo netplan apply
```

### Для Debian/Ubuntu с /etc/network/interfaces:
```bash
# /etc/network/interfaces
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.250
    netmask 255.255.255.0
    gateway 192.168.1.1
    dns-nameservers 8.8.8.8 1.1.1.1
```

Применить:
```bash
sudo systemctl restart networking
```

## 2. Установка необходимых пакетов

```bash
sudo apt update
sudo apt install -y openvpn iptables-persistent
```

## 3. Включение IP forwarding

```bash
# Включаем IP forwarding
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
echo "net.ipv6.conf.all.forwarding=1" | sudo tee -a /etc/sysctl.conf

# Применяем изменения
sudo sysctl -p
```

## 4. Конфигурация OpenVPN клиента

Создайте файл конфигурации OpenVPN:
```bash
# /etc/openvpn/client.conf
client
dev tun
proto udp
remote your-vpn-server.com 1194  # замените на адрес вашего VPN сервера
resolv-retry infinite
nobind
persist-key
persist-tun

# ВАЖНО: не позволяем OpenVPN менять маршруты
route-nopull
script-security 2

# Добавляем скрипт для настройки маршрутов только для туннеля
up /etc/openvpn/up.sh
down /etc/openvpn/down.sh

# Безопасность
cipher AES-256-CBC
auth SHA256
comp-lzo
verb 3

# Логирование
log-append /var/log/openvpn.log
status /var/log/openvpn-status.log

# Здесь должны быть ваши сертификаты и ключи
# Либо inline, либо пути к файлам
ca /etc/openvpn/ca.crt
cert /etc/openvpn/client.crt
key /etc/openvpn/client.key
tls-auth /etc/openvpn/ta.key 1
```

## 5. Создание скриптов для управления маршрутами

### Скрипт up.sh:
```bash
#!/bin/bash
# /etc/openvpn/up.sh

# Логирование
echo "$(date) OpenVPN UP script started" >> /var/log/openvpn-scripts.log

# Добавляем маршрут только для VPN-сервера через основной шлюз
# чтобы сам VPN-трафик не попал в туннель
VPN_SERVER_IP=$(echo $trusted_ip | cut -d' ' -f1)
if [ -n "$VPN_SERVER_IP" ]; then
    ip route add $VPN_SERVER_IP via 192.168.1.1 dev eth0
fi

echo "$(date) OpenVPN interface $dev is up with IP $ifconfig_local" >> /var/log/openvpn-scripts.log
```

### Скрипт down.sh:
```bash
#!/bin/bash
# /etc/openvpn/down.sh

# Логирование
echo "$(date) OpenVPN DOWN script started" >> /var/log/openvpn-scripts.log

# Удаляем маршрут для VPN-сервера
VPN_SERVER_IP=$(echo $trusted_ip | cut -d' ' -f1)
if [ -n "$VPN_SERVER_IP" ]; then
    ip route del $VPN_SERVER_IP via 192.168.1.1 dev eth0
fi

echo "$(date) OpenVPN interface $dev is down" >> /var/log/openvpn-scripts.log
```

Сделайте скрипты исполняемыми:
```bash
sudo chmod +x /etc/openvpn/up.sh /etc/openvpn/down.sh
```

## 6. Настройка iptables

```bash
#!/bin/bash
# Скрипт для настройки iptables

# Очищаем существующие правила (опционально)
# sudo iptables -F
# sudo iptables -t nat -F

# Разрешаем локальный трафик
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A OUTPUT -o lo -j ACCEPT

# Разрешаем установленные соединения
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT

# Разрешаем входящий трафик из локальной сети
sudo iptables -A INPUT -i eth0 -s 192.168.1.0/24 -j ACCEPT

# Разрешаем форвардинг из локальной сети в VPN
sudo iptables -A FORWARD -i eth0 -o tun0 -s 192.168.1.0/24 -j ACCEPT
sudo iptables -A FORWARD -i tun0 -o eth0 -d 192.168.1.0/24 -j ACCEPT

# NAT для трафика, идущего через VPN
sudo iptables -t nat -A POSTROUTING -o tun0 -s 192.168.1.0/24 -j MASQUERADE

# Разрешаем SSH (для управления VM)
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Сохраняем правила
sudo netfilter-persistent save
```

Выполните этот скрипт:
```bash
sudo bash iptables-setup.sh
```

## 7. Создание systemd сервиса для автозапуска

```bash
# Включаем автозапуск OpenVPN
sudo systemctl enable openvpn@client
sudo systemctl start openvpn@client
```

## 8. Скрипт проверки состояния

Создайте скрипт для мониторинга:
```bash
#!/bin/bash
# /usr/local/bin/vpn-gateway-status.sh

echo "=== VPN Gateway Status ==="
echo ""
echo "1. IP Forwarding:"
sysctl net.ipv4.ip_forward

echo ""
echo "2. Network Interfaces:"
ip -br a

echo ""
echo "3. OpenVPN Status:"
systemctl status openvpn@client --no-pager | head -n 10

echo ""
echo "4. Routing Table:"
ip route

echo ""
echo "5. IPTables NAT Rules:"
sudo iptables -t nat -L POSTROUTING -n -v

echo ""
echo "6. Connected Clients (ARP table):"
arp -n | grep 192.168.1

echo ""
echo "7. Traffic Statistics:"
if [ -f /var/log/openvpn-status.log ]; then
    tail -n 20 /var/log/openvpn-status.log
fi
```

Сделайте его исполняемым:
```bash
sudo chmod +x /usr/local/bin/vpn-gateway-status.sh
```

## 9. Настройка клиентских устройств

### Для Linux клиентов:
```bash
# Временно (для теста)
sudo ip route del default
sudo ip route add default via 192.168.1.250

# Постоянно (Ubuntu/Debian)
# Отредактируйте /etc/netplan/*.yaml или /etc/network/interfaces
# и измените gateway на 192.168.1.250
```

### Для Windows клиентов:
```batch
# В командной строке с правами администратора
route delete 0.0.0.0
route add 0.0.0.0 mask 0.0.0.0 192.168.1.250
```

### Для выборочного роутинга (только определенные устройства):
На основном роутере можно настроить статические маршруты или использовать DHCP option 3 для выдачи разных шлюзов разным устройствам.

## 10. Дополнительные улучшения

### Скрипт для автоматического восстановления соединения:
```bash
#!/bin/bash
# /usr/local/bin/vpn-watchdog.sh

while true; do
    if ! ping -c 1 -W 5 8.8.8.8 -I tun0 > /dev/null 2>&1; then
        echo "$(date) VPN is down, restarting..." >> /var/log/vpn-watchdog.log
        systemctl restart openvpn@client
        sleep 30
    fi
    sleep 60
done
```

Добавьте в crontab:
```bash
@reboot /usr/local/bin/vpn-watchdog.sh &
```

### Мониторинг трафика:
```bash
# Установка vnstat для мониторинга
sudo apt install vnstat
sudo systemctl enable vnstat
sudo vnstat -u -i eth0
sudo vnstat -u -i tun0
```

## Проверка работы

После настройки выполните:
```bash
# На VM-шлюзе
sudo /usr/local/bin/vpn-gateway-status.sh

# На клиентском устройстве
traceroute 8.8.8.8
curl ifconfig.me
```

Если все настроено правильно, вы увидите IP-адрес VPN-сервера вместо вашего домашнего IP.
