
class ProgressDialog(urwid.WidgetWrap):
    """Диалог прогресса операций в стиле MC"""

    def __init__(self, title, callback=None):
        self.callback = callback
        self.title_text = urwid.Text(title, align='center')
        self.progress_text = urwid.Text('', align='left')
        self.file_text = urwid.Text('', align='left')
        self.stats_text = urwid.Text('', align='left')
        self.bytes_text = urwid.Text('', align='left')

        self.total_files = 0
        self.processed_files = 0
        self.success_count = 0
        self.fail_count = 0
        self.current_file = ''
        self.total_bytes = 0
        self.processed_bytes = 0
        self.start_time = time.time()

        skip_button = urwid.Button('[ Skip ]')
        cancel_button = urwid.Button('[ Cancel ]')

        self.cancelled = False

        urwid.connect_signal(skip_button, 'click', lambda b: None)
        urwid.connect_signal(cancel_button, 'click', self.on_cancel)

        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(skip_button, 'button', focus_map='button_focus')),
            ('fixed', 2, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='button_focus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)

        pile = urwid.Pile([
            urwid.Divider(),
            self.title_text,
            urwid.Divider(),
            self.progress_text,
            self.file_text,
            urwid.Divider(),
            self.stats_text,
            self.bytes_text,
            urwid.Divider(),
            buttons,
            urwid.Divider(),
        ])

        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill)

        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def on_cancel(self, button):
        self.cancelled = True
        if self.callback:
            self.callback()

    def keypress(self, size, key):
        if key == 'esc':
            self.on_cancel(None)
            return None
        return super().keypress(size, key)

    def get_speed_str(self):
        """Получить строку скорости передачи"""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            speed = self.processed_bytes / elapsed
            return f'{format_size(speed)}/s'
        return '0 B/s'

    def update(self, current_file='', file_size=0):
        if current_file:
            self.current_file = current_file
            self.processed_files += 1
            self.processed_bytes += file_size

        if self.total_files > 0:
            percent = int((self.processed_files / self.total_files) * 100)
            bar_width = 40
            filled = int((self.processed_files / self.total_files) * bar_width)
            bar = '█' * filled + '░' * (bar_width - filled)
            self.progress_text.set_text(f'[{bar}] {percent}%')

        if self.current_file:
            display_file = self.current_file
            if len(display_file) > 60:
                display_file = '...' + display_file[-57:]
            self.file_text.set_text(f'File: {display_file}')

        self.stats_text.set_text(
            f'Total: {self.total_files} | Processed: {self.processed_files} | '
            f'Success: {self.success_count} | Failed: {self.fail_count}'
        )

        if self.total_bytes > 0:
            bytes_percent = int((self.processed_bytes / self.total_bytes) * 100) if self.total_bytes > 0 else 0
            speed_str = self.get_speed_str()
            self.bytes_text.set_text(
                f'Bytes: {format_size(self.processed_bytes)} / {format_size(self.total_bytes)} ({bytes_percent}%) | Speed: {speed_str}'
            )

    def set_total(self, total_files, total_bytes=0):
        self.total_files = total_files
        self.total_bytes = total_bytes
        self.start_time = time.time()
        self.update()

    def add_success(self):
        self.success_count += 1
        self.update()

    def add_failure(self):
        self.fail_count += 1
        self.update()


class SortDialog(urwid.WidgetWrap):
    """Диалог выбора режима сортировки"""

    def __init__(self, current_mode, callback):
        self.callback = callback
        self.current_mode = current_mode

        title_text = urwid.Text('Sort by:', align='center')

        self.radio_group = []
        modes = [
            ('name', 'Name'),
            ('ext', 'Extension'),
            ('size', 'Size'),
            ('time', 'Time')
        ]

        radio_buttons = []
        for mode, label in modes:
            rb = urwid.RadioButton(self.radio_group, label, state=(mode == current_mode))
            rb.mode = mode
            radio_buttons.append(urwid.AttrMap(rb, None, focus_map='selected'))

        ok_button = urwid.Button('[ OK ]')
        cancel_button = urwid.Button('[ Cancel ]')

        urwid.connect_signal(ok_button, 'click', self.on_ok)
        urwid.connect_signal(cancel_button, 'click', self.on_cancel)

        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(ok_button, 'button', focus_map='button_focus')),
            ('fixed', 2, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='button_focus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)

        content = [
            urwid.Divider(),
            title_text,
            urwid.Divider(),
        ]
        content.extend(radio_buttons)
        content.extend([
            urwid.Divider(),
            buttons,
            urwid.Divider(),
        ])

        pile = urwid.Pile(content)
        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill)

        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def on_ok(self, button):
        for rb in self.radio_group:
            if rb.state:
                self.callback(True, rb.mode)
                return
        self.callback(False, None)

    def on_cancel(self, button):
        self.callback(False, None)

    def keypress(self, size, key):
        if key == 'enter':
            self.on_ok(None)
            return None
        elif key == 'esc':
            self.on_cancel(None)
            return None
        return super().keypress(size, key)


class CopyMoveDialog(urwid.WidgetWrap):
    """Диалог копирования/перемещения в стиле MC"""

    def __init__(self, title, source_desc, dest_path, callback):
        self.callback = callback

        title_text = urwid.Text(('dialog_title', title), align='center')
        source_text = urwid.Text(source_desc)
        self.dest_edit = urwid.Edit('to: ', dest_path)

        ok_button = urwid.Button('[ OK ]')
        cancel_button = urwid.Button('[ Cancel ]')

        urwid.connect_signal(ok_button, 'click', self.on_ok)
        urwid.connect_signal(cancel_button, 'click', self.on_cancel)

        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(ok_button, 'button', focus_map='button_focus')),
            ('fixed', 2, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='button_focus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)

        pile = urwid.Pile([
            urwid.Divider(),
            title_text,
            urwid.Divider(),
            source_text,
            urwid.Divider(),
            urwid.AttrMap(self.dest_edit, 'edit', focus_map='edit_focus'),
            urwid.Divider(),
            buttons,
            urwid.Divider(),
        ])

        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill)

        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def keypress(self, size, key):
        if key == 'enter':
            self.on_ok(None)
            return None
        elif key == 'esc':
            self.on_cancel(None)
            return None
        return super().keypress(size, key)

    def on_ok(self, button):
        dest = self.dest_edit.get_edit_text()
        self.callback(True, dest)

    def on_cancel(self, button):
        self.callback(False, None)


class SizeResultDialog(urwid.WidgetWrap):
    """Диалог отображения результатов подсчета размера"""

    def __init__(self, results, callback):
        self.callback = callback

        title_text = urwid.Text('Size Calculation Results', align='center')

        content_widgets = [title_text, urwid.Divider()]

        for result in results:
            name = result['name']
            size = format_size(result['size'])
            count = result['count']
            newest = result['newest_date'].strftime('%Y-%m-%d %H:%M:%S') if result.get('newest_date') else 'N/A'
            oldest = result['oldest_date'].strftime('%Y-%m-%d %H:%M:%S') if result.get('oldest_date') else 'N/A'

            content_widgets.append(urwid.Text(f'\n{name}:'))
            content_widgets.append(urwid.Text(f'  Size: {size} ({count} files)'))
            content_widgets.append(urwid.Text(f'  Newest: {newest}'))
            content_widgets.append(urwid.Text(f'  Oldest: {oldest}'))

        content_widgets.append(urwid.Divider())

        listbox = urwid.ListBox(urwid.SimpleFocusListWalker(content_widgets))

        close_button = urwid.Button('[ Close ]')
        urwid.connect_signal(close_button, 'click', self.on_close)

        pile = urwid.Pile([
            ('weight', 1, listbox),
            ('pack', urwid.Divider()),
            ('pack', urwid.AttrMap(close_button, 'button', focus_map='button_focus'))
        ])

        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill)

        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def on_close(self, button):
        self.callback()

    def keypress(self, size, key):
        if key == 'esc':
            self.callback()
            return None
        return super().keypress(size, key)


class InputDialog(urwid.WidgetWrap):
    def __init__(self, title, prompt, callback, default_text=''):
        self.callback = callback
        self.edit = urwid.Edit(prompt, default_text)

        ok_button = urwid.Button('OK')
        cancel_button = urwid.Button('Cancel')

        urwid.connect_signal(ok_button, 'click', self.on_ok)
        urwid.connect_signal(cancel_button, 'click', self.on_cancel)

        buttons = urwid.Columns([
            urwid.AttrMap(ok_button, None, focus_map='selected'),
            urwid.AttrMap(cancel_button, None, focus_map='selected')
        ], dividechars=2)

        pile = urwid.Pile([
            urwid.Text(title, align='center'),
            urwid.Divider(),
            self.edit,
            urwid.Divider(),
            buttons
        ])

        fill = urwid.Filler(pile)
        super().__init__(urwid.AttrMap(urwid.LineBox(fill), 'dialog'))

    def keypress(self, size, key):
        if key == 'enter':
            self.on_ok(None)
            return None
        elif key == 'esc':
            self.on_cancel(None)
            return None
        return super().keypress(size, key)

    def on_ok(self, button):
        text = self.edit.get_edit_text()
        if text.strip():
            self.callback(True, text.strip())

    def on_cancel(self, button):
        self.callback(False, None)


class ConfirmDialog(urwid.WidgetWrap):
    def __init__(self, title, message, items_info, callback):
        self.callback = callback

        yes_button = urwid.Button('Yes')
        no_button = urwid.Button('No')

        urwid.connect_signal(yes_button, 'click', self.on_yes)
        urwid.connect_signal(no_button, 'click', self.on_no)

        buttons = urwid.Columns([
            urwid.AttrMap(yes_button, None, focus_map='selected'),
            urwid.AttrMap(no_button, None, focus_map='selected')
        ], dividechars=2)

        content = [
            urwid.Text(title, align='center'),
            urwid.Divider(),
            urwid.Text(message),
            urwid.Divider(),
        ]

        if items_info:
            content.append(urwid.Text('Items:', align='left'))

            max_display = 10
            for item_info in items_info[:max_display]:
                content.append(urwid.Text(f'  {item_info}'))

            if len(items_info) > max_display:
                content.append(urwid.Text(f'  ... and {len(items_info) - max_display} more'))

            content.append(urwid.Divider())

        content.append(buttons)

        pile = urwid.Pile(content)
        fill = urwid.Filler(pile, valign='top')
        super().__init__(urwid.AttrMap(urwid.LineBox(fill), 'dialog'))

    def keypress(self, size, key):
        if key == 'enter':
            self.on_yes(None)
            return None
        elif key == 'esc':
            self.on_no(None)
            return None
        return super().keypress(size, key)

    def on_yes(self, button):
        self.callback(True)

    def on_no(self, button):
        self.callback(False)
