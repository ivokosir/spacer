#!/usr/bin/env python3

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import subprocess
import urllib.parse, urllib.request
from filemodel import FileModel


class FileView(Gtk.TreeView):
    def __init__(self):
        super().__init__()

        self.connect('key-press-event', self.on_key_press)
        #self.connect('row-activated', self.on_row_activated)

        targets = [Gtk.TargetEntry.new('text/uri-list', Gtk.TargetFlags.SAME_WIDGET, 0)]
        actions = Gdk.DragAction.COPY | Gdk.DragAction.MOVE
        self.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, targets, actions)
        self.enable_model_drag_dest(targets, actions)
        self.connect('drag-data-get', self.drag_data_get)
        self.connect('drag-data-received', self.drag_data_received)

        self.filemodel = FileModel('/home/ivo/spacer/test')
        self.set_model(self.filemodel)

        self.file_name_column = Gtk.TreeViewColumn()
        file_type_renderer = Gtk.CellRendererPixbuf()
        self.file_name_renderer = Gtk.CellRendererText()
        self.file_name_renderer.connect('edited', self.on_name_edit)
        self.file_name_column.pack_start(file_type_renderer, False)
        self.file_name_column.pack_start(self.file_name_renderer, False)
        self.file_name_column.set_cell_data_func(file_type_renderer, self.render_file_type_pix)
        self.file_name_column.set_cell_data_func(self.file_name_renderer, self.render_file_name)
        self.append_column(self.file_name_column)

        #self.show_hidden = False
        #self.cwd = os.getcwd()

    def on_key_press(self, treeview, event):
        if event.keyval == Gdk.KEY_Right:
            self.smart_expand()
            return True
        if event.keyval == Gdk.KEY_Left:
            self.smart_colapse()
            return True
        if event.keyval == Gdk.KEY_BackSpace:
            #self.refresh(os.path.dirname(self.cwd))
            return True
        if event.keyval == Gdk.KEY_F5:
            #self.refresh()
            return True
        if event.keyval == Gdk.KEY_F2:
            #self.rename()
            return True
        if event.state == Gdk.ModifierType.CONTROL_MASK:
            if event.keyval == Gdk.KEY_h:
                #self.toggle_hidden()
                return True
        return False

    def smart_expand(self):
        path = self.get_cursor().path
        if path is None: return
        self.expand_row(path, False)
        child_iter = self.filemodel.iter_children(self.filemodel.get_iter(path))
        if child_iter:
            self.set_cursor(self.filemodel.get_path(child_iter), None, False)

    def smart_colapse(self):
        path = self.get_cursor().path
        if path is None: return
        if not self.collapse_row(path):
            parent_iter = self.filemodel.iter_parent(self.filemodel.get_iter(path))
            if parent_iter:
                parent_path = self.filemodel.get_path(parent_iter)
                self.set_cursor(parent_path, None, False)
                self.collapse_row(parent_path)

    def on_row_activated(self, treeview, path, col):
        file = self.filemodel[path][0]
        if file.is_dir:
            self.refresh(file.path)
        else:
            subprocess.Popen(['xdg-open', file.path])

    def render_file_type_pix(self, col, renderer, model, iter, user_data):
        file = model[iter][0]
        renderer.set_property('icon-name', 'folder' if file.is_dir else 'text-x-generic')

    def render_file_name(self, col, renderer, model, iter, user_data):
        file = model[iter][0]
        renderer.set_property('text', file.name)

    def on_name_edit(self, renderer, path, new_text):
        renderer.set_property('editable', False)
        file = self.filemodel[path][0]
        file.rename(new_text)
        self.refresh()

    def refresh(self, new_cwd=None):
        opened = [self.cwd]
        self.map_expanded_rows(lambda widget, path: opened.append(self.filemodel[path][0].path))
        selected_path = self.get_cursor().path
        selected = self.filemodel[selected_path][0].path if selected_path else None

        self.filemodel.clear()

        self.cwd = os.fspath(new_cwd) if new_cwd else self.cwd
        while True:
            try:
                os.chdir(self.cwd)
                break
            except FileNotFoundError:
                self.cwd = os.path.dirname(self.cwd)

        def maybe_open_or_select(file, iter):
            if file.path in opened:
                opened.remove(file.path)
                self.expand_row(self.filemodel.get_path(iter), False)

                child_iter = self.filemodel.iter_children(iter)
                while child_iter:
                    child_file = self.filemodel[child_iter][0]
                    maybe_open_or_select(child_file, child_iter)
                    child_iter = self.filemodel.iter_next(child_iter)
            if file.path == selected:
                self.set_cursor(self.filemodel.get_path(iter), None)

        for file in File.list(self.cwd, self.show_hidden):
            child_iter = self.filemodel.append(None, [file])
            if file.is_dir:
                self.read_dir(file, child_iter)
            maybe_open_or_select(file, child_iter)

        new_selected_path = self.get_cursor().path
        if new_selected_path is None:
            first = self.filemodel.get_iter_first()
            if first:
                self.set_cursor(self.filemodel.get_path(first), None)

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
        path = self.get_cursor().path
        filepath = self.filemodel[path][0].path
        uri = urllib.parse.urljoin('file:', urllib.request.pathname2url(filepath))
        selection.set_uris([uri])

    def drag_data_received(self, treeview, context, x, y, selection, info, time):
        dst = self.get_dest_row_at_pos(x, y)

        if dst:
            path, pos = dst
            is_into = pos in [
                Gtk.TreeViewDropPosition.INTO_OR_BEFORE,
                Gtk.TreeViewDropPosition.INTO_OR_AFTER
            ]
            if is_into: path.down()
        else:
            path = Gtk.TreePath.new_first()

        action = context.get_selected_action()

        uris = selection.get_uris()
        if not uris:
            context.finish(True, False, time)
            return
        src_filepath = urllib.request.url2pathname(urllib.parse.urlparse(uris[0]).path)

        ok, delete, result = self.filemodel.custom_drag_data_received(path, src_filepath, action)
        context.finish(ok, delete, time)
        if ok:
            if result:
                self.expand_to_path(result)
                self.set_cursor(result, None, False)
        else:
            dialog = Gtk.MessageDialog(
                parent=self.get_toplevel(),
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                message_format=result
            )
            dialog.run()
            dialog.destroy()


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
