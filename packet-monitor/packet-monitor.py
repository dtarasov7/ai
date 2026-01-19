#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Packet Monitor - Block 6: Ultimate Edition v5.1 (FIXED - Full Working Version)
ИСПРАВЛЕНИЯ:
- Статистика выводится построчно (список виджетов)
- Info обрезается без переносов (wrap='clip')
- Exclude protocols работает
- Ширина панели статистики 43 символа
- IPv6 статистика опциональна
- Подавлен вывод scapy в stderr
- Исправлен SelectableText (без set_attr_map)
"""

import urwid
import sys
import signal
import argparse
from collections import defaultdict


def safe_str(value, default='N/A'):
    """Безопасное преобразование в строку"""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


class SelectableText(urwid.Text):
    """Selectable Text widget для ListBox с поддержкой wrap"""
    
    def __init__(self, markup, wrap='space'):
        super().__init__(markup, wrap=wrap)
        self._selectable = True
    
    def selectable(self):
        return self._selectable
    
    def keypress(self, size, key):
        return key


class StatisticsPanel(urwid.WidgetWrap):
    """Расширенная панель статистики справа - ПОЛНОСТЬЮ ИСПРАВЛЕНО"""
    
    def __init__(self, enable_ipv6_stats=False):
        self.enable_ipv6_stats = enable_ipv6_stats
        
        # Создаем SimpleFocusListWalker с пустым списком
        self.listwalker = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.listwalker)
        
        content = urwid.LineBox(
            self.listbox,
            title='Statistics'
        )
        
        super().__init__(urwid.AttrMap(content, 'stat_panel'))
    
    def update(self, packets, packet_filter, packet_capture):
        """Обновить статистику с расширенной информацией"""
        # Счетчики протоколов
        proto_count = defaultdict(int)
        ipv4_addrs = set()
        ipv6_addrs = set()
        tcp_flags = defaultdict(int)
        
        for pkt in packets:
            proto = pkt['proto']
            
            if 'TCP' in proto:
                if '::' in str(pkt.get('src_ip', '')) or '::' in str(pkt.get('dst_ip', '')):
                    proto_count['TCPv6'] += 1
                else:
                    proto_count['TCPv4'] += 1
            elif 'UDP' in proto:
                if '::' in str(pkt.get('src_ip', '')) or '::' in str(pkt.get('dst_ip', '')):
                    proto_count['UDPv6'] += 1
                else:
                    proto_count['UDPv4'] += 1
            elif proto == 'ARP':
                proto_count['ARP'] += 1
            elif proto == 'ICMP':
                proto_count['ICMP'] += 1
            elif proto == 'ICMPv6':
                proto_count['ICMPv6'] += 1
            else:
                proto_count[proto] += 1
            
            src_ip = pkt.get('src_ip')
            dst_ip = pkt.get('dst_ip')
            
            if src_ip:
                if ':' in src_ip and '.' not in src_ip:
                    ipv6_addrs.add(src_ip)
                elif '.' in src_ip:
                    ipv4_addrs.add(src_ip)
            
            if dst_ip:
                if ':' in dst_ip and '.' not in dst_ip:
                    ipv6_addrs.add(dst_ip)
                elif '.' in dst_ip:
                    ipv4_addrs.add(dst_ip)
            
            if 'TCP' in proto:
                info = pkt.get('info', '')
                if 'RST' in info:
                    tcp_flags['RST'] += 1
                if 'SYN' in info:
                    tcp_flags['SYN'] += 1
                if 'FIN' in info:
                    tcp_flags['FIN'] += 1
                if 'PSH' in info:
                    tcp_flags['PSH'] += 1
        
        stats = packet_capture.get_statistics()
        top_ips = packet_filter.get_top_ips(packets, limit=10)
        top_talkers = packet_filter.get_top_talkers(packets, limit=10)
        
        bw_mbps = stats.get('bandwidth_mbps', 0)
        bw_kbps = (stats.get('bandwidth_bps', 0) / 1000)
        avg_latency = stats.get('avg_latency_us')
        latency_str = f"{avg_latency:.0f} μs" if avg_latency else "N/A"
        packet_loss = stats.get('packet_loss_count', 0)
        excluded_streams = packet_filter.get_exclude_count()
        excluded_protos = len(packet_filter.exclude_protocols)
        
        # ИСПРАВЛЕНИЕ: Создаем СПИСОК виджетов
        widgets = []
        
        # Protocol Stats - ВСЕГДА ПОКАЗЫВАЕМ ВСЕ
        widgets.append(urwid.AttrMap(urwid.Text('═══ Protocol Stats ═══'), 'stat_title'))
        widgets.append(urwid.AttrMap(urwid.Text(f"TCPv4:  {proto_count.get('TCPv4', 0)}"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"UDPv4:  {proto_count.get('UDPv4', 0)}"), 'stat_label'))
        
        if self.enable_ipv6_stats:
            widgets.append(urwid.AttrMap(urwid.Text(f"TCPv6:  {proto_count.get('TCPv6', 0)}"), 'stat_label'))
            widgets.append(urwid.AttrMap(urwid.Text(f"UDPv6:  {proto_count.get('UDPv6', 0)}"), 'stat_label'))
        
        widgets.append(urwid.AttrMap(urwid.Text(f"ARP:    {proto_count.get('ARP', 0)}"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"ICMP:   {proto_count.get('ICMP', 0)}"), 'stat_label'))
        
        if self.enable_ipv6_stats:
            widgets.append(urwid.AttrMap(urwid.Text(f"ICMPv6: {proto_count.get('ICMPv6', 0)}"), 'stat_label'))
        
        # Unique IPs - ВСЕГДА ПОКАЗЫВАЕМ
        widgets.append(urwid.Divider())
        widgets.append(urwid.AttrMap(urwid.Text('═══ Unique IPs ═══'), 'stat_title'))
        widgets.append(urwid.AttrMap(urwid.Text(f"IPv4:   {len(ipv4_addrs)}"), 'stat_label'))
        
        if self.enable_ipv6_stats:
            widgets.append(urwid.AttrMap(urwid.Text(f"IPv6:   {len(ipv6_addrs)}"), 'stat_label'))
        
        # TCP Flags - ВСЕГДА ПОКАЗЫВАЕМ
        widgets.append(urwid.Divider())
        widgets.append(urwid.AttrMap(urwid.Text('═══ TCP Flags ═══'), 'stat_title'))
        widgets.append(urwid.AttrMap(urwid.Text(f"SYN:    {tcp_flags.get('SYN', 0)}"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"FIN:    {tcp_flags.get('FIN', 0)}"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"RST:    {tcp_flags.get('RST', 0)}"), 'stat_rst'))
        widgets.append(urwid.AttrMap(urwid.Text(f"PSH:    {tcp_flags.get('PSH', 0)}"), 'stat_label'))
        
        # Performance
        widgets.append(urwid.Divider())
        widgets.append(urwid.AttrMap(urwid.Text('═══ Performance ═══'), 'stat_title'))
        widgets.append(urwid.AttrMap(urwid.Text(f"BW:     {bw_mbps:.2f} Mbps"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"        {bw_kbps:.0f} KB/s"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"Latency:{latency_str}"), 'stat_label'))
        
        if packet_loss > 0:
            widgets.append(urwid.AttrMap(urwid.Text(f"Loss:   {packet_loss}"), 'stat_rst_value'))
        else:
            widgets.append(urwid.AttrMap(urwid.Text(f"Loss:   {packet_loss}"), 'stat_label'))
        
        # Excluded info
        if excluded_streams > 0 or excluded_protos > 0:
            widgets.append(urwid.Divider())
            widgets.append(urwid.AttrMap(urwid.Text('═══ Excluded ═══'), 'stat_title'))
            if excluded_streams > 0:
                widgets.append(urwid.AttrMap(urwid.Text(f"Streams: {excluded_streams}"), 'stat_rst'))
            if excluded_protos > 0:
                widgets.append(urwid.AttrMap(urwid.Text(f"Protocols: {excluded_protos}"), 'stat_rst'))
        
        # Top 10 IPs - ИСПРАВЛЕНО: одна строка
        widgets.append(urwid.Divider())
        widgets.append(urwid.AttrMap(urwid.Text('═══ Top 10 IPs ═══'), 'stat_title'))
        
        if top_ips:
            for i, (ip, count) in enumerate(top_ips[:10], 1):
                ip_short = ip[:18] if len(ip) > 18 else ip
                # ОДНА СТРОКА: номер, IP и счетчик
                line = f"{i}. {ip_short:<18} {count} pkts"
                widgets.append(urwid.AttrMap(urwid.Text(line), 'stat_label'))
        else:
            widgets.append(urwid.AttrMap(urwid.Text("No data"), 'stat_value'))
        
        # Top Talkers - ИСПРАВЛЕНО: одна строка
        widgets.append(urwid.Divider())
        widgets.append(urwid.AttrMap(urwid.Text('═══ Top Talkers ═══'), 'stat_title'))
        
        if top_talkers:
            for i, (ip, bytes_count) in enumerate(top_talkers[:5], 1):
                ip_short = ip[:18] if len(ip) > 18 else ip
                kb = bytes_count / 1024
                # ОДНА СТРОКА: номер, IP и размер
                line = f"{i}. {ip_short:<18} {kb:.1f} KB"
                widgets.append(urwid.AttrMap(urwid.Text(line), 'stat_label'))
        else:
            widgets.append(urwid.AttrMap(urwid.Text("No data"), 'stat_value'))
        
        # КРИТИЧНО: Очищаем walker и добавляем все виджеты
        self.listwalker.clear()
        self.listwalker.extend(widgets)
    
class ExcludeManagerDialog(urwid.WidgetWrap):
    """Диалог управления исключениями"""
    
    def __init__(self, packet_filter, on_close_callback):
        self.packet_filter = packet_filter
        self.on_close_callback = on_close_callback
        
        widgets = []
        widgets.append(urwid.Text(('dialog_title', 'Excluded Streams & Protocols Manager\n')))
        widgets.append(urwid.Divider())
        
        exclude_stream_count = self.packet_filter.get_exclude_count()
        exclude_proto_count = len(packet_filter.exclude_protocols)
        
        if exclude_stream_count == 0 and exclude_proto_count == 0:
            widgets.append(urwid.Text('No exclusions\n'))
            widgets.append(urwid.Divider())
            widgets.append(urwid.Text('Press X on any packet to exclude'))
            widgets.append(urwid.Text('  - TCP/UDP packet → exclude stream'))
            widgets.append(urwid.Text('  - ARP/ICMP/etc  → exclude protocol'))
        else:
            # Excluded Protocols
            if exclude_proto_count > 0:
                widgets.append(urwid.Text([
                    ('info', f'Excluded Protocols: {exclude_proto_count}\n')
                ]))
                for proto in sorted(self.packet_filter.exclude_protocols):
                    widgets.append(urwid.Text(f"  • {proto}"))
                widgets.append(urwid.Divider())
            
            # Excluded Streams
            if exclude_stream_count > 0:
                widgets.append(urwid.Text([
                    ('info', f'Excluded Streams: {exclude_stream_count}\n')
                ]))
                
                for i, excl in enumerate(self.packet_filter.exclude_streams, 1):
                    stream_text = (
                        f"{i:2}. {excl['proto']:<4} "
                        f"{excl['src_ip']}:{excl['src_port']} ↔ "
                        f"{excl['dst_ip']}:{excl['dst_port']}"
                    )
                    widgets.append(urwid.Text(stream_text))
        
        widgets.append(urwid.Divider())
        
        buttons = urwid.Columns([
            urwid.AttrMap(
                urwid.Button('Clear All', on_press=self._on_clear_all),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('Close', on_press=self._on_close),
                'button', 'button_focus'
            ),
        ])
        
        widgets.append(buttons)
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text('ESC/ENTER: close'))
        
        listwalker = urwid.SimpleFocusListWalker(widgets)
        listbox = urwid.ListBox(listwalker)
        content = urwid.LineBox(listbox, title='Exclude Manager')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))
    
    def keypress(self, size, key):
        if key in ('esc', 'enter'):
            self._on_close(None)
            return None
        return super().keypress(size, key)
    
    def _on_clear_all(self, button):
        self.packet_filter.clear_exclude_streams()
        self.packet_filter.clear_exclude_protocols()
        self._on_close(None)
    
    def _on_close(self, button):
        if self.on_close_callback:
            self.on_close_callback()


class PayloadSearchDialog(urwid.WidgetWrap):
    """Диалог поиска по payload"""
    
    def __init__(self, on_search_callback, on_cancel_callback):
        self.on_search_callback = on_search_callback
        self.on_cancel_callback = on_cancel_callback
        
        widgets = []
        widgets.append(urwid.Text(('dialog_title', 'Payload Search\n')))
        widgets.append(urwid.Divider())
        
        widgets.append(urwid.Text('Search string (supports regex):'))
        self.search_edit = urwid.Edit(edit_text='')
        widgets.append(urwid.AttrMap(self.search_edit, 'edit', 'edit_focus'))
        widgets.append(urwid.Divider())
        
        self.case_sensitive = urwid.CheckBox('Case sensitive')
        widgets.append(urwid.AttrMap(self.case_sensitive, 'radio', 'radio_focus'))
        widgets.append(urwid.Divider())
        
        buttons = urwid.Columns([
            urwid.AttrMap(
                urwid.Button('Search', on_press=self._on_search),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('Cancel', on_press=self._on_cancel),
                'button', 'button_focus'
            ),
        ])
        
        widgets.append(buttons)
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text('ENTER: search | ESC: cancel'))
        
        pile = urwid.Pile(widgets)
        filler = urwid.Filler(pile, valign='top')
        content = urwid.LineBox(filler, title='Payload Search')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))
    
    def keypress(self, size, key):
        if key == 'enter':
            self._on_search(None)
            return None
        elif key == 'esc':
            self._on_cancel(None)
            return None
        return super().keypress(size, key)
    
    def _on_search(self, button):
        search_string = self.search_edit.get_edit_text().strip()
        case_sensitive = self.case_sensitive.get_state()
        
        if self.on_search_callback and search_string:
            self.on_search_callback(search_string, case_sensitive)
    
    def _on_cancel(self, button):
        if self.on_cancel_callback:
            self.on_cancel_callback()


class FilterDialog(urwid.WidgetWrap):
    """Диалог для настройки фильтров"""
    
    def __init__(self, packet_filter, on_apply_callback, on_cancel_callback):
        self.packet_filter = packet_filter
        self.on_apply_callback = on_apply_callback
        self.on_cancel_callback = on_cancel_callback
        
        self.filter_fields = {}
        
        filter_labels = {
            'proto': 'Protocol (TCP, UDP, DNS, etc.):',
            'src_ip': 'Source IP Address:',
            'dst_ip': 'Destination IP Address:',
            'src_port': 'Source Port:',
            'dst_port': 'Destination Port:',
            'interface': 'Network Interface (eth0, wlan0, etc.):',
            'info': 'Info (regex supported):',
            'payload': 'Payload Search (regex):',
        }
        
        current_filters = self.packet_filter.get_active_filters()
        
        widgets = []
        widgets.append(urwid.Text(('dialog_title', 'Packet Filter Configuration\n')))
        widgets.append(urwid.Divider())
        
        for field, label in filter_labels.items():
            widgets.append(urwid.Text(label))
            edit = urwid.Edit(edit_text=current_filters.get(field, ''))
            self.filter_fields[field] = edit
            widgets.append(urwid.AttrMap(edit, 'edit', 'edit_focus'))
            widgets.append(urwid.Divider())
        
        buttons = urwid.Columns([
            urwid.AttrMap(
                urwid.Button('Apply', on_press=self._on_apply),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('Clear All', on_press=self._on_clear),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('Cancel', on_press=self._on_cancel),
                'button', 'button_focus'
            ),
        ])
        
        widgets.append(buttons)
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text('TAB: navigate | ENTER: apply | ESC: cancel'))
        
        self.listwalker = urwid.SimpleFocusListWalker(widgets)
        listbox = urwid.ListBox(self.listwalker)
        content = urwid.LineBox(listbox, title='Filter Settings')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))
    
    def keypress(self, size, key):
        if key == 'enter':
            try:
                focus_widget, _ = self.listwalker.get_focus()
                if isinstance(focus_widget, urwid.AttrMap):
                    base = focus_widget.base_widget
                    if isinstance(base, urwid.Edit):
                        self._on_apply(None)
                        return None
            except:
                pass
        elif key == 'esc':
            self._on_cancel(None)
            return None
        
        return super().keypress(size, key)
    
    def _on_apply(self, button):
        for field, edit_widget in self.filter_fields.items():
            value = edit_widget.get_edit_text().strip()
            self.packet_filter.set_filter(field, value)
        
        if self.on_apply_callback:
            self.on_apply_callback()
    
    def _on_clear(self, button):
        self.packet_filter.clear_filter()
        for edit_widget in self.filter_fields.values():
            edit_widget.set_edit_text('')
    
    def _on_cancel(self, button):
        if self.on_cancel_callback:
            self.on_cancel_callback()


class ConfirmDialog(urwid.WidgetWrap):
    """Диалог подтверждения"""
    
    def __init__(self, message, on_yes_callback, on_no_callback):
        self.on_yes_callback = on_yes_callback
        self.on_no_callback = on_no_callback
        
        widgets = []
        widgets.append(urwid.Text(('dialog_title', 'Confirmation\n')))
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text(message))
        widgets.append(urwid.Divider())
        
        buttons = urwid.Columns([
            urwid.AttrMap(
                urwid.Button('Yes', on_press=self._on_yes),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('No', on_press=self._on_no),
                'button', 'button_focus'
            ),
        ])
        
        widgets.append(buttons)
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text('Y: Yes | N/ESC: No'))
        
        pile = urwid.Pile(widgets)
        filler = urwid.Filler(pile, valign='top')
        content = urwid.LineBox(filler, title='Confirm')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))
    
    def keypress(self, size, key):
        if key in ('y', 'Y'):
            self._on_yes(None)
            return None
        elif key in ('n', 'N', 'esc'):
            self._on_no(None)
            return None
        return super().keypress(size, key)
    
    def _on_yes(self, button):
        if self.on_yes_callback:
            self.on_yes_callback()
    
    def _on_no(self, button):
        if self.on_no_callback:
            self.on_no_callback()


class SaveDialog(urwid.WidgetWrap):
    """Диалог для сохранения пакетов"""
    
    def __init__(self, export_dialog, on_save_callback, on_cancel_callback):
        self.export_dialog = export_dialog
        self.on_save_callback = on_save_callback
        self.on_cancel_callback = on_cancel_callback
        
        widgets = []
        widgets.append(urwid.Text(('dialog_title', 'Save Captured Packets\n')))
        widgets.append(urwid.Divider())
        
        widgets.append(urwid.Text('Filename (leave empty for auto-generated):'))
        self.filename_edit = urwid.Edit(edit_text='')
        widgets.append(urwid.AttrMap(self.filename_edit, 'edit', 'edit_focus'))
        widgets.append(urwid.Divider())
        
        self.save_mode = []
        
        widgets.append(urwid.Text('Save mode:'))
        rb1 = urwid.RadioButton(self.save_mode, 'All captured packets', state=True)
        rb2 = urwid.RadioButton(self.save_mode, 'Only filtered packets')
        
        widgets.append(urwid.AttrMap(rb1, 'radio', 'radio_focus'))
        widgets.append(urwid.AttrMap(rb2, 'radio', 'radio_focus'))
        widgets.append(urwid.Divider())
        
        total_packets = len(self.export_dialog.packet_capture.get_packets())
        filtered_packets = len(self.export_dialog.packet_filter.filter_packets(
            self.export_dialog.packet_capture.get_packets()
        ))
        
        widgets.append(urwid.Text([
            ('info', f'Total packets: {total_packets}\n'),
            ('info', f'Filtered packets: {filtered_packets}\n'),
        ]))
        widgets.append(urwid.Divider())
        
        buttons = urwid.Columns([
            urwid.AttrMap(
                urwid.Button('Save', on_press=self._on_save),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('Cancel', on_press=self._on_cancel),
                'button', 'button_focus'
            ),
        ])
        
        widgets.append(buttons)
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text('TAB: navigate | ENTER: save | ESC: cancel'))
        
        listwalker = urwid.SimpleFocusListWalker(widgets)
        listbox = urwid.ListBox(listwalker)
        content = urwid.LineBox(listbox, title='Save Packets')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))
    
    def keypress(self, size, key):
        if key == 'esc':
            self._on_cancel(None)
            return None
        return super().keypress(size, key)
    
    def _on_save(self, button):
        filename = self.filename_edit.get_edit_text().strip()
        filename = filename if filename else None
        
        save_all = self.save_mode[0].get_state()
        
        if save_all:
            success, filepath, message = self.export_dialog.export_all_packets(filename)
        else:
            success, filepath, message = self.export_dialog.export_filtered_packets(filename)
        
        if self.on_save_callback:
            self.on_save_callback(success, filepath, message)
    
    def _on_cancel(self, button):
        if self.on_cancel_callback:
            self.on_cancel_callback()


class HelpDialog(urwid.WidgetWrap):
    """Диалог помощи"""
    
    def __init__(self, on_close_callback):
        self.on_close_callback = on_close_callback
        
        help_text = [
            ('help_title', 'Packet Monitor - Ultimate Edition v5.1\n\n'),
            
            ('help_section', 'Navigation:\n'),
            '  ↑/↓         - Navigate packet list\n',
            '  Page Up/Down - Scroll faster\n',
            '  Home/End     - Jump to start/end\n\n',
            
            ('help_section', 'Actions:\n'),
            '  ENTER       - View packet details\n',
            '  T / t       - Follow TCP/UDP stream\n',
            '  X / x       - Exclude stream/protocol\n',
            '  E / e       - Manage exclusions\n',
            '  F / f       - Open filter dialog\n',
            '  / (slash)   - Payload search\n',
            '  S / s       - Save packets to file\n',
            '  C / c       - Clear captured packets\n',
            '  P / p       - Pause/Resume capture\n',
            '  A / a       - Toggle auto-scroll\n',
            '  H / h / F1  - Show this help\n',
            '  Q / q       - Quit (with confirmation)\n',
            '  Ctrl-C      - Quit (with confirmation)\n\n',
            
            ('help_section', 'Exclude Feature:\n'),
            '  TCP/UDP packet → exclude stream\n',
            '  ARP/ICMP/etc  → exclude protocol\n',
            '  Press E to manage all exclusions\n\n',
            
            ('help_section', 'Features:\n'),
            '  - Ring buffer (50,000 packets max)\n',
            '  - Multi-interface capture\n',
            '  - Real-time bandwidth monitoring\n',
            '  - Latency measurements\n',
            '  - Packet loss detection\n',
            '  - Top 10 IPs by packets/traffic\n',
            '  - Payload search (regex)\n',
            '  - RST packets highlighted in RED\n',
            '  - Exclude streams & protocols\n\n',
            
            ('help_section', 'Command Line:\n'),
            '  -i <iface>  - Capture interface\n',
            '  -i any      - All interfaces\n',
            '  -r <file>   - Read pcap file\n',
            '  -f <filter> - BPF filter\n',
            '  --ipv6      - Enable IPv6 stats\n\n',
            
            ('help_note', 'Press ESC or ENTER to close'),
        ]
        
        text_widget = urwid.Text(help_text)
        filler = urwid.Filler(text_widget, valign='top')
        content = urwid.LineBox(filler, title='Help')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))
    
    def keypress(self, size, key):
        if key in ('esc', 'enter'):
            if self.on_close_callback:
                self.on_close_callback()
            return None
        return super().keypress(size, key)


class PacketListBox(urwid.WidgetWrap):
    """Виджет для отображения списка пакетов"""
    
    def __init__(self, packet_capture, packet_filter):
        self.packet_capture = packet_capture
        self.packet_filter = packet_filter
        self.packet_widgets = []
        self.auto_scroll = True
        
        self.header = self._create_header()
        self.packet_list = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.packet_list)
        
        self.frame = urwid.Frame(
            body=self.listbox,
            header=self.header
        )
        
        super().__init__(self.frame)
        
    def _create_header(self):
        """Создать заголовок таблицы"""
        header_text = f"{'No':<6}{'Time':<12}{'Iface':<8}{'Proto':<8}{'Src IP':<16}{'Dst IP':<16}{'SPort':<6}{'DPort':<6}{'Info'}"
        return urwid.AttrMap(urwid.Text(header_text, wrap='clip'), 'header')
    
    def _format_packet_line(self, pkt):
        """Форматировать строку пакета с выделением RST и packet loss"""
        time_str = pkt['timestamp'].strftime('%H:%M:%S.%f')[:-3]
        
        iface = safe_str(pkt.get('interface'), 'N/A')[:7]
        src_ip = safe_str(pkt['src_ip'] if pkt['src_ip'] else pkt.get('src', '')[:15], '')[:15]
        dst_ip = safe_str(pkt['dst_ip'] if pkt['dst_ip'] else pkt.get('dst', '')[:15], '')[:15]
        src_port = str(pkt['src_port']) if pkt['src_port'] else ''
        dst_port = str(pkt['dst_port']) if pkt['dst_port'] else ''
        
        # Обрезаем info и убираем переводы строк
        info = pkt['info'].replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        info = ' '.join(info.split())
        max_info_len = 60
        if len(info) > max_info_len:
            info = info[:max_info_len-3] + '...'
        
        if pkt.get('packet_loss'):
            info = f"[LOSS] {info}"
        
        # Определяем цвет
        if 'RST' in info or pkt.get('packet_loss'):
            color = 'rst'
        else:
            proto_colors = {
                'TCP': 'tcp', 'TCPv6': 'tcp', 'UDP': 'udp', 'UDPv6': 'udp',
                'ICMP': 'icmp', 'ICMPv6': 'icmp', 'ARP': 'arp',
                'DNS': 'dns', 'HTTP': 'http', 'ETHER': 'ether',
            }
            color = proto_colors.get(pkt['proto'], 'default')
        
        # Формируем ОДНУ строку
        line = f"{pkt['num']:<6}{time_str:<12}{iface:<8}{pkt['proto']:<8}{src_ip:<16}{dst_ip:<16}{src_port:<6}{dst_port:<6}{info}"
        
        # Создаем SelectableText с wrap='clip' и оборачиваем в AttrMap
        text_widget = SelectableText(line, wrap='clip')
        colored_widget = urwid.AttrMap(text_widget, color)
        
        return colored_widget
    
    def toggle_auto_scroll(self):
        """Переключить автоскролл"""
        self.auto_scroll = not self.auto_scroll
        return self.auto_scroll
    
    def update_packets(self):
        """Обновить список пакетов"""
        all_packets = self.packet_capture.get_packets()
        filtered_packets = self.packet_filter.filter_packets(all_packets)
        
        current_count = len(self.packet_list)
        new_count = len(filtered_packets)
        
        if new_count < current_count:
            self.packet_list.clear()
            for pkt in filtered_packets:
                widget = self._format_packet_line(pkt)
                wrapped = urwid.AttrMap(widget, None, focus_map='selected')
                wrapped.packet_data = pkt
                self.packet_list.append(wrapped)
            
            if self.auto_scroll and len(self.packet_list) > 0:
                self.listbox.set_focus(len(self.packet_list) - 1)
        
        elif new_count > current_count:
            for pkt in filtered_packets[current_count:]:
                widget = self._format_packet_line(pkt)
                wrapped = urwid.AttrMap(widget, None, focus_map='selected')
                wrapped.packet_data = pkt
                self.packet_list.append(wrapped)
            
            if self.auto_scroll and len(self.packet_list) > 0:
                self.listbox.set_focus(len(self.packet_list) - 1)
    
    def get_selected_packet(self):
        """Получить выбранный пакет"""
        if len(self.packet_list) > 0:
            focus_widget, _ = self.listbox.get_focus()
            if hasattr(focus_widget, 'packet_data'):
                return focus_widget.packet_data
        return None
    
    def clear(self):
        """Очистить список"""
        self.packet_list.clear()


class StatusBar(urwid.WidgetWrap):
    """Статусная строка"""
    
    def __init__(self):
        self.text = urwid.Text('')
        self.help_text = urwid.Text('')
        
        self.pile = urwid.Pile([
            urwid.AttrMap(self.text, 'status'),
            urwid.AttrMap(self.help_text, 'default')
        ])
        
        super().__init__(self.pile)
        self._update_help_text()
    
    def _update_help_text(self):
        """Обновить подсказки"""
        help_content = [
            ('help', ' F1/H'),
            ('default', ':Help '),
            ('help', 'T'),
            ('default', ':Follow '),
            ('help', 'X'),
            ('default', ':Exclude '),
            ('help', 'E'),
            ('default', ':Manage '),
            ('help', 'F'),
            ('default', ':Filter '),
            ('help', '/'),
            ('default', ':Search '),
            ('help', 'A'),
            ('default', ':Auto '),
            ('help', 'S'),
            ('default', ':Save '),
            ('help', 'P'),
            ('default', ':Pause '),
            ('help', 'C'),
            ('default', ':Clear '),
            ('help', 'Q'),
            ('default', ':Quit '),
        ]
        self.help_text.set_text(help_content)
        
    def update(self, total_packets, filtered_packets, filter_summary, interface, capture_running, offline_mode=False, auto_scroll=False):
        """Обновить статус"""
        status_text = []
        
        if offline_mode:
            status_text.extend([
                ('status_label', 'Mode: '),
                ('status_value', 'OFFLINE  '),
            ])
        else:
            status_text.extend([
                ('status_label', 'Interface: '),
                ('status_value', f'{interface}  '),
                ('status_label', 'Status: '),
            ])
            
            if capture_running:
                status_text.append(('status_running', 'CAPTURING  '))
            else:
                status_text.append(('status_paused', 'PAUSED  '))
        
        status_text.extend([
            ('status_label', 'Total: '),
            ('status_value', f'{total_packets}  '),
            ('status_label', 'Displayed: '),
            ('status_value', f'{filtered_packets}  '),
            ('status_label', 'AutoScroll: '),
        ])
        
        if auto_scroll:
            status_text.append(('status_running', 'ON  '))
        else:
            status_text.append(('status_paused', 'OFF  '))
        
        if filter_summary != "No filters active":
            status_text.extend([
                ('status_label', 'Filter: '),
                ('status_filter', f'{filter_summary}'),
            ])
            
        self.text.set_text(status_text)


class MainApplication:
    """Главное приложение Ultimate Edition v5.1"""
    
    def __init__(self, packet_capture, packet_filter, packet_exporter, bpf_filter=None, offline_mode=False, enable_ipv6_stats=False):
        self.packet_capture = packet_capture
        self.packet_filter = packet_filter
        self.packet_exporter = packet_exporter
        self.bpf_filter = bpf_filter
        self.offline_mode = offline_mode
        
        from block4 import PacketDetailView
        from block5 import PacketExportDialog
        
        self.PacketDetailView = PacketDetailView
        self.PacketExportDialog = PacketExportDialog
        
        self.packet_list = PacketListBox(packet_capture, packet_filter)
        self.status_bar = StatusBar()
        self.stats_panel = StatisticsPanel(enable_ipv6_stats=enable_ipv6_stats)
        
        # Увеличиваем ширину панели статистики до 43
        self.columns = urwid.Columns([
            ('weight', 3, self.packet_list),
            (43, self.stats_panel),
        ], dividechars=1)
        
        self.main_frame = urwid.Frame(
            body=self.columns,
            footer=self.status_bar
        )
        
        self.overlay = None
        self.current_view = self.main_frame
        
        self.palette = [
            ('header', 'white,bold', 'dark blue'),
            ('status', 'white', 'dark blue'),
            ('status_label', 'white,bold', 'dark blue'),
            ('status_value', 'yellow', 'dark blue'),
            ('status_filter', 'light green', 'dark blue'),
            ('status_running', 'light green,bold', 'dark blue'),
            ('status_paused', 'light red,bold', 'dark blue'),
            ('selected', 'black', 'yellow'),
            
            ('tcp', 'light cyan', 'default'),
            ('udp', 'light green', 'default'),
            ('icmp', 'light magenta', 'default'),
            ('arp', 'yellow', 'default'),
            ('dns', 'light blue', 'default'),
            ('http', 'light red', 'default'),
            ('ether', 'dark gray', 'default'),
            ('rst', 'light red,bold', 'default'),
            ('default', 'white', 'default'),
            
            ('stat_panel', 'white', 'default'),
            ('stat_title', 'yellow,bold', 'default'),
            ('stat_label', 'light cyan', 'default'),
            ('stat_value', 'white', 'default'),
            ('stat_rst', 'light red,bold', 'default'),
            ('stat_rst_value', 'light red,bold', 'default'),
            
            ('dialog', 'white', 'dark blue'),
            ('dialog_title', 'yellow,bold', 'dark blue'),
            ('button', 'white', 'dark red'),
            ('button_focus', 'white,bold', 'dark green'),
            ('edit', 'white', 'dark blue'),
            ('edit_focus', 'white,bold', 'dark cyan'),
            ('radio', 'white', 'dark blue'),
            ('radio_focus', 'white,bold', 'dark cyan'),
            ('info', 'light green', 'dark blue'),
            
            ('detail_box', 'white', 'default'),
            ('detail_header', 'yellow,bold', 'default'),
            ('hexdump', 'light cyan', 'default'),
            
            ('help', 'white', 'dark red'),
            ('help_title', 'yellow,bold', 'default'),
            ('help_section', 'light cyan,bold', 'default'),
            ('help_note', 'light green', 'default'),
        ]
        
        self.loop = urwid.MainLoop(
            self.current_view,
            palette=self.palette,
            unhandled_input=self.handle_input,
            handle_mouse=False
        )
        
        self.running = False
    
    def handle_input(self, key):
        """Обработка клавиш"""
        if key in ('q', 'Q'):
            self.confirm_quit()
        elif key in ('c', 'C'):
            self.clear_packets()
        elif key in ('f', 'F'):
            self.show_filter_dialog()
        elif key == '/':
            self.show_payload_search()
        elif key in ('t', 'T'):
            self.follow_stream()
        elif key in ('x', 'X'):
            self.exclude_current_stream_or_protocol()
        elif key in ('e', 'E'):
            self.show_exclude_manager()
        elif key in ('a', 'A'):
            self.toggle_auto_scroll()
        elif key in ('s', 'S'):
            self.show_save_dialog()
        elif key in ('h', 'H', 'f1'):
            self.show_help_dialog()
        elif key in ('p', 'P'):
            if not self.offline_mode:
                self.toggle_capture()
        elif key == 'enter':
            self.show_packet_details()
    
    def exclude_current_stream_or_protocol(self):
        """Исключить stream ИЛИ протокол"""
        selected = self.packet_list.get_selected_packet()
        if not selected:
            self.show_message("No packet selected")
            return
        
        proto = selected.get('proto', '')
        
        if 'TCP' in proto or 'UDP' in proto:
            src_ip = selected.get('src_ip')
            dst_ip = selected.get('dst_ip')
            src_port = selected.get('src_port')
            dst_port = selected.get('dst_port')
            
            if not all([src_ip, dst_ip, src_port, dst_port]):
                self.show_message("Missing stream information")
                return
            
            base_proto = 'TCP' if 'TCP' in proto else 'UDP'
            
            added = self.packet_filter.add_exclude_stream(
                src_ip, dst_ip, src_port, dst_port, base_proto
            )
            
            if added:
                count = self.packet_filter.get_exclude_count()
                self.show_message(
                    f"✓ Excluded stream:\n"
                    f"{src_ip}:{src_port} ↔ {dst_ip}:{dst_port}\n\n"
                    f"Total excluded streams: {count}\n\n"
                    f"Press E to manage exclusions"
                )
            else:
                self.show_message("This stream is already excluded")
        
        else:
            added = self.packet_filter.add_exclude_protocol(proto)
            
            if added:
                proto_count = len(self.packet_filter.exclude_protocols)
                self.show_message(
                    f"✓ Excluded protocol: {proto}\n\n"
                    f"Total excluded protocols: {proto_count}\n\n"
                    f"Press E to manage exclusions"
                )
            else:
                self.show_message(f"Protocol {proto} is already excluded")
    
    def show_exclude_manager(self):
        """Показать менеджер исключений"""
        dialog = ExcludeManagerDialog(
            self.packet_filter,
            on_close_callback=self.close_dialog
        )
        self.show_overlay(dialog, width=70, height=25)
    
    def show_payload_search(self):
        """Показать диалог поиска по payload"""
        dialog = PayloadSearchDialog(
            on_search_callback=self.do_payload_search,
            on_cancel_callback=self.close_dialog
        )
        self.show_overlay(dialog, width=60, height=15)
    
    def do_payload_search(self, search_string, case_sensitive):
        """Выполнить поиск по payload"""
        self.close_dialog()
        
        all_packets = self.packet_capture.get_packets()
        results = self.packet_filter.search_payload(all_packets, search_string, case_sensitive)
        
        if results:
            self.packet_filter.clear_filter()
            self.packet_filter.set_filter('payload', search_string)
            msg = f"Found {len(results)} packets containing '{search_string}'"
        else:
            msg = f"No packets found containing '{search_string}'"
        
        self.show_message(msg)
    
    def toggle_auto_scroll(self):
        """Переключить автоскролл"""
        self.packet_list.toggle_auto_scroll()
    
    def follow_stream(self):
        """Follow stream"""
        selected = self.packet_list.get_selected_packet()
        if not selected:
            return
        
        if selected['proto'] not in ['TCP', 'UDP', 'TCPv6', 'UDPv6'] or not selected['src_port'] or not selected['dst_port']:
            self.show_message("Follow stream works only for TCP/UDP with ports")
            return
        
        src_ip = selected['src_ip']
        dst_ip = selected['dst_ip']
        src_port = str(selected['src_port'])
        dst_port = str(selected['dst_port'])
        
        self.packet_filter.clear_filter()
        
        self.packet_filter.set_filter('src_ip', f'({src_ip}|{dst_ip})')
        self.packet_filter.set_filter('dst_ip', f'({src_ip}|{dst_ip})')
        self.packet_filter.set_filter('src_port', f'({src_port}|{dst_port})')
        self.packet_filter.set_filter('dst_port', f'({src_port}|{dst_port})')
        
        base_proto = 'TCP' if 'TCP' in selected['proto'] else 'UDP'
        self.packet_filter.set_filter('proto', base_proto)
    
    def toggle_capture(self):
        """Переключить capture"""
        if self.packet_capture.running:
            self.packet_capture.stop_capture()
        else:
            self.packet_capture.start_capture()
    
    def confirm_quit(self):
        """Подтверждение выхода"""
        total = len(self.packet_capture.get_packets())
        stats = self.packet_capture.get_statistics()
        
        message = (f"Quit?\n\n"
                  f"Packets: {total}\n"
                  f"Traffic: {stats['total_bytes']:,} bytes\n"
                  f"Bandwidth: {stats['bandwidth_mbps']:.2f} Mbps")
        
        dialog = ConfirmDialog(
            message,
            on_yes_callback=self.quit_application,
            on_no_callback=self.close_dialog
        )
        
        self.show_overlay(dialog, width=50, height=14)
    
    def quit_application(self):
        """Выход"""
        self.running = False
        raise urwid.ExitMainLoop()
    
    def show_packet_details(self):
        """Детали пакета"""
        selected = self.packet_list.get_selected_packet()
        if selected:
            detail_view = self.PacketDetailView(
                selected,
                on_close_callback=self.close_packet_details
            )
            self.loop.widget = detail_view
    
    def close_packet_details(self):
        """Закрыть детали"""
        self.loop.widget = self.main_frame
    
    def show_filter_dialog(self):
        """Диалог фильтров"""
        dialog = FilterDialog(
            self.packet_filter,
            on_apply_callback=self.apply_filters,
            on_cancel_callback=self.close_dialog
        )
        self.show_overlay(dialog, width=60, height=32)
    
    def apply_filters(self):
        """Применить фильтры"""
        self.close_dialog()
    
    def show_save_dialog(self):
        """Сохранение"""
        export_dialog = self.PacketExportDialog(
            self.packet_capture,
            self.packet_filter,
            self.packet_exporter
        )
        
        dialog = SaveDialog(
            export_dialog,
            on_save_callback=self.on_save_complete,
            on_cancel_callback=self.close_dialog
        )
        self.show_overlay(dialog, width=60, height=20)
    
    def on_save_complete(self, success, filepath, message):
        """После сохранения"""
        self.close_dialog()
        msg = f"✓ {message}\nFile: {filepath}" if success else f"✗ {message}"
        self.show_message(msg)
    
    def show_help_dialog(self):
        """Помощь"""
        dialog = HelpDialog(on_close_callback=self.close_dialog)
        self.show_overlay(dialog, width=75, height=50)
    
    def show_overlay(self, widget, width, height):
        """Overlay"""
        self.overlay = urwid.Overlay(
            widget,
            self.main_frame,
            align='center',
            width=width,
            valign='middle',
            height=height
        )
        self.loop.widget = self.overlay
    
    def close_dialog(self):
        """Закрыть диалог"""
        self.loop.widget = self.main_frame
        self.overlay = None
    
    def show_message(self, message):
        """Сообщение"""
        msg_widget = urwid.AttrMap(
            urwid.Filler(
                urwid.Text(f"\n{message}\n\nPress any key", align='center')
            ),
            'help'
        )
        
        def dismiss(key):
            self.loop.widget = self.main_frame
            raise urwid.ExitMainLoop()
        
        temp_loop = urwid.MainLoop(
            msg_widget,
            palette=self.palette,
            unhandled_input=dismiss
        )
        temp_loop.run()
        self.loop.start()
    
    def clear_packets(self):
        """Очистить"""
        self.packet_capture.clear_packets()
        self.packet_list.clear()
    
    def refresh_display(self, loop, user_data):
        """Callback для периодического обновления"""
        if not self.running:
            return
        
        try:
            self.packet_list.update_packets()
            
            all_packets = self.packet_capture.get_packets()
            filtered = self.packet_filter.filter_packets(all_packets)
            
            self.stats_panel.update(filtered, self.packet_filter, self.packet_capture)
            
            total = len(all_packets)
            filter_summary = self.packet_filter.get_filter_summary()
            
            self.status_bar.update(
                total,
                len(filtered),
                filter_summary,
                self.packet_capture.interface,
                self.packet_capture.running,
                self.offline_mode,
                self.packet_list.auto_scroll
            )
            
            # Принудительно перерисовываем экран
            self.loop.draw_screen()
            
        except Exception as e:
            if self.packet_capture.log_file:
                try:
                    with open(self.packet_capture.log_file, 'a') as f:
                        import traceback
                        f.write(f"[ERROR in refresh_display] {e}\n{traceback.format_exc()}\n")
                except:
                    pass
        
        self.loop.set_alarm_in(0.1, self.refresh_display)
    
    def reset_terminal(self):
        """Сброс терминала"""
        try:
            sys.stdout.write('\033[0m\033[?25h')
            sys.stdout.flush()
        except:
            pass
    
    def start(self):
        """Старт приложения"""
        self.running = True
        self.loop.set_alarm_in(0.1, self.refresh_display)
        
        try:
            self.loop.run()
        finally:
            self.reset_terminal()
    
    def stop(self):
        """Стоп"""
        self.running = False
        self.reset_terminal()


def parse_arguments():
    """Аргументы командной строки"""
    parser = argparse.ArgumentParser(
        description='Packet Monitor v5.1 - Ultimate Edition',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('-i', '--interface', metavar='<iface>', default=None,
                       help='Network interface (use "any" for all)')
    parser.add_argument('-r', '--read', metavar='<file>', default=None,
                       help='Read from pcap/pcapng file')
    parser.add_argument('-f', '--filter', metavar='<filter>', default=None,
                       help='BPF filter (tcpdump syntax)')
    parser.add_argument('--ipv6', action='store_true',
                       help='Enable IPv6 statistics collection')
    parser.add_argument('--version', action='version', version='Packet Monitor v5.1')
    
    return parser.parse_args()


def main():
    """Main"""
    args = parse_arguments()
    
    # Подавляем вывод scapy в stderr
    import os
    stderr_backup = sys.stderr
    try:
        sys.stderr = open(os.devnull, 'w')
        from scapy.all import rdpcap
        from block1 import PacketCapture
        from block2 import PacketFilter
        from block5 import PacketExporter
        sys.stderr.close()
        sys.stderr = stderr_backup
    except Exception as e:
        if sys.stderr != stderr_backup:
            sys.stderr.close()
        sys.stderr = stderr_backup
        print(f"\n[ERROR] Import failed: {e}")
        sys.exit(1)
    
    print("=" * 70)
    print("Packet Monitor v5.1 - Ultimate Edition")
    print("=" * 70)
    
    try:
        import urwid
    except ImportError as e:
        print(f"\n[ERROR] Import failed: {e}")
        sys.exit(1)
    
    print("\nInitializing...")
    
    offline_mode = args.read is not None
    
    if offline_mode:
        print(f"  Reading {args.read}...")
        capture = PacketCapture(interface='offline', log_file='/tmp/packet_monitor.log')
        capture.running = False
        
        try:
            packets = rdpcap(args.read)
            print(f"  Loaded {len(packets)} packets")
            
            for i, pkt in enumerate(packets, 1):
                packet_info = capture._parse_packet(pkt)
                packet_info['num'] = i
                if hasattr(pkt, 'sniffed_on'):
                    packet_info['interface'] = str(pkt.sniffed_on)
                capture.packets.append(packet_info)
            
            print(f"  ✓ Ready")
        except Exception as e:
            print(f"\n[ERROR] Failed: {e}")
            sys.exit(1)
    else:
        if args.interface == 'any':
            interface = 'any'
        else:
            interface = args.interface
        
        capture = PacketCapture(
            interface=interface,
            packet_limit=50000,
            log_file='/tmp/packet_monitor.log'
        )
        
        print(f"  ✓ Interface: {capture.interface}")
        print(f"  ✓ Monitoring: {capture.interfaces}")
        print(f"  ✓ Buffer limit: 50000")
        print("  ✓ Starting PAUSED (press P to start)")
    
    pfilter = PacketFilter()
    exporter = PacketExporter()
    
    print("  ✓ Components initialized")
    print("  ✓ Log file: /tmp/packet_monitor.log")
    
    if args.ipv6:
        print("  ✓ IPv6 statistics: ENABLED")
    
    app = MainApplication(
        capture, pfilter, exporter,
        bpf_filter=args.filter,
        offline_mode=offline_mode,
        enable_ipv6_stats=args.ipv6
    )
    
    def signal_handler(sig, frame):
        app.confirm_quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print("\nStarting TUI...")
    print("=" * 70)
    
    try:
        app.start()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n\nShutdown...")
        if not offline_mode:
            capture.stop_capture()
        
        stats = capture.get_statistics()
        print(f"Packets captured: {stats['total_packets']}")
        print(f"Traffic: {stats['total_bytes']:,} bytes")
        print(f"Bandwidth: {stats['bandwidth_mbps']:.2f} Mbps")
        
        all_pkts = capture.get_packets()
        print(f"Packets in buffer: {len(all_pkts)}")
        
        if all_pkts:
            print("\nLast 5 packets:")
            for pkt in all_pkts[-5:]:
                iface_str = safe_str(pkt.get('interface'), 'N/A')
                proto_str = safe_str(pkt.get('proto'), 'N/A')
                src_ip_str = safe_str(pkt.get('src_ip'), 'N/A')
                dst_ip_str = safe_str(pkt.get('dst_ip'), 'N/A')
                
                print(f"  [{pkt['num']}] {iface_str:<8} {proto_str:<8} {src_ip_str} -> {dst_ip_str}")
        
        print("\nCheck log: tail -f /tmp/packet_monitor.log")
        print("\nGoodbye!")


if __name__ == '__main__':
    main()
