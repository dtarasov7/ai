```python
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
        
        # Флаг для включения/выключения кеширования
        self.use_cache = True
        
        self.walker = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.walker)

        self.header_text = urwid.Text(title, align='center')
        header_widget = urwid.AttrMap(self.header_text, 'header')
        
        self.path_text = urwid.Text('')
        path_widget = urwid.AttrMap(self.path_text, 'path')

        self.linebox = urwid.LineBox(
            urwid.Frame(
                urwid.AttrMap(self.listbox, 'body'),
                header=path_widget
            )
        )

        super().__init__(self.linebox)

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

    def update_header(self, info):
        if info:
            self.linebox.set_title(f"{self.title} {info}")
        else:
            self.linebox.set_title(self.title)

    def refresh(self, focus_on=None, force_reload=False):
        """Обновить панель с опциональной принудительной перезагрузкой"""
        # Если force_reload, временно отключаем кеш
        old_cache_setting = self.use_cache
        if force_reload:
            self.use_cache = False
        
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
        
        # Восстанавливаем настройку кеша
        if force_reload:
            self.use_cache = old_cache_setting
        
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
        self.update_header('[Root Menu]')
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

    def view_s3_file_version(self, file_data, version_data=None, close_callback=None):
        """Просмотр S3 файла с указанной версией"""
        version_id = version_data.get('VersionId') if version_data else None
        filename = file_data['name']
        
        if version_id:
            self.app.show_result(f"Downloading {filename} (version {version_id[:8]})...")
        else:
            self.app.show_result(f"Downloading {filename}...")
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmppath = tmp.name
            
            if self.s3_manager.download_object(
                self.current_bucket, 
                file_data['key'], 
                tmppath,
                version_id=version_id ):
                self._view_file(tmppath, filename, close_callback=close_callback)
                try:
                    os.unlink(tmppath)
                except:
                    pass
            else:
                self.app.show_result(f"Failed to download {filename}")

    def show_version_select_dialog(self, file_data):
        """Показать диалог выбора версии для просмотра"""
        versions = self.s3_manager.list_object_versions(
            self.current_bucket, 
            file_data['key'],
            use_cache=self.use_cache
        )

        if not versions:
            self.app.show_result("No versions found")
            return

        if len(versions) == 1:
            self.view_s3_file_version(file_data, versions[0])
            return

        def callback(action, version_data):
            if action == 'cancel':
                self.app.close_dialog()
                self.refresh()
                return

            if action == 'view' and version_data:
                self.app.close_dialog()
                self.view_s3_file_version( file_data, version_data,
                    close_callback=lambda: self.show_version_select_dialog(file_data)
                )

            elif action == 'delete' and version_data:
                self.app.close_dialog()
                self.confirm_delete_version(file_data, version_data)

        dialog = VersionSelectDialog(file_data, versions, callback)
        self.app.show_dialog(dialog, height=('relative', 60))

    def confirm_delete_version(self, file_data, version_data, close_callback=None):
        """Подтверждение удаления конкретной версии"""
        def confirm_callback(confirmed):
            self.app.close_dialog()
            if confirmed:
                version_id_full = version_data.get('VersionId')
                if self.s3_manager.delete_object(
                    self.current_bucket, 
                    file_data['key'], 
                    version_id=version_id_full
                ):
                    version_id = version_data.get('VersionId', '')[:12]
                    self.app.show_result(f"Version {version_id} deleted successfully")
                else:
                    version_id = version_data.get('VersionId', '')[:12]
                    self.app.show_result(f"Failed to delete version {version_id}")
                self.show_version_select_dialog(file_data)
            else:
                self.show_version_select_dialog(file_data)

        version_id = version_data.get('VersionId', '')[:12]
        is_latest = version_data.get('IsLatest', False)
        latest_warn = " [THIS IS THE LATEST VERSION!]" if is_latest else ""
        size = format_size(version_data.get('Size', 0))
        mtime = version_data.get('LastModified', '').strftime('%Y-%m-%d %H:%M:%S') if version_data.get('LastModified') else 'N/A'
        message = f"Delete version of '{file_data['name']}'?{latest_warn}"
        items_info = [
            f"Version ID: {version_id}",
            f"Size: {size}",
            f"Modified: {mtime}"
        ]
        dialog = ConfirmDialog( "Confirm Delete Version", message, items_info, confirm_callback )
        self.app.show_dialog(dialog)

    def _refresh_endpoints(self):
        self.update_header('[S3 Mode - Endpoints]')
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

    def _refresh_s3(self):
        if self.current_bucket is None:
            cache_indicator = " [CACHE]" if self.use_cache else ""
            self.update_header(f'[S3 Mode - {self.current_endpoint}] Sort: {self.sort_mode}{cache_indicator}')
            self.path_text.set_text(f'S3: /{self.current_endpoint}/')
            
            data = {'type': 'to_root_menu', 'can_select': False}
            text = SelectableText('  [..] Back to root menu', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
            
            buckets = self.s3_manager.list_buckets(use_cache=self.use_cache)
            
            if not buckets and self.s3_manager.connection_error:
                error_msg = f'[ERROR] Connection failed: {self.s3_manager.connection_error[:60]}'
                data = {'type': 'error', 'can_select': False}
                text = SelectableText(f'  {error_msg}', data, self)
                self.walker.append(urwid.AttrMap(text, 'error'))
                self.app.show_result(f'Cannot connect to {self.current_endpoint}: {self.s3_manager.connection_error[:80]}')
                return

            bucket_items = []
            for bucket in buckets:
                versioning_status = self.s3_manager.get_versioning_status(
                    bucket['Name'],
                    use_cache=self.use_cache
                )
                if versioning_status == 'Enabled':
                    versioning_mark = '[V]' 
                elif versioning_status == 'Suspended':
                    versioning_mark = '[S]'
                else:
                    versioning_mark = '   '

                bucket_items.append({
                    'name': bucket['Name'],
                    'type': 'bucket',
                    'CreationDate': bucket.get('CreationDate'),
                    'mtime': bucket.get('CreationDate'),
                    'size': 0,
                    'versioning': versioning_status,
                    'versioning_mark': versioning_mark,
                    'can_select': True
                })
            
            bucket_items = self.sort_items(bucket_items)
            
            for bucket in bucket_items:
                creation_date = bucket.get('CreationDate')
                date_str = creation_date.strftime('%Y-%m-%d %H:%M:%S') if creation_date else ' ' * 19
                
                label = f'*{bucket["name"]:40} {date_str} {bucket["versioning_mark"]}'

                data = {'type': 'bucket', 'name': bucket['name'], 'can_select': True}
                text = SelectableText(f'  {label}', data, self)
                self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
        else:
            cache_indicator = " [CACHE]" if self.use_cache else ""
            self.update_header(f'[S3 Mode - {self.current_endpoint}] Sort: {self.sort_mode}{cache_indicator}')
            self.path_text.set_text(f'S3: /{self.current_endpoint}/{self.current_bucket}/{self.current_prefix}')
            
            if self.current_prefix:
                data = {'type': 's3_parent', 'can_select': False}
                text = SelectableText('  [..] Parent', data, self)
            else:
                data = {'type': 's3_back', 'can_select': False}
                text = SelectableText('  [..] Back to buckets', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
            
            folders, files = self.s3_manager.list_objects(
                self.current_bucket, 
                self.current_prefix,
                use_cache=self.use_cache
            )
            
            if not folders and not files and self.s3_manager.connection_error:
                error_msg = f'[ERROR] Cannot list objects: {self.s3_manager.connection_error[:60]}'
                data = {'type': 'error', 'can_select': False}
                text = SelectableText(f'  {error_msg}', data, self)
                self.walker.append(urwid.AttrMap(text, 'error'))
                return
            
            folder_items = []
            for folder in folders:
                folder_name = folder['Key'][len(self.current_prefix):].rstrip('/')
                folder_items.append({
                    'name': folder_name,
                    'key': folder['Key'],
                    'type': 's3_dir',
                    'size': 0,
                    'mtime': datetime.min,
                    'can_select': True
                })
            
            file_items = []
            for file_obj in files:
                key = file_obj['Key']
                file_name = key[len(self.current_prefix):]
                
                versions = self.s3_manager.list_object_versions(
                    self.current_bucket, 
                    key,
                    use_cache=self.use_cache
                )
                version_info = ''
                if len(versions) > 1:
                    version_info = f' [{len(versions)}]'
                
                file_items.append({
                    'name': file_name,
                    'key': key,
                    'type': 's3_file',
                    'size': file_obj['Size'],
                    'Size': file_obj['Size'],
                    'mtime': file_obj.get('LastModified', datetime.min),
                    'LastModified': file_obj.get('LastModified'),
                    'version_count': len(versions),
                    'version_info': version_info,
                    'can_select': True
                })
            
            folder_items = self.sort_items(folder_items)
            file_items = self.sort_items(file_items)
            
            for folder_item in folder_items:
                label = f'/{folder_item["name"]:40}                ' + ' ' * 19
                data = {'type': 's3_dir', 'key': folder_item['key'], 'name': folder_item['name'], 'can_select': True}
                text = SelectableText(f'  {label}', data, self)
                self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
            
            for file_item in file_items:
                mtime = file_item['LastModified'].strftime('%Y-%m-%d %H:%M:%S') if file_item.get('LastModified') else ' ' * 19
                size_str = self.format_size(file_item['size'])
                version_str = file_item['version_info']
                
                label = f' {file_item["name"]:40} {size_str:>10}{version_str:4} {mtime}'
                data = {
                    'type': 's3_file',
                    'key': file_item['key'],
                    'name': file_item['name'],
                    'size': file_item['size'],
                    'version_count': file_item['version_count'],
                    'can_select': True
                }
                text = SelectableText(f'  {label}', data, self)
                self.walker.append(urwid.AttrMap(text, 'file', focus_map='selected'))

    def _refresh_fs(self):
        cache_indicator = " [CACHE]" if self.use_cache else ""
        self.update_header(f'[FS Mode] Sort: {self.sort_mode}{cache_indicator}')
        self.path_text.set_text(f'FS: {self.fs_browser.current_path}')
        
        if self.is_fs_root():
            data = {'type': 'to_root_menu', 'can_select': False}
            text = SelectableText('  [..] Back to root menu', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
        
        items = self.fs_browser.list_directory(use_cache=self.use_cache)
        
        dirs = [item for item in items if item['is_dir'] and item['name'] != '..']
        files = [item for item in items if not item['is_dir']]
        parent = [item for item in items if item['name'] == '..']
        
        dirs = self.sort_items(dirs)
        files = self.sort_items(files)
        
        for item_data in parent:
            label = '/..'
            data = {
                'type': 'fs_dir',
                'name': item_data['name'],
                'size': item_data['size'],
                'can_select': False
            }
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
        
        for item_data in dirs:
            mtime = item_data['mtime'].strftime('%Y-%m-%d %H:%M:%S') if item_data['mtime'] else ' ' * 19
            label = f'/{item_data["name"]:40}            {mtime}'
            data = {
                'type': 'fs_dir',
                'name': item_data['name'],
                'size': item_data['size'],
                'mtime': item_data['mtime'],
                'can_select': True
            }
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, 'body', focus_map='selected'))
        
        for item_data in files:
            mtime = item_data['mtime'].strftime('%Y-%m-%d %H:%M:%S') if item_data['mtime'] else ' ' * 19
            label = f' {item_data["name"]:40} {self.format_size(item_data["size"]):>10} {mtime}'
            data = {
                'type': 'fs_file',
                'name': item_data['name'],
                'size': item_data['size'],
                'mtime': item_data['mtime'],
                'can_select': True
            }
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, 'file', focus_map='selected'))

    def format_size(self, size):
        for unit in ['B  ', 'KB ', 'MB ', 'GB ']:
            if size < 1024.0:
                return f'{size:.1f}{unit}'
            size /= 1024.0
        return f'{size:.1f}TB'

    def on_item_activated(self, data):
        item_type = data.get('type')
        
        if item_type == 'to_root_menu':
            self.mode = 'root_menu'
            self.current_endpoint = None
            self.current_bucket = None
            self.current_prefix = ''
            self.s3_manager = None
            self.refresh()
        
        elif item_type == 'root_fs':
            self.mode = 'fs'
            if self.fs_browser is None:
                self.fs_browser = FileSystemBrowser()
            self.refresh()
        
        elif item_type == 'root_endpoint':
            self.mode = 's3'
            self.current_endpoint = data['name']
            endpoint_config = data['config']
            self.s3_manager = S3Manager(endpoint_config)
            self.current_bucket = None
            self.current_prefix = ''
            self.refresh()
        
        elif item_type == 'endpoint':
            self.current_endpoint = data['name']
            endpoint_config = data['config']
            self.s3_manager = S3Manager(endpoint_config)
            self.current_bucket = None
            self.current_prefix = ''
            self.refresh()
        
        elif item_type == 'bucket':
            self.current_bucket = data['name']
            self.current_prefix = ''
            self.refresh()
        
        elif item_type == 's3_back':
            focus_on = self.current_bucket
            self.current_bucket = None
            self.current_prefix = ''
            self.refresh(focus_on=focus_on)
        
        elif item_type == 's3_parent':
            if self.current_prefix:
                parts = self.current_prefix.rstrip('/').split('/')
                focus_on = parts[-1]
                self.current_prefix = '/'.join(parts[:-1]) + '/' if len(parts) > 1 else ''
                self.refresh(focus_on=focus_on)
        
        elif item_type == 's3_dir':
            self.current_prefix = data['key']
            self.refresh()
        
        elif item_type == 's3_file':
            if data.get('version_count', 1) > 1:
                self.show_versions(data)
            else:
                self.view_item()
        
        elif item_type == 'fs_dir':
            if data['name'] == '..':
                focus_on = os.path.basename(self.fs_browser.current_path)
                self.fs_browser.current_path = os.path.dirname(self.fs_browser.current_path)
                self.refresh(focus_on=focus_on)
            else:
                self.fs_browser.current_path = os.path.join(self.fs_browser.current_path, data['name'])
                self.refresh()

    def show_versions(self, file_data):
        versions = self.s3_manager.list_object_versions(
            self.current_bucket, 
            file_data['key'],
            use_cache=self.use_cache
        )
        if not versions:
            self.app.show_result('No versions found')
            return
        
        version_lines = [f"Versions of: {file_data['name']}\n"]
        for idx, v in enumerate(versions):
            is_latest = v.get('IsLatest', False)
            latest_mark = '[LATEST] ' if is_latest else '        '
            size = self.format_size(v.get('Size', 0))
            mtime = v.get('LastModified', '').strftime('%Y-%m-%d %H:%M:%S') if v.get('LastModified') else ''
            version_id = v.get('VersionId', '')[:12]
            version_lines.append(f"{idx+1}. {latest_mark}{version_id} {size:>10} {mtime}")
        
        content = '\n'.join(version_lines)
        content += '\n\nUse F3 to view, F5 to copy, F8 to delete selected version'
        
        viewer = FileViewerDialog(f'Versions: {file_data["name"]}', content, self.app.close_dialog)
        self.app.show_dialog(viewer)

    def select_by_pattern(self, pattern, select=True):
        """Выбрать/снять выбор элементов по glob pattern (только файлы)"""
        try:
            regex_pattern = fnmatch.translate(pattern)
            regex = re.compile(regex_pattern, re.IGNORECASE)
            count = 0
            
            for widget in self.walker:
                w = widget.original_widget
                if isinstance(w, SelectableText) and w.data.get('can_select'):
                    item_type = w.data.get('type')
                    if item_type in ('fs_file', 's3_file'):
                        name = w.data.get('name', '')
                        if regex.match(name):
                            w.selected = select
                            self.update_item_display(w)
                            count += 1
            
            action = 'Selected' if select else 'Unselected'
            self.app.show_result(f'{action} {count} files')
        except re.error:
            self.app.show_result('Invalid pattern')

    def invert_selection(self):
        """Инвертировать выбор (только файлы)"""
        count = 0
        for widget in self.walker:
            w = widget.original_widget
            if isinstance(w, SelectableText) and w.data.get('can_select'):
                item_type = w.data.get('type')
                if item_type in ('fs_file', 's3_file'):
                    w.selected = not w.selected
                    self.update_item_display(w)
                    if w.selected:
                        count += 1
        
        self.app.show_result(f'Selected {count} files')

    def update_item_display(self, text_widget):
        if text_widget.selected:
            text_widget.set_text('* ' + text_widget.get_text()[0][2:])
        else:
            text_widget.set_text('  ' + text_widget.get_text()[0][2:])

    def get_selected_items(self):
        selected = []
        for widget in self.walker:
            w = widget.original_widget
            if isinstance(w, SelectableText) and w.selected:
                selected.append(w.data)
        return selected

    def get_focused_item(self):
        focus_widget, pos = self.listbox.get_focus()
        if focus_widget:
            w = focus_widget.original_widget
            if isinstance(w, SelectableText):
                return w.data
        return None

    def view_item(self):
        focused = self.get_focused_item()
        if not focused:
            return

        item_type = focused['type']

        if item_type == 'fs_file':
            file_path = os.path.join(self.fs_browser.current_path, focused['name'])
            self._view_file(file_path, focused['name'])

        elif item_type == 's3_file':
            if focused.get('version_count', 1) > 1:
                self.show_version_select_dialog(focused)
            else:
                self.view_s3_file_version(focused)

        elif item_type in ('fs_dir', 's3_dir', 'bucket'):
            self._calculate_size(focused)

    def _view_file(self, file_path, title, close_callback=None):
        try:
            if is_binary_file(file_path):
                content = f"[Binary file: {title}]\n\nFile size: {os.path.getsize(file_path)} bytes\n\n"
                content += "This is a binary file and cannot be displayed as text."
            else:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read(50000)
                        if len(content) == 50000:
                            content += "\n\n[... File truncated ...]"
                except Exception as e:
                    content = f"Error reading file: {str(e)}"

            def on_viewer_close():
                self.app.close_dialog()
                if close_callback:
                    close_callback()

            viewer = FileViewerDialog(f'View: {title}', content, on_viewer_close)
            self.app.show_dialog(viewer, height=('relative', 80))

        except Exception as e:
            self.app.show_result(f'Error viewing file: {str(e)}')

    def _calculate_size(self, item):
        """Подсчет размера директории/бакета/псевдодиректории"""
        item_type = item['type']
        
        def calculate_in_thread():
            try:
                total_size = 0
                file_count = 0
                
                if item_type == 'fs_dir':
                    dir_path = os.path.join(self.fs_browser.current_path, item['name'])
