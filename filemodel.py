from gi.repository import GObject, Gtk, Gdk
import os, shutil
import locale, functools

class File:
    def __init__(self, filepath, *, name=None, is_dir=None):
        if filepath is None: return
        self.path = filepath
        self.name = name if name is not None else os.path.basename(filepath)
        self.is_dir = is_dir if is_dir is not None else os.path.isdir(filepath)

    def list(self):
        if not self.is_dir: return []
        try:
            with os.scandir(self.path) as entries:
                def to_file(entry):
                    return self.__class__(entry.path, name=entry.name, is_dir=entry.is_dir())
                children = [to_file(entry) for entry in entries]
        except PermissionError:
            children = []
        return children

    def __str__(self):
        return self.path

    def __repr__(self):
        return "File('" + self.path + "')"


class FileModel(
        GObject.GObject, Gtk.TreeModel, #Gtk.TreeSortable,
        Gtk.TreeDragSource, Gtk.TreeDragDest
):
    def __init__(self, dir):
        GObject.GObject.__init__(self)

        self.sort_order = Gtk.SortType.ASCENDING
        self.sort_func = lambda m, a, b: locale.strcoll(m[a][0].path, m[b][0].path)

        self.stamp = 0
        self.ids = [(File(dir, is_dir=True), None, None)]
        self.update_children(0)

    def update_children(self, id):
        file, parent_id, child_ids = self.ids[id]

        if not file.is_dir or child_ids is not None: return

        first_id = len(self.ids)
        self.ids.extend([(child_file, id, None) for child_file in file.list()])
        last_id = len(self.ids)
        child_ids = list(range(first_id, last_id))
        self.ids[id] = (file, parent_id, child_ids)
        #self.sort(id)

    def file_id_is_valid(self, id):
        return (id is not None) and (id > 0 and id < len(self.ids))

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

    def get_id_from_filepath(self, filepath, id=0):
        file, _, child_ids = self.ids[id]

        if os.path.commonpath([file.path, filepath]) != file.path: return None
        if file.path == filepath: return id

        if child_ids == None: return None
        for id in child_ids:
            id = self.get_id_from_filepath(filepath, id)
            if id is not None: return id
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
        self.update_children(id)
        child_ids = self.ids[id][2]
        if not child_ids: return None
        if i >= 0 and i < len(child_ids): return child_ids[i]
        return None

    def do_iter_nth_child(self, iter, n):
        return self.with_iter(lambda id: self.get_id_nth_child(id, n), iter, fallback=True)

    def get_id_next(self, id):
        parent_id = self.ids[id][1]
        sibling_ids = self.ids[parent_id][2]
        return self.get_id_nth_child(parent_id, sibling_ids.index(id) + 1)

    def do_iter_next(self, iter):
        return self.with_iter(self.get_id_next, iter)

    def get_id_previous(self, id):
        parent_id = self.ids[id][1]
        sibling_ids = self.ids[parent_id][2]
        return self.get_id_nth_child(parent_id, sibling_ids.index(id) - 1)

    def do_iter_previous(self, iter):
        return self.with_iter(self.get_id_previous, iter)

    def do_iter_has_child(self, iter):
        if not self.iter_is_valid(iter): return False
        self.update_children(iter.user_data)
        child_ids = self.ids[iter.user_data][2]
        return bool(child_ids)

    def do_iter_n_children(self, iter):
        if not self.iter_is_valid(iter): return 0
        self.update_children(iter.user_data)
        child_ids = self.ids[iter.user_data][2]
        return len(child_ids)

    def do_iter_children(self, iter):
        return self.with_iter(lambda id: self.get_id_nth_child(id, 0), iter)

    def get_id_parent(self, id):
        return self.ids[id][1]

    def do_iter_parent(self, iter):
        return self.with_iter(self.get_id_parent, iter)

    def get_path_from_id(self, id):
        indices = []
        while True:
            parent_id = self.ids[id][1]
            sibling_ids = self.ids[parent_id][2]
            indices.insert(0, sibling_ids.index(id))
            id = parent_id
            if parent_id == 0: break

        return Gtk.TreePath(indices)

    def do_get_path(self, iter):
        if not self.iter_is_valid(iter): return None
        return self.get_path_from_id(iter.user_data)

    def do_get_value(self, iter, column):
        if not self.iter_is_valid(iter): None
        return self.ids[iter.user_data][0]

    def do_get_column_type(self, column):
        return object

    def do_get_n_columns(self):
        return 1

    def do_get_flags(self):
        return 0

    def sort(self, id=0):
        def cmp(a_id, b_id):
            a = self.new_iter(a_id)
            b = self.new_iter(b_id)
            return self.sort_func(self, a, b)
        child_ids = self.ids[id][2]
        child_ids.sort(key=functools.cmp_to_key(cmp))
        for child_id in child_ids:
            self.sort(child_id)

    def do_get_sort_column_id(self):
        return (True, 0, Gtk.SortType.ASCENDING)

    def do_has_default_sort_func(self):
        return False

    def do_set_default_sort_func(self, sort_func, user_data):
        pass

    def do_set_sort_column_id(self, sort_column_id, order):
        self.sort_order = order

    def do_set_sort_func(self, sort_column_id, sort_func, user_data):
        self.sort_func = lambda model, a, b: sort_func(model, a, b, user_data)

    def do_sort_column_changed(self):
        print('do_sort_column_changed')

    def custom_drag_data_received(self, dst_path, src_filepath, action):
        is_move = action == Gdk.DragAction.MOVE

        *indices, i = dst_path.get_indices()
        parent_id = self.get_id_from_indices(indices)
        if not self.ids[parent_id][0].is_dir:
            parent_id = self.ids[parent_id][1]

        parent_file, _, sibling_ids = self.ids[parent_id]

        dst_filepath = os.path.join(parent_file.path, os.path.basename(src_filepath))

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

        file = File(dst_filepath)
        if is_move:
            id = self.get_id_from_filepath(src_filepath)
            child_ids = self.ids[id][2]
            self.ids[id] = (file, parent_id, child_ids)
        else:
            id = len(self.ids)
            self.ids.append((file, parent_id, None))

        sibling_ids.insert(i, id)

        iter = self.new_iter(id)
        self.row_inserted(dst_path, iter)
        self.row_has_child_toggled(dst_path, iter)

        return (True, is_move, dst_path)

    def do_drag_data_delete(self, path):
        *indices, i = path.get_indices()
        parent_id = self.get_id_from_indices(indices)
        del self.ids[parent_id][2][i]

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

#    def do_row_changed(self, path, iter):
#        pass

#    def do_row_deleted(self, path):
#        pass

#    def do_row_has_child_toggled(self, path, iter):
#        pass

#    def do_row_inserted(self, path, iter):
#        pass
