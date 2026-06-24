#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Packet Monitor - Block 3: TUI interface with packet list (Fixed terminal reset)
Требования: scapy==2.4.5, urwid
"""

import urwid
import threading
import time
import sys
import os
from datetime import datetime


class PacketListBox(urwid.WidgetWrap):
    """Виджет для отображения списка пакетов"""
    
    def __init__(self, packet_capture, packet_filter):
        """
        Инициализация списка пакетов
        
        Args:
            packet_capture: экземпляр PacketCapture
            packet_filter: экземпляр PacketFilter
        """
        self.packet_capture = packet_capture
        self.packet_filter = packet_filter
        self.packet_widgets = []
        
        # Создаем заголовок таблицы
        self.header = self._create_header()
        
        # Создаем список для пакетов
        self.packet_list = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.packet_list)
        
        # Оборачиваем в рамку с заголовком
        self.frame = urwid.Frame(
            body=self.listbox,
            header=self.header
        )
        
        super().__init__(self.frame)
        
    def _create_header(self):
        """Создать заголовок таблицы"""
        header_text = [
            ('header', f"{'No':<6}"),
            ('header', f"{'Time':<12}"),
            ('header', f"{'Protocol':<10}"),
            ('header', f"{'Source IP':<18}"),
            ('header', f"{'Dest IP':<18}"),
            ('header', f"{'Src Port':<10}"),
            ('header', f"{'Dst Port':<10}"),
            ('header', f"{'Info':<30}"),
        ]
        return urwid.AttrMap(urwid.Text(header_text), 'header')
    
    def _format_packet_line(self, pkt):
        """
        Форматировать строку пакета для отображения
        
        Args:
            pkt: информация о пакете
            
        Returns:
            urwid.Text widget
        """
        time_str = pkt['timestamp'].strftime('%H:%M:%S.%f')[:-3]
        src_ip = pkt['src_ip'] if pkt['src_ip'] else pkt['src'][:15]
        dst_ip = pkt['dst_ip'] if pkt['dst_ip'] else pkt['dst'][:15]
        src_port = str(pkt['src_port']) if pkt['src_port'] else ''
        dst_port = str(pkt['dst_port']) if pkt['dst_port'] else ''
        info = pkt['info'][:28]
        
        # Определяем цвет на основе протокола
        proto_colors = {
            'TCP': 'tcp',
            'UDP': 'udp',
            'ICMP': 'icmp',
            'ARP': 'arp',
            'DNS': 'dns',
            'HTTP': 'http',
            'ETHER': 'ether',
        }
        color = proto_colors.get(pkt['proto'], 'default')
        
        line_text = [
            (color, f"{pkt['num']:<6}"),
            (color, f"{time_str:<12}"),
            (color, f"{pkt['proto']:<10}"),
            (color, f"{src_ip:<18}"),
            (color, f"{dst_ip:<18}"),
            (color, f"{src_port:<10}"),
            (color, f"{dst_port:<10}"),
            (color, f"{info:<30}"),
        ]
        
        return urwid.Text(line_text)
    
    def update_packets(self):
        """Обновить список пакетов из PacketCapture"""
        # Получаем все пакеты
        all_packets = self.packet_capture.get_packets()
        
        # Применяем фильтр
        filtered_packets = self.packet_filter.filter_packets(all_packets)
        
        # Обновляем список только если есть новые пакеты
        current_count = len(self.packet_list)
        new_count = len(filtered_packets)
        
        if new_count > current_count:
            # Добавляем только новые пакеты
            for pkt in filtered_packets[current_count:]:
                widget = urwid.AttrMap(
                    self._format_packet_line(pkt),
                    None,
                    focus_map='selected'
                )
                widget.packet_data = pkt  # Сохраняем данные пакета
                self.packet_list.append(widget)
                
            # Автопрокрутка к последнему пакету
            if len(self.packet_list) > 0:
                self.listbox.set_focus(len(self.packet_list) - 1)
        
        elif new_count < current_count:
            # Фильтр изменился - пересоздаем список
            self.packet_list.clear()
            for pkt in filtered_packets:
                widget = urwid.AttrMap(
                    self._format_packet_line(pkt),
                    None,
                    focus_map='selected'
                )
                widget.packet_data = pkt
                self.packet_list.append(widget)
    
    def get_selected_packet(self):
        """Получить выбранный пакет"""
        if len(self.packet_list) > 0:
            focus_widget, _ = self.listbox.get_focus()
            if hasattr(focus_widget, 'packet_data'):
                return focus_widget.packet_data
        return None
    
    def clear(self):
        """Очистить список пакетов"""
        self.packet_list.clear()


class StatusBar(urwid.WidgetWrap):
    """Статусная строка внизу экрана"""
    
    def __init__(self):
        self.text = urwid.Text('')
        super().__init__(urwid.AttrMap(self.text, 'status'))
        
    def update(self, total_packets, filtered_packets, filter_summary, interface):
        """Обновить статусную строку"""
        status_text = [
            ('status_label', 'Interface: '),
            ('status_value', f'{interface}  '),
            ('status_label', 'Total: '),
            ('status_value', f'{total_packets}  '),
            ('status_label', 'Displayed: '),
            ('status_value', f'{filtered_packets}  '),
        ]
        
        if filter_summary != "No filters active":
            status_text.extend([
                ('status_label', 'Filter: '),
                ('status_filter', f'{filter_summary}'),
            ])
            
        self.text.set_text(status_text)


class PacketMonitorTUI:
    """Главный TUI класс для мониторинга пакетов"""
    
    def __init__(self, packet_capture, packet_filter):
        """
        Инициализация TUI
        
        Args:
            packet_capture: экземпляр PacketCapture
            packet_filter: экземпляр PacketFilter
        """
        self.packet_capture = packet_capture
        self.packet_filter = packet_filter
        self.running = False
        
        # Создаем компоненты интерфейса
        self.packet_list = PacketListBox(packet_capture, packet_filter)
        self.status_bar = StatusBar()
        
        # Создаем главный фрейм
        self.main_frame = urwid.Frame(
            body=self.packet_list,
            footer=self._create_footer()
        )
        
        # Палитра цветов
        self.palette = [
            ('header', 'white,bold', 'dark blue'),
            ('status', 'white', 'dark blue'),
            ('status_label', 'white,bold', 'dark blue'),
            ('status_value', 'yellow', 'dark blue'),
            ('status_filter', 'light green', 'dark blue'),
            ('selected', 'black', 'yellow'),
            ('tcp', 'light cyan', 'default'),
            ('udp', 'light green', 'default'),
            ('icmp', 'light magenta', 'default'),
            ('arp', 'yellow', 'default'),
            ('dns', 'light blue', 'default'),
            ('http', 'light red', 'default'),
            ('ether', 'dark gray', 'default'),
            ('default', 'white', 'default'),
            ('help', 'white', 'dark red'),
        ]
        
        # Создаем главный loop
        self.loop = urwid.MainLoop(
            self.main_frame,
            palette=self.palette,
            unhandled_input=self.handle_input
        )
        
        # Поток обновления
        self.update_thread = None
        
    def _create_footer(self):
        """Создать футер с подсказками и статусом"""
        help_text = urwid.Text([
            ('help', ' Q'),
            ('default', ':Quit '),
            ('help', 'C'),
            ('default', ':Clear '),
            ('help', 'F'),
            ('default', ':Filter '),
            ('help', 'ENTER'),
            ('default', ':Details '),
        ])
        
        footer_pile = urwid.Pile([
            self.status_bar,
            urwid.AttrMap(help_text, 'default')
        ])
        
        return footer_pile
    
    def handle_input(self, key):
        """Обработка нажатий клавиш"""
        if key in ('q', 'Q'):
            self.stop()
            raise urwid.ExitMainLoop()
            
        elif key in ('c', 'C'):
            # Очистить захваченные пакеты
            self.packet_capture.clear_packets()
            self.packet_list.clear()
            
        elif key in ('f', 'F'):
            # Открыть диалог фильтра (будет реализовано в блоке 6)
            self.show_message("Filter dialog - coming in Block 6!")
            
        elif key == 'enter':
            # Показать детали пакета (будет реализовано в блоке 4)
            selected = self.packet_list.get_selected_packet()
            if selected:
                self.show_message(f"Packet details - coming in Block 4! (Packet #{selected['num']})")
    
    def show_message(self, message):
        """Показать временное сообщение"""
        original_footer = self.main_frame.footer
        msg_widget = urwid.AttrMap(
            urwid.Text(f" {message} (press any key)"),
            'help'
        )
        self.main_frame.footer = msg_widget
        self.loop.draw_screen()
        
        # Ждем нажатия клавиши
        def restore_footer(key):
            self.main_frame.footer = original_footer
            raise urwid.ExitMainLoop()
            
        temp_loop = urwid.MainLoop(
            self.main_frame,
            palette=self.palette,
            unhandled_input=restore_footer
        )
        temp_loop.run()
        self.loop.start()
    
    def update_display(self):
        """Обновление отображения (вызывается в отдельном потоке)"""
        while self.running:
            try:
                # Обновляем список пакетов
                self.packet_list.update_packets()
                
                # Обновляем статус
                total = len(self.packet_capture.get_packets())
                filtered = len(self.packet_filter.filter_packets(
                    self.packet_capture.get_packets()
                ))
                filter_summary = self.packet_filter.get_filter_summary()
                
                self.status_bar.update(
                    total,
                    filtered,
                    filter_summary,
                    self.packet_capture.interface
                )
                
                # Перерисовываем экран
                self.loop.draw_screen()
                
                time.sleep(0.2)  # Обновление 5 раз в секунду
                
            except Exception as e:
                # Игнорируем ошибки отрисовки
                pass
    
    def reset_terminal(self):
        """Сброс терминала в нормальное состояние"""
        try:
            # Сброс цветов и атрибутов терминала
            sys.stdout.write('\033[0m')  # Reset all attributes
            sys.stdout.write('\033[?25h')  # Show cursor
            sys.stdout.flush()
            
            # Очистка экрана (опционально)
            # os.system('clear' if os.name == 'posix' else 'cls')
            
        except Exception:
            pass
    
    def start(self):
        """Запустить TUI"""
        self.running = True
        
        # Запускаем поток обновления
        self.update_thread = threading.Thread(
            target=self.update_display,
            daemon=True
        )
        self.update_thread.start()
        
        try:
            # Запускаем главный loop
            self.loop.run()
        finally:
            # ВАЖНО: Всегда сбрасываем терминал при выходе
            self.reset_terminal()
    
    def stop(self):
        """Остановить TUI"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=1)
        
        # Сбрасываем терминал
        self.reset_terminal()


# Тестирование блока 3
if __name__ == '__main__':
    import sys
    
    # Проверяем наличие urwid
    try:
        import urwid
    except ImportError:
        print("Error: urwid not installed")
        print("\nInstall with:")
        print("  sudo pip3 install urwid")
        sys.exit(1)
    
    # Для демонстрации создадим mock объекты
    class MockCapture:
        def __init__(self):
            self.interface = 'eth0'
            self.packets = []
            self.running = False
            self.packet_count = 0
            
        def get_packets(self):
            return self.packets
            
        def clear_packets(self):
            self.packets.clear()
            self.packet_count = 0
            
        def start_capture(self):
            self.running = True
            
        def stop_capture(self):
            self.running = False
            
        # Генерируем тестовые пакеты
        def generate_test_packets(self):
            import random
            protocols = ['TCP', 'UDP', 'DNS', 'HTTP', 'ICMP', 'ARP']
            ips = ['192.168.1.1', '8.8.8.8', '1.1.1.1', '10.0.0.1', '172.16.0.1']
            
            for i in range(100):
                if not self.running:
                    break
                    
                self.packet_count += 1
                pkt = {
                    'num': self.packet_count,
                    'timestamp': datetime.now(),
                    'proto': random.choice(protocols),
                    'src_ip': random.choice(ips),
                    'dst_ip': random.choice(ips),
                    'src_port': random.randint(1024, 65535) if random.random() > 0.3 else '',
                    'dst_port': random.choice([80, 443, 53, 22, 8080]) if random.random() > 0.3 else '',
                    'src': f'{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:00:00:00',
                    'dst': f'{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:00:00:00',
                    'info': f'Test packet {i+1}',
                    'length': random.randint(60, 1500),
                    'vlan': '',
                    'raw_packet': None
                }
                self.packets.append(pkt)
                time.sleep(0.05)
    
    class MockFilter:
        def __init__(self):
            self.active = False
            
        def filter_packets(self, packets):
            return packets
            
        def get_filter_summary(self):
            return "No filters active"
    
    print("=" * 70)
    print("Starting Packet Monitor TUI - Block 3 Test (Fixed)")
    print("=" * 70)
    print("\nGenerating test packets...")
    
    # Создаем mock объекты
    capture = MockCapture()
    pfilter = MockFilter()
    
    capture.start_capture()
    
    # Генерируем тестовые пакеты в фоне
    import threading
    gen_thread = threading.Thread(
        target=capture.generate_test_packets,
        daemon=True
    )
    gen_thread.start()
    
    print("Starting TUI in 2 seconds...")
    time.sleep(2)
    
    # Запускаем TUI
    try:
        tui = PacketMonitorTUI(capture, pfilter)
        tui.start()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        capture.stop_capture()
        # Финальный сброс терминала на всякий случай
        sys.stdout.write('\033[0m\033[?25h')
        sys.stdout.flush()
        print("\nTerminal reset complete.")
