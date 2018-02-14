#!/usr/bin/env python3
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import os, subprocess
import urllib.parse, urllib.request
from filemodel import FileModel


class FileView(Gtk.TreeView):
    def __init__(self):
        super().__init__()

        self.connect('key-press-event', self.on_key_press)
        self.connect('row-activated', self.on_row_activated)

        targets = [Gtk.TargetEntry.new('text/uri-list', Gtk.TargetFlags.SAME_WIDGET, 0)]
        actions = Gdk.DragAction.COPY | Gdk.DragAction.MOVE
        self.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, targets, actions)
        self.enable_model_drag_dest(targets, actions)
        self.connect('drag-data-get', self.drag_data_get)
        self.connect('drag-data-received', self.drag_data_received)

        self.filemodel = FileModel(os.getcwd())
        self.filemodel.do_refresh = self.do_refresh
        self.filemodel.on_refresh = self.on_refresh
        self.set_model(self.filemodel)

        self.file_name_column = Gtk.TreeViewColumn('Name')
        self.file_name_column.set_sort_column_id(0)

        file_type_renderer = Gtk.CellRendererPixbuf()
        self.file_name_renderer = Gtk.CellRendererText()
        self.file_name_renderer.connect('edited', self.on_name_edit)
        self.file_name_column.pack_start(file_type_renderer, False)
        self.file_name_column.pack_start(self.file_name_renderer, False)
        self.file_name_column.set_cell_data_func(file_type_renderer, self.render_file_type_pix)
        self.file_name_column.set_cell_data_func(self.file_name_renderer, self.render_file_name)
        self.append_column(self.file_name_column)

    def on_key_press(self, treeview, event):
        if event.keyval == Gdk.KEY_Right:
            self.smart_expand()
            return True
        if event.keyval == Gdk.KEY_Left:
            self.smart_colapse()
            return True
        if event.keyval == Gdk.KEY_BackSpace:
            os.chdir(os.path.dirname(os.getcwd()))
            self.filemodel.refresh(os.getcwd())
            return True
        if event.keyval == Gdk.KEY_F5:
            self.filemodel.refresh()
            return True
        if event.keyval == Gdk.KEY_F2:
            self.rename()
            return True
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            if event.keyval == Gdk.KEY_h:
                self.filemodel.toggle_hidden()
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
            os.chdir(file.path)
            self.filemodel.refresh(os.getcwd())
        else:
            subprocess.Popen(['xdg-open', file.path])
            Gtk.main_quit()

    def do_refresh(self):
        selected = self.get_cursor().path
        opened = [Gtk.TreePath.new()]
        self.map_expanded_rows(lambda widget, path: opened.append(path))
        self.set_model(None)
        return (selected, opened)

    def on_refresh(self, selected, opened):
        self.set_model(self.filemodel)

        for o in opened:
            self.expand_row(o, False)

        if selected:
            self.set_cursor(selected, None)
        else:
            self.set_cursor(Gtk.TreePath.new_first())

    def render_file_type_pix(self, col, renderer, model, iter, user_data):
        file = model[iter][0]
        renderer.set_property('icon-name', 'folder' if file.is_dir else 'text-x-generic')

    def render_file_name(self, col, renderer, model, iter, user_data):
        file = model[iter][0]
        renderer.set_property('text', file.name)

    def rename(self):
        path = self.get_cursor().path
        self.file_name_renderer.set_property('editable', True)
        self.grab_focus()
        self.set_cursor_on_cell(path, self.file_name_column, self.file_name_renderer, True)

    def on_name_edit(self, renderer, path, new_name):
        renderer.set_property('editable', False)
        ok, ret = self.filemodel.rename(path, new_name)
        if not ok: self.show_error(msg)
        if ret: self.set_cursor(ret, None)

    def drag_data_get(self, treeview, context, selection, info, time):
        path = self.get_cursor().path
        filepath = self.filemodel[path][0].path
        uri = urllib.parse.urljoin('file:', urllib.request.pathname2url(filepath))
        selection.set_uris([uri])

    def drag_data_received(self, treeview, context, x, y, selection, info, time):
        dst = self.get_dest_row_at_pos(x, y)

        if dst:
            path, pos = dst
            indices = path.get_indices()
            is_into = pos in [
                Gtk.TreeViewDropPosition.INTO_OR_BEFORE,
                Gtk.TreeViewDropPosition.INTO_OR_AFTER
            ]
            if not is_into: indices.pop()
        else:
            indices = []

        action = context.get_selected_action()

        uris = selection.get_uris()
        if not uris:
            context.finish(True, False, time)
            return
        src_filepath = urllib.request.url2pathname(urllib.parse.urlparse(uris[0]).path)

        ok, delete, result = self.filemodel.custom_drag_data_received(indices, src_filepath, action)
        if ok:
            if result:
                self.expand_to_path(result)
                self.set_cursor(result, None, False)
        context.finish(ok, delete, time)
        if not ok:
            self.show_error(result)

    def show_error(self, msg):
        dialog = Gtk.MessageDialog(
            parent=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            message_format=msg
        )
        dialog.run()
        dialog.destroy()
