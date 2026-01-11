

class DualPaneApp:
    def __init__(self, s3_config):
        self.s3_config = s3_config

        self.left_panel = PanelWidget('LEFT PANEL', panel_type='root_menu', s3_config=s3_config, app=self)
        self.right_panel = PanelWidget('RIGHT PANEL', panel_type='root_menu', s3_config=s3_config, app=self)

        self.left_panel.mode = 'root_menu'
        self.right_panel.mode = 'root_menu'

        self.columns = urwid.Columns([
            ('weight', 1, urwid.LineBox(self.left_panel)),
            ('weight', 1, urwid.LineBox(self.right_panel))
        ], dividechars=1, focus_column=0)

        self.hotkey_text = urwid.Text(
            'F3:view/size | F5:copy | F6:move | F7:mkdir | F8:del | F9:del_old_ver | F10:sort | INS:sel | +:select | -:unsel | *:invert | TAB | q:quit'
        )
        self.result_text = urwid.Text('')

        status_content = urwid.Pile([
            urwid.AttrMap(self.result_text, 'result'),
            urwid.AttrMap(self.hotkey_text, 'status')
        ])

        self.frame = urwid.Frame(
            urwid.AttrMap(self.columns, 'body'),
            footer=status_content
        )

        self.main_widget = self.frame

        self.palette = [
            ('header', 'black', 'light cyan', 'bold'),
            ('path', 'black', 'light cyan'),
            ('mode', 'black', 'light cyan'),
            ('body', 'white', 'dark blue'),
            ('selected', 'black', 'light cyan'),
            ('status', 'black', 'light cyan'),
            ('result', 'yellow', 'dark blue'),
            ('dialog', 'black', 'light gray'),
            ('dialog_title', 'black', 'light cyan'),
            ('edit', 'black', 'light cyan'),
            ('edit_focus', 'white', 'dark cyan'),
            ('button', 'black', 'light gray'),
            ('button_focus', 'white', 'dark cyan'),
            ('error', 'light red', 'dark blue'),
        ]

        self.overwrite_all = False
        self.version_all = False
        self.skip_all = False

    def run(self):
        self.loop = urwid.MainLoop(
            self.main_widget,
            palette=self.palette,
            unhandled_input=self.handle_input
        )
        self.loop.run()

    def handle_input(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        elif key == 'tab':
            current_focus = self.columns.focus_position
            self.columns.focus_position = 1 - current_focus
        elif key == 'f3':
            active_panel = self.get_active_panel()
            active_panel.view_item()
        elif key == 'f5':
            self.copy_items()
        elif key == 'f6':
            self.move_items()
        elif key == 'f7':
            self.create_directory()
        elif key == 'f8':
            self.delete_items()
        elif key == 'f9':
            self.delete_old_versions()
        elif key == 'f10':
            active_panel = self.get_active_panel()
            active_panel.show_sort_dialog()
        elif key == '+':
            self.select_by_pattern()
        elif key == '-':
            self.unselect_by_pattern()
        elif key == '*':
            active_panel = self.get_active_panel()
            active_panel.invert_selection()

    def select_by_pattern(self):
        def callback(confirmed, pattern):
            self.close_dialog()
            if confirmed:
                active_panel = self.get_active_panel()
                active_panel.select_by_pattern(pattern, select=True)

        dialog = InputDialog('Select files by pattern', 'Pattern: ', callback, default_text='*')
        self.show_dialog(dialog)

    def unselect_by_pattern(self):
        def callback(confirmed, pattern):
            self.close_dialog()
            if confirmed:
                active_panel = self.get_active_panel()
                active_panel.select_by_pattern(pattern, select=False)

        dialog = InputDialog('Unselect files by pattern', 'Pattern: ', callback, default_text='*')
        self.show_dialog(dialog)

    def delete_old_versions(self):
        active_panel = self.get_active_panel()

        if active_panel.mode != 's3' or not active_panel.current_bucket:
            self.show_result('This function works only with S3 objects')
            return

        selected_items = active_panel.get_selected_items()
        if not selected_items:
            focused = active_panel.get_focused_item()
            if focused and focused['type'] == 's3_file':
                selected_items = [focused]

        if not selected_items:
            self.show_result('No items selected')
            return

        versioned_items = []
        for item in selected_items:
            if item['type'] == 's3_file' and item.get('version_count', 1) > 1:
                versioned_items.append(item)

        if not versioned_items:
            self.show_result('No versioned files selected')
            return

        items_info = [f"{item['name']} ({item['version_count']} versions)" for item in versioned_items]

        def callback(confirmed):
            self.close_dialog()
            if confirmed:
                progress = ProgressDialog('Deleting old versions...', callback=self.close_dialog)
                progress.set_total(len(versioned_items))
                self.show_dialog(progress)

                def delete_thread():
                    for item in versioned_items:
                        if progress.cancelled:
                            break

                        self.loop.draw_screen()
                        progress.update(item['name'])

                        deleted = active_panel.s3_manager.delete_old_versions(
                            active_panel.current_bucket,
                            item['key']
                        )

                        if deleted > 0:
                            progress.add_success()
                        else:
                            progress.add_failure()

                    time.sleep(0.5)
                    self.loop.draw_screen()

                thread = threading.Thread(target=delete_thread)
                thread.daemon = True
                thread.start()

                def check_thread():
                    if thread.is_alive():
                        self.loop.set_alarm_in(0.1, lambda *args: check_thread())
                    else:
                        self.close_dialog()
                        active_panel.refresh()
                        self.show_result(f'Deleted old versions: {progress.success_count}, Failed: {progress.fail_count}')

                self.loop.set_alarm_in(0.1, lambda *args: check_thread())

        message = f'Delete old versions of {len(versioned_items)} file(s)?\nThis will keep only the latest version!'
        dialog = ConfirmDialog('Confirm Delete Old Versions', message, items_info, callback)
        self.show_dialog(dialog)

    def show_dialog(self, dialog):
        overlay = urwid.Overlay(
            dialog,
            self.frame,
            align='center',
            width=('relative', 80),
            valign='middle',
            height='pack'
        )
        self.loop.widget = overlay

    def close_dialog(self):
        self.loop.widget = self.main_widget

    def show_result(self, message):
        self.result_text.set_text(message)

    def get_active_panel(self):
        return self.left_panel if self.columns.focus_position == 0 else self.right_panel

    def get_inactive_panel(self):
        return self.right_panel if self.columns.focus_position == 0 else self.left_panel

    def create_directory(self):
        active_panel = self.get_active_panel()

        if active_panel.is_root_menu():
            self.show_result('Select FS or S3 endpoint first')
            return

        if active_panel.mode == 's3':
            if active_panel.is_bucket_list():
                def callback(confirmed, bucket_name):
                    self.close_dialog()
                    if confirmed:
                        if active_panel.s3_manager.create_bucket(bucket_name):
                            self.show_result(f'Created bucket: {bucket_name}')
                            active_panel.refresh(focus_on=bucket_name)
                        else:
                            self.show_result(f'Failed to create bucket: {bucket_name}')

                dialog = InputDialog('Create New Bucket', 'Bucket name: ', callback)
                self.show_dialog(dialog)
            elif active_panel.is_endpoint_list():
                self.show_result('Cannot create directory at endpoint level')
            else:
                self.show_result('Cannot create directory in S3 (use prefix when copying)')
        else:
            def callback(confirmed, dir_name):
                self.close_dialog()
                if confirmed:
                    if active_panel.fs_browser.create_directory(dir_name):
                        self.show_result(f'Created directory: {dir_name}')
                        active_panel.refresh(focus_on=dir_name)
                    else:
                        self.show_result(f'Failed to create directory: {dir_name}')

            dialog = InputDialog('Create New Directory', 'Directory name: ', callback)
            self.show_dialog(dialog)

    def analyze_items(self, items, source_panel):
        analyzed = []
        items_info = []
        total_bytes = 0

        for item in items:
            item_type = item['type']

            if item_type == 'fs_file':
                analyzed.append({'type': 'fs_file', 'item': item, 'files': [item]})
                items_info.append(f"[FILE] {item['name']}")
                total_bytes += item.get('size', 0)

            elif item_type == 'fs_dir':
                dir_path = os.path.join(source_panel.fs_browser.current_path, item['name'])
                all_files = source_panel.fs_browser.list_all_files(dir_path)
                analyzed.append({'type': 'fs_dir', 'item': item, 'files': all_files, 'dir_path': dir_path})
                items_info.append(f"[DIR ] {item['name']} ({len(all_files)} files)")
                total_bytes += sum(f['size'] for f in all_files)

            elif item_type == 's3_file':
                analyzed.append({'type': 's3_file', 'item': item, 'files': [item]})
                items_info.append(f"[FILE] {item['name']}")
                total_bytes += item.get('size', 0)

            elif item_type == 's3_dir':
                all_objects = source_panel.s3_manager.list_all_objects(source_panel.current_bucket, item['key'])
                analyzed.append({'type': 's3_dir', 'item': item, 'files': all_objects})
                items_info.append(f"[DIR ] {item['name']} ({len(all_objects)} objects)")
                total_bytes += sum(obj.get('Size', 0) for obj in all_objects)

            elif item_type == 'bucket':
                all_objects = source_panel.s3_manager.list_all_objects(item['name'], '')
                analyzed.append({'type': 'bucket', 'item': item, 'files': all_objects})
                items_info.append(f"[BUCKET] {item['name']} ({len(all_objects)} objects)")
                total_bytes += sum(obj.get('Size', 0) for obj in all_objects)

        return analyzed, items_info, total_bytes
