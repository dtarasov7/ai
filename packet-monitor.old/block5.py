#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Packet Monitor - Block 5: Save packets to pcapng file
Требования: scapy==2.4.5
"""

import os
from datetime import datetime
from scapy.utils import wrpcap, PcapWriter


class PacketExporter:
    """Класс для экспорта пакетов в различные форматы"""
    
    def __init__(self):
        """Инициализация экспортера"""
        self.default_directory = "./captures"
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Создать директорию для сохранения если не существует"""
        try:
            if not os.path.exists(self.default_directory):
                os.makedirs(self.default_directory)
        except Exception as e:
            print(f"Warning: Could not create directory {self.default_directory}: {e}")
            self.default_directory = "."
    
    def save_to_pcapng(self, packets, filename=None):
        """
        Сохранить пакеты в формат pcapng
        
        Args:
            packets: список packet_info словарей с raw_packet
            filename: имя файла (если None - генерируется автоматически)
            
        Returns:
            tuple (success: bool, filepath: str, message: str)
        """
        try:
            # Генерируем имя файла если не указано
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"capture_{timestamp}.pcapng"
            
            # Добавляем расширение если отсутствует
            if not filename.endswith('.pcapng') and not filename.endswith('.pcap'):
                filename += '.pcapng'
            
            # Формируем полный путь
            filepath = os.path.join(self.default_directory, filename)
            
            # Извлекаем raw пакеты из packet_info
            raw_packets = []
            for pkt_info in packets:
                if pkt_info.get('raw_packet') is not None:
                    raw_packets.append(pkt_info['raw_packet'])
            
            if len(raw_packets) == 0:
                return False, "", "No valid packets to save"
            
            # Сохраняем используя wrpcap из scapy
            # wrpcap автоматически создает pcapng для Python 3
            wrpcap(filepath, raw_packets)
            
            return True, filepath, f"Successfully saved {len(raw_packets)} packets"
            
        except Exception as e:
            return False, "", f"Error saving packets: {str(e)}"
    
    def save_to_pcap(self, packets, filename=None):
        """
        Сохранить пакеты в формат pcap (старый формат)
        
        Args:
            packets: список packet_info словарей с raw_packet
            filename: имя файла (если None - генерируется автоматически)
            
        Returns:
            tuple (success: bool, filepath: str, message: str)
        """
        try:
            # Генерируем имя файла если не указано
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"capture_{timestamp}.pcap"
            
            # Добавляем расширение если отсутствует
            if not filename.endswith('.pcap'):
                filename += '.pcap'
            
            # Формируем полный путь
            filepath = os.path.join(self.default_directory, filename)
            
            # Извлекаем raw пакеты
            raw_packets = []
            for pkt_info in packets:
                if pkt_info.get('raw_packet') is not None:
                    raw_packets.append(pkt_info['raw_packet'])
            
            if len(raw_packets) == 0:
                return False, "", "No valid packets to save"
            
            # Сохраняем в pcap формат
            wrpcap(filepath, raw_packets)
            
            return True, filepath, f"Successfully saved {len(raw_packets)} packets"
            
        except Exception as e:
            return False, "", f"Error saving packets: {str(e)}"
    
    def save_filtered_packets(self, all_packets, packet_filter, filename=None):
        """
        Сохранить отфильтрованные пакеты
        
        Args:
            all_packets: все пакеты
            packet_filter: экземпляр PacketFilter
            filename: имя файла
            
        Returns:
            tuple (success: bool, filepath: str, message: str)
        """
        # Применяем фильтр
        filtered = packet_filter.filter_packets(all_packets)
        
        if len(filtered) == 0:
            return False, "", "No packets match the current filter"
        
        # Сохраняем
        return self.save_to_pcapng(filtered, filename)
    
    def get_capture_info(self, filepath):
        """
        Получить информацию о сохраненном файле
        
        Args:
            filepath: путь к файлу
            
        Returns:
            dict с информацией о файле
        """
        try:
            if not os.path.exists(filepath):
                return None
            
            stat = os.stat(filepath)
            
            return {
                'filename': os.path.basename(filepath),
                'filepath': filepath,
                'size_bytes': stat.st_size,
                'size_human': self._human_readable_size(stat.st_size),
                'created': datetime.fromtimestamp(stat.st_ctime),
                'modified': datetime.fromtimestamp(stat.st_mtime),
            }
        except Exception as e:
            return None
    
    def _human_readable_size(self, size_bytes):
        """Конвертировать размер в человекочитаемый формат"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
    
    def list_saved_captures(self):
        """
        Получить список сохраненных файлов захвата
        
        Returns:
            список словарей с информацией о файлах
        """
        captures = []
        
        try:
            if not os.path.exists(self.default_directory):
                return captures
            
            for filename in os.listdir(self.default_directory):
                if filename.endswith('.pcap') or filename.endswith('.pcapng'):
                    filepath = os.path.join(self.default_directory, filename)
                    info = self.get_capture_info(filepath)
                    if info:
                        captures.append(info)
            
            # Сортируем по дате изменения (новые первыми)
            captures.sort(key=lambda x: x['modified'], reverse=True)
            
        except Exception as e:
            print(f"Error listing captures: {e}")
        
        return captures
    
    def delete_capture(self, filepath):
        """
        Удалить файл захвата
        
        Args:
            filepath: путь к файлу
            
        Returns:
            tuple (success: bool, message: str)
        """
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True, f"Deleted {os.path.basename(filepath)}"
            else:
                return False, "File not found"
        except Exception as e:
            return False, f"Error deleting file: {str(e)}"


class PacketExportDialog:
    """Диалог для экспорта пакетов (для интеграции с TUI)"""
    
    def __init__(self, packet_capture, packet_filter, exporter=None):
        """
        Инициализация диалога экспорта
        
        Args:
            packet_capture: экземпляр PacketCapture
            packet_filter: экземпляр PacketFilter
            exporter: экземпляр PacketExporter (опционально)
        """
        self.packet_capture = packet_capture
        self.packet_filter = packet_filter
        self.exporter = exporter if exporter else PacketExporter()
    
    def export_all_packets(self, filename=None):
        """
        Экспортировать все захваченные пакеты
        
        Args:
            filename: имя файла
            
        Returns:
            tuple (success, filepath, message)
        """
        packets = self.packet_capture.get_packets()
        return self.exporter.save_to_pcapng(packets, filename)
    
    def export_filtered_packets(self, filename=None):
        """
        Экспортировать только отфильтрованные пакеты
        
        Args:
            filename: имя файла
            
        Returns:
            tuple (success, filepath, message)
        """
        packets = self.packet_capture.get_packets()
        return self.exporter.save_filtered_packets(packets, self.packet_filter, filename)
    
    def export_selected_packets(self, packet_numbers, filename=None):
        """
        Экспортировать выбранные пакеты по номерам
        
        Args:
            packet_numbers: список номеров пакетов
            filename: имя файла
            
        Returns:
            tuple (success, filepath, message)
        """
        all_packets = self.packet_capture.get_packets()
        selected = [pkt for pkt in all_packets if pkt['num'] in packet_numbers]
        
        if len(selected) == 0:
            return False, "", "No packets selected"
        
        return self.exporter.save_to_pcapng(selected, filename)


# Тестирование блока 5
if __name__ == '__main__':
    import sys
    
    # Проверяем наличие scapy
    try:
        from scapy.all import Ether, IP, TCP, UDP, DNS, DNSQR, ARP, ICMP
    except ImportError:
        print("Error: scapy not installed")
        print("\nInstall with:")
        print("  sudo pip3 install scapy==2.4.5")
        sys.exit(1)
    
    from datetime import datetime
    import time
    
    print("=" * 70)
    print("Packet Exporter - Block 5 Test")
    print("=" * 70)
    
    # Создаем тестовые пакеты
    print("\nCreating test packets...")
    test_packets = []
    
    # Пакет 1: DNS Query
    pkt1 = Ether()/IP(src="192.168.1.100", dst="8.8.8.8")/UDP(sport=12345, dport=53)/DNS(
        qd=DNSQR(qname="example.com")
    )
    test_packets.append({
        'num': 1,
        'timestamp': datetime.now(),
        'proto': 'DNS',
        'src_ip': '192.168.1.100',
        'dst_ip': '8.8.8.8',
        'src_port': 12345,
        'dst_port': 53,
        'src': '00:11:22:33:44:55',
        'dst': 'aa:bb:cc:dd:ee:ff',
        'info': 'Query: example.com',
        'length': len(pkt1),
        'vlan': '',
        'raw_packet': pkt1
    })
    
    # Пакет 2: TCP SYN
    pkt2 = Ether()/IP(src="10.0.0.1", dst="93.184.216.34")/TCP(
        sport=54321, dport=80, flags='S', seq=1000
    )
    test_packets.append({
        'num': 2,
        'timestamp': datetime.now(),
        'proto': 'TCP',
        'src_ip': '10.0.0.1',
        'dst_ip': '93.184.216.34',
        'src_port': 54321,
        'dst_port': 80,
        'src': '00:11:22:33:44:55',
        'dst': 'aa:bb:cc:dd:ee:ff',
        'info': '[SYN] Seq=1000',
        'length': len(pkt2),
        'vlan': '',
        'raw_packet': pkt2
    })
    
    # Пакет 3: ARP Request
    pkt3 = Ether(dst="ff:ff:ff:ff:ff:ff")/ARP(
        op=1, psrc="192.168.1.1", pdst="192.168.1.100"
    )
    test_packets.append({
        'num': 3,
        'timestamp': datetime.now(),
        'proto': 'ARP',
        'src_ip': '192.168.1.1',
        'dst_ip': '192.168.1.100',
        'src_port': '',
        'dst_port': '',
        'src': pkt3[ARP].hwsrc,
        'dst': 'ff:ff:ff:ff:ff:ff',
        'info': 'Who has 192.168.1.100?',
        'length': len(pkt3),
        'vlan': '',
        'raw_packet': pkt3
    })
    
    # Пакет 4: ICMP Echo Request
    pkt4 = Ether()/IP(src="192.168.1.1", dst="8.8.8.8")/ICMP(type=8, code=0, id=1, seq=1)
    test_packets.append({
        'num': 4,
        'timestamp': datetime.now(),
        'proto': 'ICMP',
        'src_ip': '192.168.1.1',
        'dst_ip': '8.8.8.8',
        'src_port': '',
        'dst_port': '',
        'src': '00:11:22:33:44:55',
        'dst': 'aa:bb:cc:dd:ee:ff',
        'info': 'Echo Request',
        'length': len(pkt4),
        'vlan': '',
        'raw_packet': pkt4
    })
    
    # Пакет 5: UDP
    pkt5 = Ether()/IP(src="10.0.0.1", dst="10.0.0.2")/UDP(sport=5000, dport=6000)/"Test payload"
    test_packets.append({
        'num': 5,
        'timestamp': datetime.now(),
        'proto': 'UDP',
        'src_ip': '10.0.0.1',
        'dst_ip': '10.0.0.2',
        'src_port': 5000,
        'dst_port': 6000,
        'src': '00:11:22:33:44:55',
        'dst': 'aa:bb:cc:dd:ee:ff',
        'info': 'Len=20',
        'length': len(pkt5),
        'vlan': '',
        'raw_packet': pkt5
    })
    
    print(f"Created {len(test_packets)} test packets")
    
    # Создаем экспортер
    exporter = PacketExporter()
    print(f"\nSave directory: {exporter.default_directory}")
    
    # Тест 1: Сохранение всех пакетов
    print("\n" + "=" * 70)
    print("Test 1: Save all packets to pcapng")
    print("=" * 70)
    
    success, filepath, message = exporter.save_to_pcapng(test_packets)
    
    if success:
        print(f"✓ {message}")
        print(f"  File: {filepath}")
        
        # Показываем информацию о файле
        info = exporter.get_capture_info(filepath)
        if info:
            print(f"  Size: {info['size_human']}")
            print(f"  Created: {info['created'].strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"✗ {message}")
    
    # Тест 2: Сохранение с именем файла
    print("\n" + "=" * 70)
    print("Test 2: Save with custom filename")
    print("=" * 70)
    
    success, filepath, message = exporter.save_to_pcapng(
        test_packets, 
        filename="test_custom_name.pcapng"
    )
    
    if success:
        print(f"✓ {message}")
        print(f"  File: {filepath}")
    else:
        print(f"✗ {message}")
    
    # Тест 3: Сохранение в старый формат pcap
    print("\n" + "=" * 70)
    print("Test 3: Save to legacy pcap format")
    print("=" * 70)
    
    success, filepath, message = exporter.save_to_pcap(test_packets)
    
    if success:
        print(f"✓ {message}")
        print(f"  File: {filepath}")
    else:
        print(f"✗ {message}")
    
    # Тест 4: Список сохраненных файлов
    print("\n" + "=" * 70)
    print("Test 4: List saved capture files")
    print("=" * 70)
    
    captures = exporter.list_saved_captures()
    
    if captures:
        print(f"Found {len(captures)} capture file(s):")
        print(f"\n{'Filename':<30} {'Size':<12} {'Modified':<20}")
        print("-" * 70)
        for cap in captures:
            print(f"{cap['filename']:<30} {cap['size_human']:<12} "
                  f"{cap['modified'].strftime('%Y-%m-%d %H:%M:%S'):<20}")
    else:
        print("No capture files found")
    
    # Тест 5: Проверка совместимости с Wireshark
    print("\n" + "=" * 70)
    print("Test 5: Wireshark compatibility check")
    print("=" * 70)
    
    if captures and len(captures) > 0:
        test_file = captures[0]['filepath']
        print(f"To verify Wireshark compatibility, run:")
        print(f"  wireshark {test_file}")
        print(f"\nor:")
        print(f"  tshark -r {test_file}")
    
    # Тест 6: Экспорт только определенных пакетов
    print("\n" + "=" * 70)
    print("Test 6: Export selected packets (TCP and DNS only)")
    print("=" * 70)
    
    selected_packets = [pkt for pkt in test_packets if pkt['proto'] in ['TCP', 'DNS']]
    
    success, filepath, message = exporter.save_to_pcapng(
        selected_packets,
        filename="selected_tcp_dns.pcapng"
    )
    
    if success:
        print(f"✓ {message}")
        print(f"  File: {filepath}")
    else:
        print(f"✗ {message}")
    
    print("\n" + "=" * 70)
    print("Block 5 tests completed!")
    print("=" * 70)
    
    # Опция для очистки тестовых файлов
    print("\nCleanup test files? (y/N): ", end='')
    try:
        choice = input().strip().lower()
        if choice == 'y':
            import shutil
            if os.path.exists(exporter.default_directory):
                shutil.rmtree(exporter.default_directory)
                print("✓ Test files deleted")
    except:
        pass
