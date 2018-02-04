from gi.repository import GObject, Gtk, Gdk
import os, shutil
import locale, functools

class File:
    def __init__(self, parent_id, path, *, name=None, is_dir=None, child_ids=None):
        self.parent_id = parent_id
        self.path = path

        if name is None: self.update_name()
        else: self.name = name

        if is_dir is None: self.update_is_dir()
        else: self.is_dir = is_dir

        self.child_ids = child_ids

    def update_path(self):
        self.path = os.path.join(os.path.dirname(self.path), self.name)

    def update_name(self):
        self.name = os.path.basename(self.path)

    def update_is_dir(self):
        self.is_dir = os.path.isdir(self.path)

    def is_hidden(self):
        return self.name.startswith('.')

    def rename(self, new_name):
        new_path = os.path.join(os.path.dirname(self.path), new_name)
        try:
            os.replace(self.path, new_path)
        except Exception as e:
            return (False, str(e))
        self.name = new_name
        self.path = new_path
        return (True, None)

    def list(self):
        if not self.is_dir: return []
        try:
            with os.scandir(self.path) as entries:
                def entry_to_file(entry):
                    child = self.__class__(self.id, entry.path,
                        name=entry.name, is_dir=entry.is_dir()
                    )
                    return child
                children = [entry_to_file(entry) for entry in entries]
        except PermissionError:
            children = []
        return children


class FileModel(
        GObject.GObject, Gtk.TreeModel, Gtk.TreeSortable,
        Gtk.TreeDragSource, Gtk.TreeDragDest
):
    def __init__(self, dir):
        GObject.GObject.__init__(self)

        self.do_refresh = lambda: (None, [])
        self.on_refresh = lambda selected, opened: None

        self.show_hidden = False
        self.sort_order = Gtk.SortType.ASCENDING

        self.refresh(dir)

    def refresh(self, new_path=None):
        if new_path is None: new_path = self.files[0].path

        selected, opened = self.do_refresh()

        def get_filepath_from_path(path):
            if path is None: return None
            indices = path.get_indices()
            id = self.get_id_from_indices(indices) if indices else 0
            if id is None: return None
            return self.files[id].path

        selected = get_filepath_from_path(selected)
        opened = [get_filepath_from_path(path) for path in opened]
        opened = [o for o in opened if o]

        self.files = []
        root = File(None, new_path, is_dir=True)
        self.add_files(root)
        self.update_children(root)

        def get_path_from_filepath(filepath):
            if filepath is None: return None
            file = self.get_file_from_filepath(filepath)
            if file is None or file.id == 0: return None
            return self.get_path_from_id(file.id)

        selected = get_path_from_filepath(selected)
        opened = [get_path_from_filepath(o) for o in opened]
        opened = [o for o in opened if o]

        self.on_refresh(selected, opened)

    def toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        self.refresh()

    def add_files(self, *files):
        first_id = len(self.files)
        for i, file in enumerate(files):
            file.id = first_id + i
        self.files.extend(files)

    def update_children(self, file, *, force_update=False):
        if not file.is_dir: return
        if file.child_ids is not None and not force_update: return

        if file.child_ids is None:
            children = file.list()
            self.add_files(*children)
            file.child_ids = [child.id for child in children]

        def key(id):
            return locale.strxfrm(self.files[id].path)
        reverse = self.sort_order == Gtk.SortType.DESCENDING
        file.child_ids = list(sorted(file.child_ids, key=key, reverse=reverse))

        file.child_ids = [
            c for c in file.child_ids
            if self.show_hidden or not self.files[c].is_hidden()
        ]

    def file_id_is_valid(self, id):
        return (id is not None) and (id > 0 and id < len(self.files))

    def iter_is_valid(self, iter):
        return iter and self.file_id_is_valid(iter.user_data)

    def new_iter(self, id, iter=None):
        if not self.file_id_is_valid(id): return None

        if iter is None: iter = Gtk.TreeIter()
        iter.user_data = id
        return iter

    def with_iter(self, get_id, iter, fallback=False):
        if (iter is None or iter.user_data == 0) and fallback:
            id = 0
        elif self.iter_is_valid(iter):
            id = iter.user_data
        else:
            return (None, False)

        new_id = get_id(id)

        iter = self.new_iter(new_id, iter)
        return (True, iter) if iter else (False, None)

    def get_file_from_filepath(self, filepath, *, file=None):
        if file is None: file = self.files[0]

        if os.path.commonpath([file.path, filepath]) != file.path: return None
        if file.path == filepath: return file

        self.update_children(file)

        if file.child_ids == None: return None
        for id in file.child_ids:
            child = self.files[id]
            child = self.get_file_from_filepath(filepath, file=child)
            if child is not None: return child
        return None

    def get_id_from_indices(self, indices):
        id = 0
        for i in indices:
            id = self.get_id_nth_child(id, i)
            if id is None: return None
        return id

    def do_get_iter(self, path):
        get_id = lambda _: self.get_id_from_indices(path.get_indices())
        return self.with_iter(get_id, None, fallback=True)

    def get_id_nth_child(self, id, i):
        file = self.files[id]
        self.update_children(file)
        if not file.child_ids: return None
        if i >= 0 and i < len(file.child_ids): return file.child_ids[i]
        return None

    def do_iter_nth_child(self, iter, n):
        return self.with_iter(lambda id: self.get_id_nth_child(id, n), iter, fallback=True)

    def get_id_next(self, id):
        file = self.files[id]
        parent = self.files[file.parent_id]
        return self.get_id_nth_child(file.parent_id, parent.child_ids.index(id) + 1)

    def do_iter_next(self, iter):
        return self.with_iter(self.get_id_next, iter)

    def get_id_previous(self, id):
        file = self.files[id]
        parent = self.files[file.parent_id]
        return self.get_id_nth_child(file.parent_id, parent.child_ids.index(id) - 1)

    def do_iter_previous(self, iter):
        return self.with_iter(self.get_id_previous, iter)

    def do_iter_has_child(self, iter):
        if not self.iter_is_valid(iter): return False
        file = self.files[iter.user_data]
        self.update_children(file)
        return bool(file.child_ids)

    def do_iter_n_children(self, iter):
        if not self.iter_is_valid(iter): return 0
        file = self.files[iter.user_data]
        self.update_children(file)
        return len(file.child_ids)

    def do_iter_children(self, iter):
        return self.with_iter(lambda id: self.get_id_nth_child(id, 0), iter)

    def get_id_parent(self, id):
        return self.files[id].parent_id

    def do_iter_parent(self, iter):
        return self.with_iter(self.get_id_parent, iter)

    def get_path_from_id(self, id):
        indices = []
        while True:
            file = self.files[id]
            parent = self.files[file.parent_id]
            indices.insert(0, parent.child_ids.index(id))
            id = file.parent_id
            if id == 0: break

        return Gtk.TreePath(indices)

    def do_get_path(self, iter):
        if not self.iter_is_valid(iter): return None
        return self.get_path_from_id(iter.user_data)

    def do_get_value(self, iter, column):
        if not self.iter_is_valid(iter): return None
        return self.files[iter.user_data]

    def do_get_column_type(self, column):
        return object

    def do_get_n_columns(self):
        return 1

    def do_get_flags(self):
        return 0

    def rename(self, path, new_name):
        file = self[path][0]
        ok, ret = file.rename(new_name)

        if ok:
            parent = self.files[file.parent_id]
            self.update_children(parent, force_update=True)
            self.row_deleted(path)

            if not self.show_hidden and file.is_hidden():
                if file.parent_id != 0:
                    iter = self.new_iter(file.parent_id)
                    path = self.get_path_from_id(file.parent_id)
                    self.row_has_child_toggled(path, iter)
                return (True, None)

            path = self.get_path_from_id(file.id)
            iter = self.new_iter(file.id)
            self.row_inserted(path, iter)
            self.row_has_child_toggled(path, iter)
            ret = path

        return (ok, ret)

    def custom_drag_data_received(self, indices, src_filepath, action):
        is_move = action == Gdk.DragAction.MOVE

        parent_id = self.get_id_from_indices(indices)
        parent = self.files[parent_id]
        if not parent.is_dir:
            parent_id = parent.parent_id
            parent = self.files[parent_id]

        dst_filepath = os.path.join(parent.path, os.path.basename(src_filepath))

        if is_move and src_filepath == dst_filepath: return (True, False, None)

        existing_file_counter = 1
        while os.path.lexists(dst_filepath) == True:
            root, ext = os.path.splitext(dst_filepath)
            dst_filepath = root + ' (' + str(existing_file_counter) + ')' + ext

        try:
            if is_move:
                os.replace(src_filepath, dst_filepath)
            else:
                try:
                    shutil.copyfile(src_filepath, dst_filepath)
                except IsADirectoryError:
                    shutil.copytree(src_filepath, dst_filepath, copy_function=shutil.copyfile)
        except Exception as e: return (False, False, str(e))

        file = File(parent_id, dst_filepath)
        if not self.show_hidden and file.is_hidden(): return (True, is_move, path)
        self.add_files(file)

        id = file.id
        parent.child_ids.append(id)
        self.update_children(parent)

        path = self.get_path_from_id(id)
        iter = self.new_iter(id)
        self.row_inserted(path, iter)
        self.row_has_child_toggled(path, iter)

        return (True, is_move, path)

    def do_drag_data_delete(self, path):
        *indices, i = path.get_indices()
        parent_id = self.get_id_from_indices(indices)
        del self.files[parent_id].child_ids[i]

        self.row_deleted(path)
        iter = self.new_iter(parent_id)
        if path.up() and iter:
            self.row_has_child_toggled(path, iter)
        return True

    def do_drag_data_get(self, path, selection):
        return False

    def do_row_draggable(self, path):
        return True

    def do_drag_data_received(self, dst_path, selection):
        return False

    def do_row_drop_possible(self, path, selection):
        return True

    def do_get_sort_column_id(self):
        return (True, 0, self.sort_order)

    def do_has_default_sort_func(self):
        return False

    def do_set_sort_column_id(self, sort_column_id, order):
        self.sort_order = order
        self.refresh()
        self.sort_column_changed()
