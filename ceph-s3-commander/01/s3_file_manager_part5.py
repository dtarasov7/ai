
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
        versions = self.s3_manager.list_object_versions(self.current_bucket, file_data['key'])
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
        selected_items = self.get_selected_items()

        if not selected_items:
            focused = self.get_focused_item()
            if focused:
                selected_items = [focused]

        if not selected_items:
            return

        items_to_calc = [item for item in selected_items if item['type'] in ('fs_dir', 's3_dir', 'bucket')]

        if not items_to_calc:
            focused = self.get_focused_item()
            if focused:
                item_type = focused['type']

                if item_type == 'fs_file':
                    file_path = os.path.join(self.fs_browser.current_path, focused['name'])
                    self._view_file(file_path, focused['name'])

                elif item_type == 's3_file':
                    self.app.show_result(f'Downloading {focused["name"]}...')
                    with tempfile.NamedTemporaryFile(delete=False) as tmp:
                        tmp_path = tmp.name

                    if self.s3_manager.download_object(self.current_bucket, focused['key'], tmp_path):
                        self._view_file(tmp_path, focused['name'])
                        try:
                            os.unlink(tmp_path)
                        except:
                            pass
                    else:
                        self.app.show_result(f'Failed to download {focused["name"]}')
            return

        self._calculate_size_multiple(items_to_calc)

    def _view_file(self, file_path, title):
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

            viewer = FileViewerDialog(f'View: {title}', content, self.app.close_dialog)
            self.app.show_dialog(viewer)

        except Exception as e:
            self.app.show_result(f'Error viewing file: {str(e)}')

    def _calculate_size_multiple(self, items):
        """Подсчет размера для нескольких элементов"""

        def calculate_in_thread():
            results = []

            for item in items:
                try:
                    item_type = item['type']
                    total_size = 0
                    file_count = 0
                    newest_date = None
                    oldest_date = None

                    if item_type == 'fs_dir':
                        dir_path = os.path.join(self.fs_browser.current_path, item['name'])
                        files = self.fs_browser.list_all_files(dir_path)
                        file_count = len(files)
                        total_size = sum(f['size'] for f in files)

                        for f in files:
                            try:
                                mtime = datetime.fromtimestamp(os.path.getmtime(f['path']))
                                if newest_date is None or mtime > newest_date:
                                    newest_date = mtime
                                if oldest_date is None or mtime < oldest_date:
                                    oldest_date = mtime
                            except:
                                pass

                    elif item_type == 's3_dir':
                        objects = self.s3_manager.list_all_objects(self.current_bucket, item['key'])
                        file_count = len(objects)
                        total_size = sum(obj.get('Size', 0) for obj in objects)

                        for obj in objects:
                            mtime = obj.get('LastModified')
                            if mtime:
                                if newest_date is None or mtime > newest_date:
                                    newest_date = mtime
                                if oldest_date is None or mtime < oldest_date:
                                    oldest_date = mtime

                    elif item_type == 'bucket':
                        objects = self.s3_manager.list_all_objects(item['name'], '')
                        file_count = len(objects)
                        total_size = sum(obj.get('Size', 0) for obj in objects)

                        for obj in objects:
                            mtime = obj.get('LastModified')
                            if mtime:
                                if newest_date is None or mtime > newest_date:
                                    newest_date = mtime
                                if oldest_date is None or mtime < oldest_date:
                                    oldest_date = mtime

                    results.append({
                        'name': item['name'],
                        'size': total_size,
                        'count': file_count,
                        'newest_date': newest_date,
                        'oldest_date': oldest_date
                    })

                except Exception as e:
                    results.append({
                        'name': item['name'],
                        'size': 0,
                        'count': 0,
                        'error': str(e)
                    })

            def show_results():
                dialog = SizeResultDialog(results, self.app.close_dialog)
                self.app.show_dialog(dialog)

            self.app.loop.set_alarm_in(0, lambda *args: show_results())

        self.app.show_result('Calculating size...')
        thread = threading.Thread(target=calculate_in_thread)
        thread.daemon = True
        thread.start()
