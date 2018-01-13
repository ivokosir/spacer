#!/usr/bin/env python3

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import os, subprocess
import urllib.parse, urllib.request
import locale

class File:
    def rename(self, new_name):
        old_path = self.path
        self.path = os.path.join(os.path.dirname(self.path), new_name)
        self.name = os.path.basename(self.path)
        os.replace(old_path, self.path)

    @classmethod
    def move(cls, old_path, new_dir):
        file = cls()
        file.name = os.path.basename(old_path)
        file.path = os.path.join(new_dir, file.name)
        file.is_dir = os.path.isdir(old_path)
        try:
            os.replace(old_path, file.path)
        except OSError as err:
            if err.errno == 22:
                return None
            raise err
        return file

    @classmethod
    def list(cls, dir, show_hidden):
        if isinstance(dir, cls):
            dir = dir.path

        try:
            with os.scandir(dir) as entries:
                for entry in entries:
                    file = cls()
                    file.path = entry.path
                    file.name = entry.name
                    file.is_dir = entry.is_dir()
                    if not file.name.startswith('.') or show_hidden:
                        yield file
        except PermissionError: pass


class FileView(Gtk.TreeView):
    def __init__(self):
        super().__init__()

        self.connect('key-press-event', self.on_key_press)
        self.connect('row-expanded', self.on_row_expanded)
        self.connect('row-collapsed', self.on_row_collapsed)
        self.connect('row-activated', self.on_row_activated)

        self.treestore = Gtk.TreeStore(object)
        self.treestore.set_sort_func(0, self.sort_by_name)
        self.treestore.set_sort_column_id(0, Gtk.SortType.ASCENDING)
        self.set_model(self.treestore)

        self.file_name_column = Gtk.TreeViewColumn()
        file_type_renderer = Gtk.CellRendererPixbuf()
        self.file_name_renderer = Gtk.CellRendererText()
        self.file_name_renderer.connect('edited', self.on_name_edit)
        self.file_name_column.pack_start(file_type_renderer, False)
        self.file_name_column.pack_start(self.file_name_renderer, False)
        self.file_name_column.set_cell_data_func(file_type_renderer, self.render_file_type_pix)
        self.file_name_column.set_cell_data_func(self.file_name_renderer, self.render_file_name)
        self.append_column(self.file_name_column)

        targets = [Gtk.TargetEntry.new('text/uri-list', Gtk.TargetFlags.SAME_WIDGET, 0)]
        self.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, targets, Gdk.DragAction.MOVE)
        self.enable_model_drag_dest(targets, Gdk.DragAction.MOVE)
        self.connect('drag-data-get', self.drag_data_get)
        self.connect('drag-data-received', self.drag_data_received)
        self.connect('drag-end', self.drag_end)

        self.show_hidden = False
        self.cwd = os.getcwd()
        self.refresh()

    def on_key_press(self, treeview, event):
        if event.keyval == Gdk.KEY_Right:
            self.smart_expand()
            return True
        if event.keyval == Gdk.KEY_Left:
            self.smart_colapse()
            return True
        if event.keyval == Gdk.KEY_BackSpace:
            self.refresh(os.path.dirname(self.cwd))
            return True
        if event.keyval == Gdk.KEY_F5:
            self.refresh()
            return True
        if event.keyval == Gdk.KEY_F2:
            self.rename()
            return True
        if event.state == Gdk.ModifierType.CONTROL_MASK:
            if event.keyval == Gdk.KEY_h:
                self.toggle_hidden()
                return True
        return False

    def smart_expand(self):
        path = self.get_cursor().path
        if path is None: return
        self.expand_row(path, False)
        child_iter = self.treestore.iter_children(self.treestore.get_iter(path))
        if child_iter:
            self.set_cursor(self.treestore.get_path(child_iter), None, False)

    def smart_colapse(self):
        path = self.get_cursor().path
        if path is None: return
        if not self.collapse_row(path):
            parent_iter = self.treestore.iter_parent(self.treestore.get_iter(path))
            if parent_iter:
                parent_path = self.treestore.get_path(parent_iter)
                self.set_cursor(parent_path, None, False)
                self.collapse_row(parent_path)

    def on_row_expanded(self, treeview, tree_iter, path):
        child_iter = self.treestore.iter_children(tree_iter)
        while child_iter:
            file = self.treestore[child_iter][0]
            if file.is_dir:
                self.read_dir(file, child_iter)
            child_iter = self.treestore.iter_next(child_iter)

    def on_row_collapsed(self, treeview, tree_iter, path):
        while self.treestore.remove(self.treestore.iter_children(tree_iter)):
            pass

        self.read_dir(self.treestore[tree_iter][0], tree_iter)

    def read_dir(self, dir, tree_iter):
        for file in File.list(dir, self.show_hidden):
            self.treestore.append(tree_iter, [file])

    def on_row_activated(self, treeview, path, col):
        file = self.treestore[path][0]
        if file.is_dir:
            self.refresh(file.path)
        else:
            subprocess.Popen(['xdg-open', file.path])

    def render_file_type_pix(self, col, renderer, model, tree_iter, user_data):
        file = model[tree_iter][0]
        renderer.set_property('icon-name', 'folder' if file.is_dir else 'text-x-generic')

    def render_file_name(self, col, renderer, model, tree_iter, user_data):
        file = model[tree_iter][0]
        renderer.set_property('text', file.name)

    def on_name_edit(self, renderer, path, new_text):
        renderer.set_property('editable', False)
        file = self.treestore[path][0]
        file.rename(new_text)
        self.refresh()

    def refresh(self, new_cwd=None):
        opened = [self.cwd]
        self.map_expanded_rows(lambda widget, path: opened.append(self.treestore[path][0].path))
        selected_path = self.get_cursor().path
        selected = self.treestore[selected_path][0].path if selected_path else None

        self.treestore.clear()

        self.cwd = os.fspath(new_cwd) if new_cwd else self.cwd
        while True:
            try:
                os.chdir(self.cwd)
                break
            except FileNotFoundError:
                self.cwd = os.path.dirname(self.cwd)

        def maybe_open_or_select(file, tree_iter):
            if file.path in opened:
                opened.remove(file.path)
                self.expand_row(self.treestore.get_path(tree_iter), False)

                child_iter = self.treestore.iter_children(tree_iter)
                while child_iter:
                    child_file = self.treestore[child_iter][0]
                    maybe_open_or_select(child_file, child_iter)
                    child_iter = self.treestore.iter_next(child_iter)
            if file.path == selected:
                self.set_cursor(self.treestore.get_path(tree_iter), None)

        for file in File.list(self.cwd, self.show_hidden):
            child_iter = self.treestore.append(None, [file])
            if file.is_dir:
                self.read_dir(file, child_iter)
            maybe_open_or_select(file, child_iter)

        new_selected_path = self.get_cursor().path
        if new_selected_path is None:
            first = self.treestore.get_iter_first()
            if first:
                self.set_cursor(self.treestore.get_path(first), None)

    def rename(self):
        path = self.get_cursor().path
        self.file_name_renderer.set_property('editable', True)
        self.grab_focus()
        self.set_cursor_on_cell(path, self.file_name_column, self.file_name_renderer, True)

    def sort_by_name(self, model, iter_a, iter_b, x):
        a = model[iter_a][0].path
        b = model[iter_b][0].path
        return locale.strcoll(a, b)

    def toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        self.refresh()

    def drag_data_get(self, treeview, context, selection, info, time):
        path = self.treestore[self.get_cursor().path][0].path
        uri = urllib.parse.urljoin('file:', urllib.request.pathname2url(path))
        selection.set_uris([uri])

    def drag_data_received(self, treeview, context, x, y, selection, info, time):
        uri = selection.get_uris()[0]
        path = urllib.request.url2pathname(urllib.parse.urlparse(uri).path)

        dest = self.get_dest_row_at_pos(x, y)
        if dest:
            target_path, pos = dest
            target_iter = self.treestore.get_iter(target_path)

            target_file = self.treestore[target_path][0]

            is_into = target_file.is_dir and pos in [
                Gtk.TreeViewDropPosition.INTO_OR_BEFORE,
                Gtk.TreeViewDropPosition.INTO_OR_AFTER
            ]
            is_before = not is_into and pos in [
                Gtk.TreeViewDropPosition.BEFORE,
                Gtk.TreeViewDropPosition.INTO_OR_BEFORE
            ]
            is_after = not is_into and pos in [
                Gtk.TreeViewDropPosition.AFTER,
                Gtk.TreeViewDropPosition.INTO_OR_AFTER
            ]

            dir = target_file.path if is_into else os.path.dirname(target_file.path)
        else:
            target_iter = None
            is_into, is_before, is_after = (True, False, False)
            dir = self.cwd

        new_file = File.move(path, dir)

        if new_file:
            if is_into:
                iter = self.treestore.append(target_iter, [new_file])
            elif is_before:
                iter = self.treestore.insert_before(None, target_iter, [new_file])
            elif is_after:
                iter = self.treestore.insert_after(None, target_iter, [new_file])

            self.set_cursor(self.treestore.get_path(iter), None, False)

        is_deleted = bool(new_file)
        context.finish(True, is_deleted, time)

    def drag_end(self, treeview, context):
        self.refresh()


def main():
    fileview = FileView()
    scrolledwindow = Gtk.ScrolledWindow()
    scrolledwindow.add(fileview)
    window = Gtk.Window(title='Spacer')
    window.connect('delete-event', Gtk.main_quit)
    window.add(scrolledwindow)
    window.show_all()

    Gtk.main()

if __name__ == '__main__':
    main()
