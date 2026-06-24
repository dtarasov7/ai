#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Packet Monitor - Block 4: Packet detail view (FIXED)
Требования: scapy==2.4.5, urwid
"""

import urwid
import io
import sys
from scapy.all import Packet
from scapy.layers.l2 import Ether, ARP, Dot1Q
from scapy.layers.inet import IP, TCP, UDP, ICMP
from scapy.layers.inet6 import IPv6
from scapy.layers.dns import DNS, DNSQR, DNSRR


def safe_str(value, default='N/A'):
    """Безопасное преобразование в строку"""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


class PacketDetailView(urwid.WidgetWrap):
    """Виджет для детального просмотра пакета"""
    
    def __init__(self, packet_info, on_close_callback=None):
        """
        Инициализация детального просмотра
        
        Args:
            packet_info: информация о пакете из PacketCapture
            on_close_callback: функция для вызова при закрытии
        """
        self.packet_info = packet_info
        self.on_close_callback = on_close_callback
        
        # Создаем контент
        content = self._create_content()
        
        # Оборачиваем в LineBox с заголовком
        title = f"Packet #{packet_info['num']} Details - Press ESC to close"
        boxed_content = urwid.LineBox(content, title=title)
        
        super().__init__(urwid.AttrMap(boxed_content, 'detail_box'))
    
    def _create_content(self):
        """Создать содержимое детального просмотра"""
        widgets = []
        
        # === Секция 1: Основная информация ===
        widgets.append(urwid.AttrMap(
            urwid.Text(('detail_header', '═══ Packet Summary ═══')),
            'detail_header'
        ))
        
        summary_text = [
            f"Packet Number:  {self.packet_info['num']}",
            f"Timestamp:      {self.packet_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}",
            f"Interface:      {safe_str(self.packet_info.get('interface'), 'N/A')}",
            f"Length:         {self.packet_info.get('size', self.packet_info.get('length', 0))} bytes",
            f"Protocol:       {self.packet_info['proto']}",
        ]
        
        if self.packet_info.get('vlan'):
            summary_text.append(f"VLAN ID:        {self.packet_info['vlan']}")
        
        if self.packet_info.get('packet_loss'):
            summary_text.append("⚠ PACKET LOSS DETECTED")
        
        widgets.append(urwid.Text('\n'.join(summary_text)))
        widgets.append(urwid.Divider())
        
        # === Секция 2: Детали протоколов (разбор слоев) ===
        # Пытаемся восстановить Scapy packet из raw данных
        raw_packet = self.packet_info.get('raw_packet')
        
        if not raw_packet and self.packet_info.get('raw'):
            # Пытаемся создать Scapy packet из raw bytes
            try:
                from scapy.all import Ether
                raw_packet = Ether(self.packet_info['raw'])
            except:
                raw_packet = None
        
        if raw_packet:
            widgets.append(urwid.AttrMap(
                urwid.Text(('detail_header', '═══ Protocol Layers ═══')),
                'detail_header'
            ))
            
            layer_details = self._parse_protocol_layers(raw_packet)
            widgets.append(urwid.Text(layer_details))
            widgets.append(urwid.Divider())
        
        # === Секция 3: Hexdump ===
        widgets.append(urwid.AttrMap(
            urwid.Text(('detail_header', '═══ Hexdump ═══')),
            'detail_header'
        ))
        
        hexdump_text = self._create_hexdump(raw_packet if raw_packet else self.packet_info.get('raw'))
        widgets.append(urwid.Text(('hexdump', hexdump_text)))
        
        # Создаем прокручиваемый список
        listwalker = urwid.SimpleFocusListWalker(widgets)
        listbox = urwid.ListBox(listwalker)
        
        return listbox
    
    def _parse_protocol_layers(self, packet):
        """
        Разбор слоев протокола пакета
        
        Args:
            packet: scapy packet объект
            
        Returns:
            строка с детальной информацией о слоях
        """
        if not packet:
            return "No packet data available"
        
        output = []
        
        try:
            # Используем встроенный метод show() из scapy
            # Перехватываем stdout для получения текста
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            
            packet.show()
            
            result = sys.stdout.getvalue()
            sys.stdout = old_stdout
            
            # Форматируем вывод
            if result:
                return result
                
        except Exception as e:
            if 'old_stdout' in locals():
                sys.stdout = old_stdout
            output.append(f"Error parsing packet: {e}")
        
        # Если show() не сработал, делаем ручной разбор
        if not output or len(output) == 0:
            output = self._manual_layer_parse(packet)
        
        return '\n'.join(output) if output else "Unable to parse packet layers"
    
    def _manual_layer_parse(self, packet):
        """Ручной разбор слоев пакета"""
        output = []
        
        try:
            # Ethernet Layer
            if packet.haslayer(Ether):
                eth = packet[Ether]
                output.append("### Ethernet II")
                output.append(f"  Source MAC:      {eth.src}")
                output.append(f"  Destination MAC: {eth.dst}")
                output.append(f"  EtherType:       0x{eth.type:04x}")
                output.append("")
            
            # VLAN Layer
            if packet.haslayer(Dot1Q):
                vlan = packet[Dot1Q]
                output.append("### 802.1Q VLAN")
                output.append(f"  VLAN ID:         {vlan.vlan}")
                output.append(f"  Priority:        {vlan.prio}")
                output.append("")
            
            # ARP Layer
            if packet.haslayer(ARP):
                arp = packet[ARP]
                output.append("### ARP (Address Resolution Protocol)")
                output.append(f"  Hardware Type:   {arp.hwtype}")
                output.append(f"  Protocol Type:   0x{arp.ptype:04x}")
                output.append(f"  Operation:       {['', 'Request', 'Reply'][arp.op] if arp.op <= 2 else arp.op}")
                output.append(f"  Sender MAC:      {arp.hwsrc}")
                output.append(f"  Sender IP:       {arp.psrc}")
                output.append(f"  Target MAC:      {arp.hwdst}")
                output.append(f"  Target IP:       {arp.pdst}")
                output.append("")
            
            # IP Layer
            if packet.haslayer(IP):
                ip = packet[IP]
                output.append("### IPv4")
                output.append(f"  Version:         {ip.version}")
                output.append(f"  Header Length:   {ip.ihl * 4} bytes")
                output.append(f"  TOS:             0x{ip.tos:02x}")
                output.append(f"  Total Length:    {ip.len}")
                output.append(f"  Identification:  {ip.id}")
                output.append(f"  Flags:           {ip.flags}")
                output.append(f"  Fragment Offset: {ip.frag}")
                output.append(f"  TTL:             {ip.ttl}")
                output.append(f"  Protocol:        {ip.proto}")
                output.append(f"  Checksum:        0x{ip.chksum:04x}")
                output.append(f"  Source IP:       {ip.src}")
                output.append(f"  Destination IP:  {ip.dst}")
                output.append("")
            
            # IPv6 Layer
            if packet.haslayer(IPv6):
                ipv6 = packet[IPv6]
                output.append("### IPv6")
                output.append(f"  Version:         {ipv6.version}")
                output.append(f"  Traffic Class:   {ipv6.tc}")
                output.append(f"  Flow Label:      {ipv6.fl}")
                output.append(f"  Payload Length:  {ipv6.plen}")
                output.append(f"  Next Header:     {ipv6.nh}")
                output.append(f"  Hop Limit:       {ipv6.hlim}")
                output.append(f"  Source IP:       {ipv6.src}")
                output.append(f"  Destination IP:  {ipv6.dst}")
                output.append("")
            
            # ICMP Layer
            if packet.haslayer(ICMP):
                icmp = packet[ICMP]
                output.append("### ICMP (Internet Control Message Protocol)")
                output.append(f"  Type:            {icmp.type}")
                output.append(f"  Code:            {icmp.code}")
                output.append(f"  Checksum:        0x{icmp.chksum:04x}")
                if hasattr(icmp, 'id'):
                    output.append(f"  ID:              {icmp.id}")
                if hasattr(icmp, 'seq'):
                    output.append(f"  Sequence:        {icmp.seq}")
                output.append("")
            
            # TCP Layer
            if packet.haslayer(TCP):
                tcp = packet[TCP]
                output.append("### TCP (Transmission Control Protocol)")
                output.append(f"  Source Port:     {tcp.sport}")
                output.append(f"  Destination Port:{tcp.dport}")
                output.append(f"  Sequence Number: {tcp.seq}")
                output.append(f"  Ack Number:      {tcp.ack}")
                output.append(f"  Data Offset:     {tcp.dataofs * 4} bytes")
                
                # TCP Flags
                flags = []
                if tcp.flags & 0x01: flags.append('FIN')
                if tcp.flags & 0x02: flags.append('SYN')
                if tcp.flags & 0x04: flags.append('RST')
                if tcp.flags & 0x08: flags.append('PSH')
                if tcp.flags & 0x10: flags.append('ACK')
                if tcp.flags & 0x20: flags.append('URG')
                if tcp.flags & 0x40: flags.append('ECE')
                if tcp.flags & 0x80: flags.append('CWR')
                
                output.append(f"  Flags:           0x{tcp.flags:02x} ({', '.join(flags)})")
                output.append(f"  Window Size:     {tcp.window}")
                output.append(f"  Checksum:        0x{tcp.chksum:04x}")
                output.append(f"  Urgent Pointer:  {tcp.urgptr}")
                output.append("")
            
            # UDP Layer
            if packet.haslayer(UDP):
                udp = packet[UDP]
                output.append("### UDP (User Datagram Protocol)")
                output.append(f"  Source Port:     {udp.sport}")
                output.append(f"  Destination Port:{udp.dport}")
                output.append(f"  Length:          {udp.len}")
                output.append(f"  Checksum:        0x{udp.chksum:04x}")
                output.append("")
            
            # DNS Layer
            if packet.haslayer(DNS):
                dns = packet[DNS]
                output.append("### DNS (Domain Name System)")
                output.append(f"  Transaction ID:  0x{dns.id:04x}")
                output.append(f"  Query/Response:  {'Response' if dns.qr else 'Query'}")
                output.append(f"  Opcode:          {dns.opcode}")
                output.append(f"  Questions:       {dns.qdcount}")
                output.append(f"  Answers:         {dns.ancount}")
                output.append(f"  Authority RRs:   {dns.nscount}")
                output.append(f"  Additional RRs:  {dns.arcount}")
                
                # DNS Queries
                if dns.qdcount > 0 and hasattr(dns, 'qd') and dns.qd:
                    output.append("")
                    output.append("  Queries:")
                    qname = dns.qd.qname
                    if isinstance(qname, bytes):
                        qname = qname.decode('utf-8', errors='ignore')
                    output.append(f"    Name:          {qname}")
                    output.append(f"    Type:          {dns.qd.qtype}")
                    output.append(f"    Class:         {dns.qd.qclass}")
                
                # DNS Answers
                if dns.ancount > 0 and hasattr(dns, 'an') and dns.an:
                    output.append("")
                    output.append("  Answers:")
                    ans = dns.an
                    count = 0
                    while ans and count < dns.ancount:
                        if hasattr(ans, 'rrname'):
                            rrname = ans.rrname
                            if isinstance(rrname, bytes):
                                rrname = rrname.decode('utf-8', errors='ignore')
                            output.append(f"    [{count+1}] {rrname}")
                        if hasattr(ans, 'rdata'):
                            output.append(f"         Data: {ans.rdata}")
                        ans = ans.payload if hasattr(ans, 'payload') else None
                        count += 1
                
                output.append("")
            
            # Raw payload
            if packet.haslayer('Raw'):
                from scapy.packet import Raw
                raw = packet[Raw]
                payload = bytes(raw.load)
                
                if len(payload) > 0:
                    output.append("### Raw Payload")
                    # Показываем первые 100 байт
                    preview = payload[:100]
                    
                    # Пытаемся декодировать как текст
                    try:
                        text = preview.decode('utf-8', errors='ignore')
                        if text.isprintable() or '\n' in text or '\r' in text:
                            output.append(f"  [Text Preview]")
                            for line in text.split('\n')[:5]:
                                output.append(f"    {line[:80]}")
                        else:
                            output.append(f"  [Binary Data - {len(payload)} bytes]")
                    except:
                        output.append(f"  [Binary Data - {len(payload)} bytes]")
                    
                    output.append("")
        
        except Exception as e:
            output.append(f"Error during manual parsing: {e}")
        
        return output
    
    def _create_hexdump(self, packet):
        """
        Создать hexdump пакета
        
        Args:
            packet: scapy packet объект или bytes
            
        Returns:
            строка с hexdump
        """
        if not packet:
            return "No packet data available"
        
        # Если это Scapy packet
        if hasattr(packet, 'show'):
            try:
                # Используем встроенный hexdump из scapy
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                
                from scapy.utils import hexdump
                hexdump(packet)
                
                result = sys.stdout.getvalue()
                sys.stdout = old_stdout
                
                return result if result else self._manual_hexdump(bytes(packet))
                
            except Exception as e:
                if 'old_stdout' in locals():
                    sys.stdout = old_stdout
                # Fallback на ручной hexdump
                return self._manual_hexdump(bytes(packet))
        
        # Если это bytes
        elif isinstance(packet, bytes):
            return self._manual_hexdump(packet)
        
        return "Unable to create hexdump"
    
    def _manual_hexdump(self, data):
        """
        Ручная реализация hexdump
        
        Args:
            data: bytes
            
        Returns:
            строка с hexdump
        """
        if not isinstance(data, bytes):
            try:
                data = bytes(data)
            except:
                return "Invalid data type for hexdump"
        
        lines = []
        
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            
            # Offset
            offset = f"{i:04x}"
            
            # Hex bytes
            hex_part = ' '.join(f"{b:02x}" for b in chunk)
            # Дополняем пробелами если неполная строка
            hex_part = hex_part.ljust(16 * 3 - 1)
            
            # ASCII representation
            ascii_part = ''.join(
                chr(b) if 32 <= b < 127 else '.'
                for b in chunk
            )
            
            lines.append(f"{offset}  {hex_part}  {ascii_part}")
        
        return '\n'.join(lines)
    
    def keypress(self, size, key):
        """Обработка нажатий клавиш"""
        if key == 'esc':
            if self.on_close_callback:
                self.on_close_callback()
            return None
        
        # Передаем остальные клавиши дальше (для прокрутки)
        return super().keypress(size, key)
