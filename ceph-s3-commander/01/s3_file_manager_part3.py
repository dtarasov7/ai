
class PanelWidget(urwid.WidgetWrap):
    def __init__(self, title, panel_type='fs', s3_config=None, app=None):
        self.title = title
        self.panel_type = panel_type
        self.s3_config = s3_config
        self.s3_manager = None
        self.fs_browser = FileSystemBrowser() if panel_type == 'fs' else None
        self.app = app

        self.current_endpoint = None
        self.current_bucket = None
        self.current_prefix = ''
        self.mode = panel_type

        self.sort_mode = 'name'

        self.walker = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.walker)

        header = urwid.AttrMap(urwid.Text(title, align='center'), 'header')
        self.path_text = urwid.Text('')
        path_widget = urwid.AttrMap(self.path_text, 'path')
        self.mode_text = urwid.Text('')
        mode_widget = urwid.AttrMap(self.mode_text, 'mode')

        frame = urwid.Frame(
            urwid.AttrMap(self.listbox, 'body'),
            header=urwid.Pile([header, mode_widget, path_widget])
        )

        super().__init__(frame)
        self.refresh()

    def show_sort_dialog(self):
        """Показать диалог выбора сортировки"""
        def callback(confirmed, mode):
            self.app.close_dialog()
            if confirmed and mode:
                self.sort_mode = mode
                self.refresh()
                self.app.show_result(f'Sort by: {mode}')

        dialog = SortDialog(self.sort_mode, callback)
        self.app.show_dialog(dialog)

    def sort_items(self, items):
        """Сортировать элементы согласно режиму сортировки"""
        if self.sort_mode == 'name':
            return sorted(items, key=lambda x: x.get('name', x.get('key', '')).lower())
        elif self.sort_mode == 'ext':
            def get_ext(item):
                name = item.get('name', item.get('key', ''))
                if '.' in name:
                    return name.rsplit('.', 1)[1].lower()
                return ''
            return sorted(items, key=get_ext)
        elif self.sort_mode == 'size':
            return sorted(items, key=lambda x: x.get('size', x.get('Size', 0)), reverse=True)
        elif self.sort_mode == 'time':
            return sorted(items, key=lambda x: x.get('mtime', x.get('LastModified', datetime.min)), reverse=True)
        return items

    def is_root_menu(self):
        return self.mode == 'root_menu'

    def is_endpoint_list(self):
        return self.mode == 's3' and self.current_endpoint is None

    def is_bucket_list(self):
        return self.mode == 's3' and self.current_endpoint is not None and self.current_bucket is None

    def is_fs_root(self):
        return self.mode == 'fs' and self.fs_browser.current_path == '/'

    def get_current_path(self):
        """Получить текущий путь для копирования"""
        if self.mode == 's3':
            if self.current_bucket:
                return self.current_prefix if self.current_prefix else ''
            else:
                return ''
        elif self.mode == 'fs':
            return self.fs_browser.current_path
        else:
            return ''

    def refresh(self, focus_on=None):
        self.walker.clear()

        if self.mode == 'root_menu':
            self._refresh_root_menu()
        elif self.mode == 's3':
            if self.current_endpoint is None:
                self._refresh_endpoints()
            else:
                self._refresh_s3()
        else:
            self._refresh_fs()

        if focus_on:
            self.set_focus_on_item(focus_on)

    def set_focus_on_item(self, item_name):
        for idx, widget in enumerate(self.walker):
            w = widget.original_widget
            if isinstance(w, SelectableText):
                data = w.data
                if data.get('name') == item_name or data.get('key', '').rstrip('/').split('/')[-1] == item_name:
                    self.listbox.set_focus(idx)
                    return

    def _refresh_root_menu(self):
        self.mode_text.set_text('[Root Menu]')
        self.path_text.set_text('Select source type:')

        label = '[FS] Local File System'
        data = {'type': 'root_fs', 'can_select': False}
        text = SelectableText(f'  {label}', data, self)
        self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

        self.walker.append(urwid.Divider())

        endpoints = self.s3_config.get_endpoints()
        for ep in endpoints:
            label = f'[S3] {ep["name"]:35} {ep["url"]}'
            data = {'type': 'root_endpoint', 'name': ep['name'], 'config': ep, 'can_select': False}
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

    def _refresh_endpoints(self):
        self.mode_text.set_text('[S3 Mode - Endpoints]')
        self.path_text.set_text('S3: /')

        data = {'type': 'to_root_menu', 'can_select': False}
        text = SelectableText('  [..] Back to root menu', data, self)
        self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

        endpoints = self.s3_config.get_endpoints()

        for ep in endpoints:
            label = f'[ENDPOINT] {ep["name"]:35} {ep["url"]}'
            data = {'type': 'endpoint', 'name': ep['name'], 'config': ep, 'can_select': False}
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
