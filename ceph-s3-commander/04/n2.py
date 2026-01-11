latest_mark = "[LATEST] " if is_latest else ""
            size = format_size(v.get('Size', 0))
            mtime = v.get('LastModified', '').strftime('%Y-%m-%d %H:%M:%S') if v.get('LastModified') else ''
            version_id = v.get('VersionId', '')[:12]
            
            label = f"{latest_mark}{version_id}  {size:>10}  {mtime}"
            
            rb = urwid.RadioButton(self.radio_group, label, state=(idx == 0))
            rb.version_data = v
            version_buttons.append(('pack', urwid.AttrMap(rb, None, focus_map='selected')))
        
        # Кнопки управления
        view_button = urwid.Button("[ View ]")
        delete_button = urwid.Button("[ Delete ]")
        cancel_button = urwid.Button("[ Cancel ]")
        
        urwid.connect_signal(view_button, 'click', self.on_view)
        urwid.connect_signal(delete_button, 'click', self.on_delete)
        urwid.connect_signal(cancel_button, 'click', self.on_cancel)
        
        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(view_button, 'button', focus_map='buttonfocus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(delete_button, 'button', focus_map='buttonfocus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='buttonfocus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)
        
        # Собираем диалог
        content = [
            ('pack', urwid.Divider()),
            ('pack', urwid.Text(f"Total versions: {len(versions)}")),
            ('pack', urwid.Divider()),
        ]
        content.extend(version_buttons)
        content.extend([
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])
        title = f"Select version: {file_data['name']}"
        pile = urwid.Pile(content)
        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill, title=title)
        
        super().__init__(urwid.AttrMap(linebox, 'dialog'))
    
    def get_selected_version(self):
        """Получить выбранную версию"""
        for rb in self.radio_group:
            if rb.state:
                return rb.version_data
        return None
    
    def on_view(self, button):
        version_data = self.get_selected_version()
        self.callback('view', version_data)
    
    def on_delete(self, button):
        version_data = self.get_selected_version()
        if version_data:
            self.callback('delete', version_data)
    
    def on_cancel(self, button):
        self.callback('cancel', None)

    def keypress(self, size, key):
        if key == 'enter':
            btn = get_focus_button(self._w)
            if btn != None:
                if isinstance(btn, urwid.Button) and btn.get_label() == '[ Cancel ]':
                    self.on_cancel(None)
                    return None
                if isinstance(btn, urwid.Button) and btn.get_label() == '[ Delete ]':
                    self.on_delete(None)
                    return None
            self.on_view(None)
            return None
        elif key == 'esc':
            self.on_cancel(None)
            return None
        elif key == 'f8':
            self.on_delete(None)
            return None
        return super().keypress(size, key)


class OverwriteDialog(urwid.WidgetWrap):
    """Диалог подтверждения перезаписи файла"""

    def __init__(self, filename, source_info, dest_info, callback, show_version_options=False):
        self.callback = callback

        title_text = urwid.Text('File already exists!', align='center')
        file_text = urwid.Text(f'File: {filename}')

        src_size = source_info.get("size", 0)
        dst_size = dest_info.get("size", 0)

        src_mtime = source_info.get("mtime")
        dst_mtime = dest_info.get("mtime")

        src_time_str = src_mtime.strftime("%Y-%m-%d %H:%M:%S") if src_mtime else "N/A"
        dst_time_str = dst_mtime.strftime("%Y-%m-%d %H:%M:%S") if dst_mtime else "N/A"

        source_text = urwid.Text( f'Source: {format_size(src_size)} | {src_time_str}' )
        dest_text = urwid.Text( f'Target: {format_size(dst_size)} | {dst_time_str}' )

        buttons_list = []

        overwrite_button = urwid.Button('[ Overwrite ]')
        all_button = urwid.Button('[ All ]')
        urwid.connect_signal(overwrite_button, 'click', lambda b: self.on_choice('overwrite'))
        urwid.connect_signal(all_button, 'click', lambda b: self.on_choice('all'))
        buttons_list.extend([
            ('pack', urwid.AttrMap(overwrite_button, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(all_button, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
        ])

        if show_version_options:
            version_button = urwid.Button('[ New Version ]')
            version_all_button = urwid.Button('[ Version All ]')
            urwid.connect_signal(version_button, 'click', lambda b: self.on_choice('version'))
            urwid.connect_signal(version_all_button, 'click', lambda b: self.on_choice('version_all'))
            buttons_list.extend([
                ('pack', urwid.AttrMap(version_button, 'button', focus_map='button_focus')),
                ('fixed', 1, urwid.Text('')),
                ('pack', urwid.AttrMap(version_all_button, 'button', focus_map='button_focus')),
                ('fixed', 1, urwid.Text('')),
            ])

        skip_button = urwid.Button('[ Skip ]')
        skip_all_button = urwid.Button('[ Skip All ]')
        cancel_button = urwid.Button('[ Cancel ]')
        urwid.connect_signal(skip_button, 'click', lambda b: self.on_choice('skip'))
        urwid.connect_signal(skip_all_button, 'click', lambda b: self.on_choice('skip_all'))
        urwid.connect_signal(cancel_button, 'click', lambda b: self.on_choice('cancel'))
        buttons_list.extend([
            ('pack', urwid.AttrMap(skip_button, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(skip_all_button, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='button_focus')),
        ])

        buttons_list.insert(0, ('weight', 1, urwid.Text('')))
        buttons_list.append(('weight', 1, urwid.Text('')))

        buttons = urwid.Columns(buttons_list, dividechars=0)

        pile = urwid.Pile([
            ('pack', urwid.Divider()),
            ('pack', title_text),
            ('pack', urwid.Divider()),
            ('pack', file_text),
            ('pack', urwid.Divider()),
            ('pack', source_text),
            ('pack', dest_text),
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])
        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill)

        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def on_choice(self, choice):
        self.callback(choice)

    def keypress(self, size, key):
        if key == 'esc':
            self.callback('cancel')
            return None
        return super().keypress(size, key)


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
            ('pack', urwid.Divider()),
            ('pack', self.title_text),
            ('pack', urwid.Divider()),
            ('pack', self.progress_text),
            ('pack', self.file_text),
            ('pack', urwid.Divider()),
            ('pack', self.stats_text),
            ('pack', self.bytes_text),
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
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
            ('pack', urwid.Divider()),
            ('pack', title_text),
            ('pack', urwid.Divider()),
        ]
        content.extend([('pack', rb) for rb in radio_buttons])
        content.extend([
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
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
            ('pack', urwid.Divider()),
            ('pack', source_text),
            ('pack', urwid.Divider()),
            ('pack', urwid.AttrMap(self.dest_edit, 'edit', focus_map='edit_focus')),
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])

        
        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill, title=title)
        
        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def keypress(self, size, key):
        if key == 'enter':
            btn = get_focus_button(self._w)
            if btn != None:
                if isinstance(btn, urwid.Button) and btn.get_label() == '[ Cancel ]':
                    self.on_cancel(None)
                    return None
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


