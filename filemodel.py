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

    def __str__(self):
        return self.path

    def __repr__(self):
        return "File('" + self.path + "')"


class FileModel(
        GObject.GObject, Gtk.TreeModel, Gtk.TreeSortable,
        Gtk.TreeDragSource, Gtk.TreeDragDest
):
    def __init__(self, dir):
        GObject.GObject.__init__(self)

        self.sort_order = Gtk.SortType.ASCENDING
        self.sort_func = lambda m, a, b: locale.strcoll(m[a][0].path, m[b][0].path)

        self.stamp = 0

        self.files = []
        root = File(None, dir, is_dir=True)
        self.add_files(root)
        self.update_children(root)

    def add_files(self, *files):
        first_id = len(self.files)
        for i, file in enumerate(files):
            file.id = first_id + i
        self.files.extend(files)

    def update_children(self, file):
        if not file.is_dir or file.child_ids is not None: return

        children = file.list()
        self.add_files(*children)
        file.child_ids = [child.id for child in children]
        self.sort(file)

    def file_id_is_valid(self, id):
        return (id is not None) and (id > 0 and id < len(self.files))

    def iter_is_valid(self, iter):
        return iter and (iter.stamp == self.stamp and self.file_id_is_valid(iter.user_data))

    def new_iter(self, id, iter=None):
        if not self.file_id_is_valid(id): return None

        if iter is None:
            iter = Gtk.TreeIter()
            iter.stamp = self.stamp
        iter.user_data = id
        return iter

    def with_iter(self, get_id, iter, fallback=False):
        if iter is None and fallback:
            id = 0
        elif self.iter_is_valid(iter):
            id = iter.user_data
        else:
            return (None, False)

        new_id = get_id(id)

        iter = self.new_iter(new_id, iter)
        return (True, iter) if iter else (False, None)

    def get_file_from_filepath(self, filepath, file=None):
        if file is None: file = self.files[0]

        if os.path.commonpath([file.path, filepath]) != file.path: return None
        if file.path == filepath: return file

        if file.child_ids == None: return None
        for id in file.child_ids:
            child = self.files[id]
            child = self.get_file_from_filepath(filepath, child)
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
        if not self.iter_is_valid(iter): None
        return self.files[iter.user_data]

    def do_get_column_type(self, column):
        return object

    def do_get_n_columns(self):
        return 1

    def do_get_flags(self):
        return 0

    def rename(self, path, new_name):
        file = self[path][0]
        ok, msg = file.rename(new_name)
        if ok:
            self.row_changed(path, self.new_iter(file.id))
        return (ok, msg)

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

        if is_move:
            file = self.get_file_from_filepath(src_filepath)
            file.parent_id = parent_id
            file.path = dst_filepath
            file.update_name()
            file.update_is_dir()
        else:
            file = File(parent_id, dst_filepath)
            self.add_files(file)

        id = file.id
        parent.child_ids.append(id)
        self.sort(parent)

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

    def sort(self, file, *, emit_signal=False, recursive=False):
        if not file.child_ids: return

        def cmp(fst, snd):
            _, fst_id = fst
            _, snd_id = snd
            fst_iter = self.new_iter(fst_id)
            snd_iter = self.new_iter(snd_id)

            if self.sort_order == Gtk.SortType.ASCENDING:
                a, b = (fst_iter, snd_iter)
            elif self.sort_order == Gtk.SortType.DESCENDING:
                b, a = (fst_iter, snd_iter)

            return self.sort_func(self, a, b)

        sort_key = functools.cmp_to_key(cmp)

        sorted_with_i = list(sorted(enumerate(file.child_ids), key=sort_key))
        file.child_ids = [child for _, child in sorted_with_i]
        reordered_ids = [i for i, _ in sorted_with_i]

        if emit_signal:
            if file.id != 0:
                path = self.get_path_from_id(file.id)
                iter = self.new_iter(file.id)
            else:
                path = Gtk.TreePath()
                iter = None
            self.rows_reordered(path, iter, reordered_ids)

        if recursive:
            for child_id in file.child_ids:
                child = self.files[child_id]
                self.sort(child, emit_signal=emit_signal, recursive=recursive)

    def do_get_sort_column_id(self):
        print('get', 0, self.sort_order)
        return (True, 0, self.sort_order)

    def do_has_default_sort_func(self):
        return False

    def do_set_default_sort_func(self, sort_func, user_data):
        pass

    def do_set_sort_column_id(self, sort_column_id, order):
        self.sort_order = order
        self.sort(self.files[0], emit_signal=True, recursive=True)
        self.sort_column_changed()
        print('set', sort_column_id, self.sort_order)

    def do_set_sort_func(self, sort_column_id, sort_func, user_data):
        self.sort_func = lambda model, a, b: sort_func(model, a, b, user_data)

    def do_sort_column_changed(self):
        print('do_sort_column_changed')

#    def do_row_changed(self, path, iter):
#        pass

#    def do_row_deleted(self, path):
#        pass

#    def do_row_has_child_toggled(self, path, iter):
#        pass

#    def do_row_inserted(self, path, iter):
#        pass
