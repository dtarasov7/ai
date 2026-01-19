#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Packet Monitor - Block 1: Multi-Interface Packet Capture (FIXED)
Поддержка захвата с нескольких интерфейсов одновременно
"""

from scapy.all import sniff, conf, get_if_list
from datetime import datetime
from collections import deque
import threading
import time
import sys


class PacketCapture:
    """
    Захват пакетов с кольцевым буфером и поддержкой нескольких интерфейсов
    """
    
    def __init__(self, interface=None, packet_limit=50000, log_file=None):
        """
        Инициализация захвата пакетов
        
        Args:
            interface: сетевой интерфейс или список интерфейсов
                      None - автоопределение
                      'any' - все интерфейсы
                      'eth0' - один интерфейс
                      ['eth0', 'wlan0'] - список интерфейсов
            packet_limit: максимальное количество пакетов в буфере
            log_file: путь к файлу логов (None = без логов)
        """
        self.packet_limit = packet_limit
        self.log_file = log_file
        
        # Определяем список интерфейсов для захвата
        if interface is None:
            # Автоопределение - основной интерфейс
            self.interfaces = [conf.iface]
            self.interface = conf.iface
        elif interface == 'any':
            # Захват со всех интерфейсов
            self.interfaces = self._get_all_interfaces()
            self.interface = 'any'
        elif isinstance(interface, list):
            # Список интерфейсов
            self.interfaces = interface
            self.interface = ','.join(interface)
        else:
            # Один интерфейс
            self.interfaces = [interface]
            self.interface = interface
        
        # Кольцевой буфер с максимальным размером
        self.packets = deque(maxlen=packet_limit)
        
        # Lock для thread-safety
        self.lock = threading.Lock()
        
        # Потоки захвата (по одному на интерфейс)
        self.capture_threads = []
        self.running = False
        self.stop_sniffing = threading.Event()
        
        # Счетчики для статистики
        self.packet_counter = 0
        self.total_bytes = 0
        self.start_time = None
        
        # Bandwidth tracking
        self.bytes_last_second = 0
        self.last_bandwidth_check = None
        self.current_bandwidth = 0
        
        # Latency tracking
        self.latency_samples = deque(maxlen=1000)
        
        # Packet loss detection
        self.tcp_sequence_tracker = {}
        self.packet_loss_count = 0
        
        self._log(f"Initialized with interfaces: {self.interfaces}")
        self._log(f"Ring buffer max: {packet_limit} packets")
    
    def _get_all_interfaces(self):
        """Получить список всех сетевых интерфейсов"""
        try:
            # Получаем все интерфейсы
            all_ifaces = get_if_list()
            
            # Фильтруем служебные интерфейсы
            filtered = [
                iface for iface in all_ifaces
                if not iface.startswith('lo') and  # loopback
                   not iface.startswith('docker') and  # docker
                   not iface.startswith('veth') and  # virtual ethernet
                   not iface.startswith('br-')  # bridge
            ]
            
            # Если список пустой - берем все кроме lo
            if not filtered:
                filtered = [iface for iface in all_ifaces if iface != 'lo']
            
            self._log(f"Detected interfaces: {filtered}")
            return filtered if filtered else [conf.iface]
            
        except Exception as e:
            self._log(f"Error getting interfaces: {e}")
            return [conf.iface]
    
    def _log(self, message):
        """Логирование в файл вместо print()"""
        if self.log_file:
            try:
                with open(self.log_file, 'a') as f:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    f.write(f"[{timestamp}] {message}\n")
            except:
                pass
    
    def _packet_handler(self, pkt):
        """Обработчик пакета (callback для sniff)"""
        if not self.running:
            return
        
        with self.lock:
            # Парсим пакет
            packet_info = self._parse_packet(pkt)
            
            # Добавляем номер пакета
            self.packet_counter += 1
            packet_info['num'] = self.packet_counter
            
            # Добавляем в кольцевой буфер
            self.packets.append(packet_info)
            
            # Обновляем статистику bandwidth
            packet_size = packet_info.get('size', 0)
            self.total_bytes += packet_size
            self.bytes_last_second += packet_size
            
            # Обновляем bandwidth каждую секунду
            current_time = time.time()
            if self.last_bandwidth_check is None:
                self.last_bandwidth_check = current_time
            elif current_time - self.last_bandwidth_check >= 1.0:
                self.current_bandwidth = self.bytes_last_second
                self.bytes_last_second = 0
                self.last_bandwidth_check = current_time
            
            # Детекция packet loss для TCP
            if packet_info['proto'] in ['TCP', 'TCPv4', 'TCPv6']:
                self._detect_packet_loss(packet_info, pkt)
            
            # Измерение latency
            self._measure_latency(pkt)
    
    def _detect_packet_loss(self, packet_info, pkt):
        """Улучшенная детекция потери пакетов"""
        try:
            from scapy.layers.inet import TCP
            
            if not pkt.haslayer(TCP):
                return
            
            tcp = pkt[TCP]
            seq = tcp.seq
            payload_len = len(tcp.payload) if tcp.payload else 0
            
            src_ip = packet_info.get('src_ip')
            dst_ip = packet_info.get('dst_ip')
            src_port = packet_info.get('src_port')
            dst_port = packet_info.get('dst_port')
            
            if not all([src_ip, dst_ip, src_port, dst_port]):
                return
            
            flow_key = (src_ip, dst_ip, src_port, dst_port)
            
            if flow_key in self.tcp_sequence_tracker:
                last_seq, last_len = self.tcp_sequence_tracker[flow_key]
                expected_seq = last_seq + max(last_len, 1)
                
                # Разрыв больше чем ожидаемый размер пакета (обычно 1460-1500)
                gap = seq - expected_seq
                
                # Игнорируем retransmissions (seq меньше expected)
                if gap > 1460:  # MSS для Ethernet
                    self.packet_loss_count += 1
                    packet_info['packet_loss'] = True
                    packet_info['seq_gap'] = gap
            
            # Сохраняем текущий seq и длину payload
            self.tcp_sequence_tracker[flow_key] = (seq, payload_len)
            
        except Exception:
            pass

    def _measure_latency(self, pkt):
        """Измерение latency"""
        try:
            if hasattr(pkt, 'time'):
                capture_time = pkt.time
                current_time = time.time()
                
                latency_us = (current_time - capture_time) * 1000000
                
                if 0 < latency_us < 1000000:
                    self.latency_samples.append(latency_us)
        except Exception:
            pass
    
    def _parse_packet(self, pkt):
        """Парсинг пакета в словарь с информацией"""
        from scapy.layers.inet import IP, TCP, UDP, ICMP
        from scapy.layers.inet6 import IPv6, ICMPv6EchoRequest, ICMPv6EchoReply
        from scapy.layers.l2 import Ether, ARP
        from scapy.layers.dns import DNS
        
        packet_info = {
            'timestamp': datetime.fromtimestamp(pkt.time),
            'proto': 'UNKNOWN',
            'src': '',
            'dst': '',
            'src_ip': None,
            'dst_ip': None,
            'src_port': None,
            'dst_port': None,
            'info': '',
            'size': len(pkt),
            'raw': bytes(pkt),
            'interface': None,
            'packet_loss': False,
        }
        
        # ИСПРАВЛЕНО: Получаем интерфейс и ВСЕГДА преобразуем в строку
        if hasattr(pkt, 'sniffed_on'):
            iface = pkt.sniffed_on
            # Преобразуем в строку независимо от типа
            packet_info['interface'] = str(iface) if iface else str(self.interface)
        else:
            packet_info['interface'] = str(self.interface)
        
        # Дополнительная проверка
        if packet_info['interface'] and not isinstance(packet_info['interface'], str):
            packet_info['interface'] = str(packet_info['interface'])
        
        # Ethernet layer
        if pkt.haslayer(Ether):
            packet_info['src'] = pkt[Ether].src
            packet_info['dst'] = pkt[Ether].dst
        
        # ARP
        if pkt.haslayer(ARP):
            packet_info['proto'] = 'ARP'
            packet_info['src_ip'] = pkt[ARP].psrc
            packet_info['dst_ip'] = pkt[ARP].pdst
            packet_info['info'] = f"Who has {pkt[ARP].pdst}? Tell {pkt[ARP].psrc}"
        
        # IPv4
        elif pkt.haslayer(IP):
            packet_info['src_ip'] = pkt[IP].src
            packet_info['dst_ip'] = pkt[IP].dst
            
            # TCP
            if pkt.haslayer(TCP):
                packet_info['proto'] = 'TCP'
                packet_info['src_port'] = pkt[TCP].sport
                packet_info['dst_port'] = pkt[TCP].dport
                
                flags = pkt[TCP].flags
                flag_str = self._get_tcp_flags(flags)
                
                packet_info['info'] = f"{pkt[TCP].sport} → {pkt[TCP].dport} [{flag_str}] Seq={pkt[TCP].seq}"
            
            # UDP
            elif pkt.haslayer(UDP):
                packet_info['proto'] = 'UDP'
                packet_info['src_port'] = pkt[UDP].sport
                packet_info['dst_port'] = pkt[UDP].dport
                
                # DNS
                if pkt.haslayer(DNS):
                    packet_info['proto'] = 'DNS'
                    try:
                        dns_query = pkt[DNS].qd.qname.decode() if pkt[DNS].qd else ''
                    except:
                        dns_query = ''
                    packet_info['info'] = f"Query: {dns_query}"
                else:
                    packet_info['info'] = f"{pkt[UDP].sport} → {pkt[UDP].dport} Len={len(pkt[UDP])}"
            
            # ICMP
            elif pkt.haslayer(ICMP):
                packet_info['proto'] = 'ICMP'
                packet_info['info'] = f"Type {pkt[ICMP].type} Code {pkt[ICMP].code}"
        
        # IPv6
        elif pkt.haslayer(IPv6):
            packet_info['src_ip'] = pkt[IPv6].src
            packet_info['dst_ip'] = pkt[IPv6].dst
            
            # TCP over IPv6
            if pkt.haslayer(TCP):
                packet_info['proto'] = 'TCPv6'
                packet_info['src_port'] = pkt[TCP].sport
                packet_info['dst_port'] = pkt[TCP].dport
                
                flags = pkt[TCP].flags
                flag_str = self._get_tcp_flags(flags)
                
                packet_info['info'] = f"{pkt[TCP].sport} → {pkt[TCP].dport} [{flag_str}]"
            
            # UDP over IPv6
            elif pkt.haslayer(UDP):
                packet_info['proto'] = 'UDPv6'
                packet_info['src_port'] = pkt[UDP].sport
                packet_info['dst_port'] = pkt[UDP].dport
                packet_info['info'] = f"{pkt[UDP].sport} → {pkt[UDP].dport}"
            
            # ICMPv6
            elif pkt.haslayer(ICMPv6EchoRequest) or pkt.haslayer(ICMPv6EchoReply):
                packet_info['proto'] = 'ICMPv6'
                packet_info['info'] = 'Echo Request/Reply'
        
        # Если протокол не определен
        if packet_info['proto'] == 'UNKNOWN':
            packet_info['proto'] = 'ETHER'
            packet_info['info'] = pkt.summary()
        
        return packet_info
    
    def _get_tcp_flags(self, flags):
        """Преобразовать TCP флаги в строку"""
        flag_list = []
        if flags & 0x01:
            flag_list.append('FIN')
        if flags & 0x02:
            flag_list.append('SYN')
        if flags & 0x04:
            flag_list.append('RST')
        if flags & 0x08:
            flag_list.append('PSH')
        if flags & 0x10:
            flag_list.append('ACK')
        if flags & 0x20:
            flag_list.append('URG')
        
        return ', '.join(flag_list) if flag_list else 'None'
    
    def _sniff_thread(self, interface):
        """Поток для захвата пакетов с одного интерфейса"""
        self._log(f"Sniff thread started on {interface}")
        
        try:
            sniff(
                iface=interface,
                prn=self._packet_handler,
                store=False,
                stop_filter=lambda x: self.stop_sniffing.is_set()
            )
        except Exception as e:
            self._log(f"Error in sniff thread ({interface}): {e}")
        finally:
            self._log(f"Sniff thread stopped ({interface})")
    
    def start_capture(self):
        """Запустить захват пакетов на всех интерфейсах"""
        if self.running:
            self._log("Already running")
            return
        
        self._log(f"Starting capture on interfaces: {self.interfaces}")
        
        self.start_time = time.time()
        self.last_bandwidth_check = time.time()
        self.stop_sniffing.clear()
        self.running = True
        
        try:
            # Запускаем отдельный поток для каждого интерфейса
            for iface in self.interfaces:
                thread = threading.Thread(
                    target=self._sniff_thread,
                    args=(iface,),
                    daemon=True,
                    name=f"Sniffer-{iface}"
                )
                thread.start()
                self.capture_threads.append(thread)
                self._log(f"Started thread for {iface}")
            
            time.sleep(0.1)
            self._log(f"Capture started on {len(self.capture_threads)} interfaces")
            
        except Exception as e:
            self._log(f"Error starting capture: {e}")
            self.running = False
    
    def stop_capture(self):
        """Остановить захват пакетов на всех интерфейсах"""
        if not self.running:
            self._log("Not running")
            return
        
        self._log("Stopping capture...")
        
        try:
            # Сигнализируем всем потокам об остановке
            self.stop_sniffing.set()
            self.running = False
            
            # Ждем завершения всех потоков
            for thread in self.capture_threads:
                if thread.is_alive():
                    thread.join(timeout=2.0)
            
            self.capture_threads.clear()
            self._log("Capture stopped")
            
        except Exception as e:
            self._log(f"Error stopping capture: {e}")
    
    def get_packets(self):
        """Получить список захваченных пакетов (thread-safe)"""
        with self.lock:
            return list(self.packets)
    
    def clear_packets(self):
        """Очистить буфер пакетов"""
        with self.lock:
            self.packets.clear()
            self.packet_counter = 0
            self.total_bytes = 0
            self.bytes_last_second = 0
            self.current_bandwidth = 0
            self.packet_loss_count = 0
            self.tcp_sequence_tracker.clear()
            self.latency_samples.clear()
            self._log("Buffer cleared")
    
    def get_bandwidth(self):
        """Получить текущую пропускную способность в bytes/sec"""
        return self.current_bandwidth
    
    def get_bandwidth_mbps(self):
        """Получить пропускную способность в Mbps"""
        return (self.current_bandwidth * 8) / 1_000_000
    
    def get_average_latency(self):
        """Получить среднюю latency в микросекундах"""
        if not self.latency_samples:
            return None
        return sum(self.latency_samples) / len(self.latency_samples)
    
    def get_packet_loss_count(self):
        """Получить количество обнаруженных потерянных пакетов"""
        return self.packet_loss_count
    
    def get_statistics(self):
        """Получить полную статистику захвата"""
        with self.lock:
            uptime = time.time() - self.start_time if self.start_time else 0
            
            return {
                'total_packets': self.packet_counter,
                'buffer_size': len(self.packets),
                'buffer_limit': self.packet_limit,
                'total_bytes': self.total_bytes,
                'bandwidth_bps': self.current_bandwidth,
                'bandwidth_mbps': self.get_bandwidth_mbps(),
                'uptime_seconds': uptime,
                'avg_latency_us': self.get_average_latency(),
                'packet_loss_count': self.packet_loss_count,
                'active_threads': len([t for t in self.capture_threads if t.is_alive()]),
            }


def main():
    """Тестирование модуля"""
    print("=" * 70)
    print("Packet Monitor - Block 1: Multi-Interface Capture (FIXED)")
    print("=" * 70)
    
    # Тест с 'any' - все интерфейсы
    capture = PacketCapture(interface='any', log_file='/tmp/packet_capture.log')
    
    print(f"\nCapturing on interfaces: {capture.interfaces}")
    print(f"Buffer limit: {capture.packet_limit} packets")
    print(f"Log file: /tmp/packet_capture.log")
    
    capture.start_capture()
    
    if not capture.running:
        print("\n[ERROR] Failed to start capture. Run with sudo!")
        return
    
    try:
        print("\nCapturing packets for 10 seconds...")
        print("Press Ctrl+C to stop early\n")
        
        for i in range(10):
            time.sleep(1)
            stats = capture.get_statistics()
            
            print(f"[{i+1}s] Packets: {stats['total_packets']} | "
                  f"Threads: {stats['active_threads']} | "
                  f"Bandwidth: {stats['bandwidth_mbps']:.2f} Mbps | "
                  f"Buffer: {stats['buffer_size']}/{stats['buffer_limit']}")
        
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    
    finally:
        capture.stop_capture()
        
        stats = capture.get_statistics()
        packets = capture.get_packets()
        
        print("\n" + "=" * 70)
        print("FINAL STATISTICS")
        print("=" * 70)
        print(f"Total packets captured: {stats['total_packets']}")
        print(f"Interfaces monitored: {len(capture.interfaces)}")
        
        # Показываем статистику по интерфейсам
        if packets:
            iface_counts = {}
            for pkt in packets:
                iface = str(pkt.get('interface', 'unknown'))
                iface_counts[iface] = iface_counts.get(iface, 0) + 1
            
            print("\nPackets per interface:")
            for iface, count in sorted(iface_counts.items()):
                print(f"  {iface}: {count} packets")


if __name__ == '__main__':
    main()
