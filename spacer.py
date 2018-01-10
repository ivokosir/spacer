import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk
import os
import subprocess

class File:
    def __init__(self, entry):
        self.path = entry.path
        self.name = entry.name
        self.is_dir = entry.is_dir()
        self.icon = 'folder' if self.is_dir else 'text-x-generic'

    def rename(self, new_name):
        new_path = os.path.join(os.path.dirname(self.path), new_name)
        os.replace(self.path, new_path)
        self.path = new_path
        self.name = os.path.basename(self.path)


class FileView(Gtk.TreeView):
    def __init__(self):
        super().__init__()

        self.connect('key-press-event', self.on_key_press)
        self.connect('row-expanded', self.on_row_expanded)
        self.connect('row-collapsed', self.on_row_collapsed)
        self.connect('row-activated', self.on_row_activated)

        self.treestore = Gtk.TreeStore(object)
        self.set_model(self.treestore)

        self.file_name_column = Gtk.TreeViewColumn()
        file_type_renderer = Gtk.CellRendererPixbuf()
        self.file_name_renderer = Gtk.CellRendererText(editable=False)
        self.file_name_renderer.connect('edited', self.on_name_edit)
        self.file_name_column.pack_start(file_type_renderer, False)
        self.file_name_column.pack_start(self.file_name_renderer, False)
        self.file_name_column.set_cell_data_func(file_type_renderer, self.render_file_type_pix)
        self.file_name_column.set_cell_data_func(self.file_name_renderer, self.render_file_name)
        self.append_column(self.file_name_column)

        self.cwd = os.getcwd()
        self.refresh()

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Right:
            self.smart_expand()
            return True
        elif event.keyval == Gdk.KEY_Left:
            self.smart_colapse()
            return True
        elif event.keyval == Gdk.KEY_BackSpace:
            self.refresh(os.path.dirname(self.cwd))
            return True
        elif event.keyval == Gdk.KEY_F5:
            self.refresh()
            return True
        elif event.keyval == Gdk.KEY_F2:
            self.rename()
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

    def on_row_expanded(self, widget, tree_iter, path):
        child_iter = self.treestore.iter_children(tree_iter)
        while child_iter:
            file = self.treestore[child_iter][0]
            if file.is_dir:
                self.read_dir(file, child_iter)
            child_iter = self.treestore.iter_next(child_iter)

    def on_row_collapsed(self, widget, tree_iter, path):
        while self.treestore.remove(self.treestore.iter_children(tree_iter)):
            pass

        self.read_dir(self.treestore[tree_iter][0], tree_iter)

    def read_dir(self, file, tree_iter):
        with os.scandir(file.path) as entries:
            for entry in entries:
                self.treestore.append(tree_iter, [File(entry)])

    def on_row_activated(self, widget, path, col):
        file = self.treestore[path][0]
        if file.is_dir:
            self.refresh(file.path)
        else:
            subprocess.Popen(['xdg-open', file.path])

    def render_file_type_pix(self, col, renderer, model, tree_iter, user_data):
        file = model[tree_iter][0]
        renderer.set_property('icon-name', file.icon)

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

        with os.scandir(self.cwd) as entries:
            for entry in entries:
                file = File(entry)
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
