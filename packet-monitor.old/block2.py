#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Packet Monitor - Block 2: Packet Filter (with Exclude Streams & Protocols)
Фильтрация пакетов с поддержкой исключения стримов и протоколов
"""

import re
from collections import defaultdict


class PacketFilter:
    """Фильтрация пакетов с поддержкой исключений"""
    
    def __init__(self):
        self.filters = {}
        self.exclude_streams = []  # Список исключенных стримов
        self.exclude_protocols = set()  # Множество исключенных протоколов
    
    def set_filter(self, field, value):
        """Установить фильтр для поля"""
        if value:
            self.filters[field] = value
        elif field in self.filters:
            del self.filters[field]
    
    def clear_filter(self):
        """Очистить все фильтры (кроме exclude)"""
        self.filters.clear()
    
    def add_exclude_stream(self, src_ip, dst_ip, src_port, dst_port, proto):
        """
        Добавить stream в список исключений
        
        Args:
            src_ip, dst_ip: IP адреса
            src_port, dst_port: порты
            proto: протокол (TCP/UDP)
        
        Returns:
            True если добавлен, False если уже существует
        """
        stream = {
            'src_ip': src_ip,
            'dst_ip': dst_ip,
            'src_port': src_port,
            'dst_port': dst_port,
            'proto': proto
        }
        
        # Проверяем что такой stream еще не исключен
        if not self._is_stream_excluded(stream):
            self.exclude_streams.append(stream)
            return True
        return False
    
    def clear_exclude_streams(self):
        """Очистить все исключения стримов"""
        self.exclude_streams.clear()
    
    def add_exclude_protocol(self, protocol):
        """
        Добавить протокол в список исключений
        
        Args:
            protocol: название протокола (ARP, ICMP, DNS, etc)
        
        Returns:
            True если добавлен, False если уже существует
        """
        protocol = protocol.upper()
        if protocol not in self.exclude_protocols:
            self.exclude_protocols.add(protocol)
            return True
        return False
    
    def clear_exclude_protocols(self):
        """Очистить все исключенные протоколы"""
        self.exclude_protocols.clear()
    
    def _is_stream_excluded(self, stream):
        """Проверить, исключен ли уже этот stream"""
        for excl in self.exclude_streams:
            if (excl['src_ip'] == stream['src_ip'] and
                excl['dst_ip'] == stream['dst_ip'] and
                excl['src_port'] == stream['src_port'] and
                excl['dst_port'] == stream['dst_port'] and
                excl['proto'] == stream['proto']):
                return True
        return False
    
    def _match_excluded_stream(self, packet):
        """Проверить, попадает ли пакет в исключенные стримы (bidirectional)"""
        pkt_src_ip = packet.get('src_ip')
        pkt_dst_ip = packet.get('dst_ip')
        pkt_src_port = packet.get('src_port')
        pkt_dst_port = packet.get('dst_port')
        pkt_proto = packet.get('proto', '').upper()
        
        if not all([pkt_src_ip, pkt_dst_ip, pkt_src_port, pkt_dst_port]):
            return False
        
        # Нормализуем протокол (TCP/TCPv6 -> TCP)
        if 'TCP' in pkt_proto:
            pkt_proto = 'TCP'
        elif 'UDP' in pkt_proto:
            pkt_proto = 'UDP'
        else:
            return False
        
        for excl in self.exclude_streams:
            # Проверяем bidirectional match
            forward_match = (
                excl['src_ip'] == pkt_src_ip and
                excl['dst_ip'] == pkt_dst_ip and
                excl['src_port'] == pkt_src_port and
                excl['dst_port'] == pkt_dst_port and
                excl['proto'] == pkt_proto
            )
            
            reverse_match = (
                excl['src_ip'] == pkt_dst_ip and
                excl['dst_ip'] == pkt_src_ip and
                excl['src_port'] == pkt_dst_port and
                excl['dst_port'] == pkt_src_port and
                excl['proto'] == pkt_proto
            )
            
            if forward_match or reverse_match:
                return True
        
        return False
    
    def get_active_filters(self):
        """Получить активные фильтры"""
        return self.filters.copy()
    
    def get_exclude_count(self):
        """Получить количество исключенных стримов"""
        return len(self.exclude_streams)
    
    def get_exclude_summary(self):
        """Получить краткую информацию об исключениях"""
        if not self.exclude_streams:
            return ""
        
        summary_parts = []
        for i, excl in enumerate(self.exclude_streams[:3], 1):
            summary_parts.append(
                f"{excl['src_ip']}:{excl['src_port']}↔{excl['dst_ip']}:{excl['dst_port']}"
            )
        
        if len(self.exclude_streams) > 3:
            summary_parts.append(f"...+{len(self.exclude_streams) - 3} more")
        
        return ", ".join(summary_parts)
    
    def filter_packets(self, packets):
        """
        Фильтровать список пакетов
        
        Args:
            packets: список пакетов
            
        Returns:
            отфильтрованный список
        """
        if not self.filters and not self.exclude_streams and not self.exclude_protocols:
            return packets
        
        filtered = []
        
        for packet in packets:
            # Проверяем исключенные протоколы
            proto = packet.get('proto', '').upper()
            if proto in self.exclude_protocols:
                continue
            
            # Затем проверяем исключенные стримы
            if self._match_excluded_stream(packet):
                continue
            
            # Затем применяем обычные фильтры
            if self._match_packet(packet):
                filtered.append(packet)
        
        return filtered
    
    def _match_packet(self, packet):
        """Проверить соответствие пакета фильтрам"""
        if not self.filters:
            return True
        
        for field, pattern in self.filters.items():
            if field == 'payload':
                if not self._match_payload(packet, pattern):
                    return False
            else:
                packet_value = str(packet.get(field, ''))
                
                if not packet_value:
                    return False
                
                # Регулярное выражение или простое совпадение
                try:
                    if not re.search(pattern, packet_value, re.IGNORECASE):
                        return False
                except re.error:
                    if pattern.lower() not in packet_value.lower():
                        return False
        
        return True
    
    def _match_payload(self, packet, pattern):
        """Поиск в payload пакета"""
        raw_data = packet.get('raw', b'')
        
        if not raw_data:
            return False
        
        try:
            # Пробуем как регулярное выражение
            pattern_bytes = pattern.encode('utf-8', errors='ignore')
            if re.search(pattern_bytes, raw_data, re.IGNORECASE):
                return True
        except:
            pass
        
        try:
            # Пробуем простой поиск
            if pattern.lower().encode('utf-8') in raw_data.lower():
                return True
        except:
            pass
        
        return False
    
    def search_payload(self, packets, search_string, case_sensitive=False):
        """
        Поиск по payload
        
        Args:
            packets: список пакетов
            search_string: строка для поиска
            case_sensitive: учитывать регистр
            
        Returns:
            список найденных пакетов
        """
        results = []
        
        for packet in packets:
            raw_data = packet.get('raw', b'')
            
            if not raw_data:
                continue
            
            try:
                if case_sensitive:
                    pattern = search_string.encode('utf-8')
                    if re.search(pattern, raw_data):
                        results.append(packet)
                else:
                    pattern = search_string.encode('utf-8')
                    if re.search(pattern, raw_data, re.IGNORECASE):
                        results.append(packet)
            except:
                continue
        
        return results
    
    def get_filter_summary(self):
        """Получить краткое описание активных фильтров"""
        if not self.filters and not self.exclude_streams and not self.exclude_protocols:
            return "No filters active"
        
        parts = []
        
        # Обычные фильтры
        for field, value in self.filters.items():
            parts.append(f"{field}={value}")
        
        # Исключения стримов
        if self.exclude_streams:
            parts.append(f"ExclStreams:{len(self.exclude_streams)}")
        
        # Исключения протоколов
        if self.exclude_protocols:
            parts.append(f"ExclProtos:{len(self.exclude_protocols)}")
        
        return " | ".join(parts) if parts else "No filters active"
    
    def get_top_ips(self, packets, limit=10):
        """Получить топ IP адресов по количеству пакетов"""
        ip_counter = defaultdict(int)
        
        for packet in packets:
            src_ip = packet.get('src_ip')
            dst_ip = packet.get('dst_ip')
            
            if src_ip:
                ip_counter[src_ip] += 1
            if dst_ip:
                ip_counter[dst_ip] += 1
        
        return sorted(ip_counter.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    def get_top_talkers(self, packets, limit=10):
        """Получить топ IP адресов по объему трафика"""
        ip_bytes = defaultdict(int)
        
        for packet in packets:
            size = packet.get('size', 0)
            src_ip = packet.get('src_ip')
            dst_ip = packet.get('dst_ip')
            
            if src_ip:
                ip_bytes[src_ip] += size
            if dst_ip:
                ip_bytes[dst_ip] += size
        
        return sorted(ip_bytes.items(), key=lambda x: x[1], reverse=True)[:limit]


def main():
    """Тестирование модуля"""
    print("=" * 70)
    print("Packet Filter - Block 2 (with Exclude Streams & Protocols)")
    print("=" * 70)
    
    # Тестовые данные
    test_packets = [
        {'num': 1, 'proto': 'TCP', 'src_ip': '192.168.1.10', 'dst_ip': '8.8.8.8', 
         'src_port': 1234, 'dst_port': 443, 'info': 'SYN', 'size': 60},
        {'num': 2, 'proto': 'TCP', 'src_ip': '8.8.8.8', 'dst_ip': '192.168.1.10',
         'src_port': 443, 'dst_port': 1234, 'info': 'SYN-ACK', 'size': 60},
        {'num': 3, 'proto': 'UDP', 'src_ip': '192.168.1.10', 'dst_ip': '1.1.1.1',
         'src_port': 5678, 'dst_port': 53, 'info': 'DNS Query', 'size': 72},
        {'num': 4, 'proto': 'ARP', 'src_ip': '192.168.1.1', 'dst_ip': '192.168.1.10',
         'src_port': None, 'dst_port': None, 'info': 'Who has?', 'size': 42},
        {'num': 5, 'proto': 'ICMP', 'src_ip': '192.168.1.10', 'dst_ip': '8.8.8.8',
         'src_port': None, 'dst_port': None, 'info': 'Echo Request', 'size': 84},
    ]
    
    pfilter = PacketFilter()
    
    print("\nТест 1: Без фильтров")
    result = pfilter.filter_packets(test_packets)
    print(f"  Результат: {len(result)} пакетов (должно быть 5)")
    
    print("\nТест 2: Exclude stream 192.168.1.10:1234 <-> 8.8.8.8:443")
    added = pfilter.add_exclude_stream('192.168.1.10', '8.8.8.8', 1234, 443, 'TCP')
    print(f"  Added: {added}")
    result = pfilter.filter_packets(test_packets)
    print(f"  Результат: {len(result)} пакетов (должно быть 3)")
    print(f"  Summary: {pfilter.get_filter_summary()}")
    
    print("\nТест 3: Exclude protocol ARP")
    added = pfilter.add_exclude_protocol('ARP')
    print(f"  Added: {added}")
    result = pfilter.filter_packets(test_packets)
    print(f"  Результат: {len(result)} пакетов (должно быть 2 - UDP и ICMP)")
    print(f"  Summary: {pfilter.get_filter_summary()}")
    
    for pkt in result:
        print(f"    #{pkt['num']}: {pkt['proto']} - {pkt['info']}")
    
    print("\nТест 4: Clear all exclusions")
    pfilter.clear_exclude_streams()
    pfilter.clear_exclude_protocols()
    result = pfilter.filter_packets(test_packets)
    print(f"  Результат: {len(result)} пакетов (должно быть 5)")
    
    print("\n✓ Все тесты пройдены")


if __name__ == '__main__':
    main()
