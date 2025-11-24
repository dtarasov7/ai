Короткий ответ
Задержка “видна” на server1, потому что она возникает НЕ внутри обработки на server2. Под нагрузкой время уходит либо:
- до попадания запроса на server2 (LB/FW/сеть, handshake, accept‑очереди), либо
- уже после того, как server2 отдал ответ (потери/ретрансляции на обратном пути).
$request_time на server2 не включает TCP‑handshake и ожидание в accept‑очереди до того, как nginx прочитал первый байт запроса, поэтому на server2 “всё быстро”, а на server1 $upstream_* копит секунды.

Типичные причины именно при нагрузке и для маленьких файлов
- Очереди/инспекция/conntrack на LoadBalancer/Firewall (SYN‑cookies, maxconn, DPI). В пиках запрос “зависает” до/после server2, а когда дошёл — обрабатывается за мс.
- Перепады/потери пакетов → экспоненциальные RTO 1s+2s+4s ≈ 7s до “первого байта” ответа. Для маленьких ответов это особенно заметно.
- Переполненная accept‑очередь/CPU паузы на server2: connect на server1 проходит быстро, но до того как nginx на server2 “примет” соединение, проходит время. В $request_time это не попадает, а на server1 растёт $upstream_header_time.
- Много коротких upstream‑соединений без keepalive между server1→LB→server2 → лишние handshakes и нагрузка на LB/FW/NAT. При высокой параллельности всплывают задержки, а одиночные запросы идут быстро.

Что сделать, чтобы точно указать место, где “горит” время
1) Детализируйте тайминги на server1.
- Лог: msec, request_id, upstream_connect_time, upstream_header_time, upstream_response_time, upstream_status, upstream_addr.
nginx:
log_format up '$msec rid=$request_id c=$upstream_connect_time h=$upstream_header_time r=$upstream_response_time st=$upstream_status addr=$upstream_addr';
access_log /var/log/nginx/access_up.log up;
proxy_set_header X-Request-ID $request_id;

2) Коррелируйте с server2 по тому же request_id.
map $http_x_request_id $rid { default $request_id; }
log_format s2 '$msec rid=$rid rtime=$request_time rtt=$tcpinfo_rtt conn=$connection creq=$connection_requests';
access_log /var/log/nginx/access_s2.log s2;

3) Интерпретация:
- Большой upstream_connect_time → проблема до server2 (LB/FW/SYN‑дропы/коннтрек).
- Малый connect, большой upstream_header_time → запрос дошёл до ядра server2, но приложение приняло его поздно (accept backlog/CPU) или “первый байт ответа” теряется по пути (RTO/потери).
- Малые connect+header, но большой (response_time − header_time) → тянется передача тела ответа (обычно сеть/потери на обратном пути).

4) Параллельные tcpdump (на короткий интервал и проблемный URI).
- На server1: tcpdump -s0 -w s1.pcap host <server2_or_LB_ip> and tcp port 80
- На server2: tcpdump -s0 -w s2.pcap host <server1_or_LB_ip> and tcp port 80
Смотрите retransmissions, DUP‑ACK, ZeroWindow, MSS/MTU. Если на server2 видно, что ответ ушёл мгновенно, а на server1 первый байт приходит спустя секунды — проблема на пути/LB/FW.

5) Проверить узкие места на LB/FW.
- Таблица conntrack, drops/overruns, maxconn/queue, включён ли DPI/IPS для этого трафика.
- CPU softirq на интерфейсах, ring‑буферы, dmesg о дропах.

6) Исключить PMTU/ICMP‑blackhole (на всякий случай).
- Разрешить ICMP “Fragmentation needed”.
- Временно MSS‑clamp и/или net.ipv4.tcp_mtu_probing=1.

Практические меры, которые часто снимают симптом
- Включите keepalive к апстриму (server1→LB/server2), чтобы не штамповать тысячи коротких TCP:
upstream static {
    server LB_IP:80;
    keepalive 512;
}
server {
    location / {
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_pass http://static;
    }
}
- Увеличьте listen backlog на server2 и системные лимиты:
listen 80 reuseport backlog=8192;
sysctl: net.core.somaxconn=8192, net.ipv4.tcp_max_syn_backlog=8192
- Проверьте worker_processes auto; worker_connections, rlimit_nofile на обоих nginx.
- На LB (например, HAProxy): не держать очередь на backend без лимитов; server … maxconn N; tune.maxaccept; включить HTTP keep‑alive на бэкенде.
- На FW: увеличить conntrack, выключить глубокую инспекцию для этого сегмента/порта, убедиться, что Fast‑path задействован.

Если пришлёте по одному “медленному” и “быстрому” примеру строк из access‑логов server1 (с c/h/r/addr/status) и соответствующие строки с server2 (rid/rtime), плюс модель LB/FW и есть ли upstream keepalive, подскажу точнее, где именно задержка и что именно подкрутить.
