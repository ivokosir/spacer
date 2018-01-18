from gi.repository import GObject, Gtk, Gdk
import os, shutil
import locale, functools

class File:
    def __init__(self, id, parent_id, path, *, name=None, is_dir=None, child_ids=None):
        self.id = id
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

    def list(self, first_id):
        if not self.is_dir: return []
        try:
            with os.scandir(self.path) as entries:
                def to_file(i, entry):
                    child = self.__class__(first_id + i, self.id, entry.path,
                        name=entry.name, is_dir=entry.is_dir()
                    )
                    return child
                children = [to_file(i, entry) for i, entry in enumerate(entries)]
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
        self.ids = [File(0, None, dir, is_dir=True)]
        self.update_children(0)

    def update_children(self, id):
        file = self.ids[id]

        if not file.is_dir or file.child_ids is not None: return

        first_id = len(self.ids)
        self.ids.extend(file.list(first_id))
        last_id = len(self.ids)
        file.child_ids = list(range(first_id, last_id))
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
        file = self.ids[id]

        if os.path.commonpath([file.path, filepath]) != file.path: return None
        if file.path == filepath: return id

        if file.child_ids == None: return None
        for id in file.child_ids:
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
        file = self.ids[id]
        if not file.child_ids: return None
        if i >= 0 and i < len(file.child_ids): return file.child_ids[i]
        return None

    def do_iter_nth_child(self, iter, n):
        return self.with_iter(lambda id: self.get_id_nth_child(id, n), iter, fallback=True)

    def get_id_next(self, id):
        file = self.ids[id]
        parent = self.ids[file.parent_id]
        return self.get_id_nth_child(file.parent_id, parent.child_ids.index(id) + 1)

    def do_iter_next(self, iter):
        return self.with_iter(self.get_id_next, iter)

    def get_id_previous(self, id):
        file = self.ids[id]
        parent = self.ids[file.parent_id]
        return self.get_id_nth_child(file.parent_id, parent.child_ids.index(id) - 1)

    def do_iter_previous(self, iter):
        return self.with_iter(self.get_id_previous, iter)

    def do_iter_has_child(self, iter):
        if not self.iter_is_valid(iter): return False
        id = iter.user_data
        self.update_children(id)
        return bool(self.ids[id].child_ids)

    def do_iter_n_children(self, iter):
        if not self.iter_is_valid(iter): return 0
        id = iter.user_data
        self.update_children(id)
        return len(self.ids[id].child_ids)

    def do_iter_children(self, iter):
        return self.with_iter(lambda id: self.get_id_nth_child(id, 0), iter)

    def get_id_parent(self, id):
        return self.ids[id].parent_id

    def do_iter_parent(self, iter):
        return self.with_iter(self.get_id_parent, iter)

    def get_path_from_id(self, id):
        indices = []
        while True:
            file = self.ids[id]
            parent = self.ids[file.parent_id]
            indices.insert(0, parent.child_ids.index(id))
            id = file.parent_id
            if id == 0: break

        return Gtk.TreePath(indices)

    def do_get_path(self, iter):
        if not self.iter_is_valid(iter): return None
        return self.get_path_from_id(iter.user_data)

    def do_get_value(self, iter, column):
        if not self.iter_is_valid(iter): None
        return self.ids[iter.user_data]

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

    def custom_drag_data_received(self, dst_path, src_filepath, action):
        is_move = action == Gdk.DragAction.MOVE

        *indices, i = dst_path.get_indices()
        parent_id = self.get_id_from_indices(indices)
        parent = self.ids[parent_id]
        if not parent.is_dir:
            parent_id = parent.parent_id
            parent = self.ids[parent_id]

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
            id = self.get_id_from_filepath(src_filepath)
            file = self.ids[id]
            file.parent_id = parent_id
            file.path = dst_filepath
            file.update_name()
            file.update_is_dir()
        else:
            id = len(self.ids)
            file = File(id, parent_id, dst_filepath)
            self.ids.append(file)

        parent.child_ids.insert(i, id)

        iter = self.new_iter(id)
        self.row_inserted(dst_path, iter)
        self.row_has_child_toggled(dst_path, iter)

        return (True, is_move, dst_path)

    def do_drag_data_delete(self, path):
        *indices, i = path.get_indices()
        parent_id = self.get_id_from_indices(indices)
        del self.ids[parent_id].child_ids[i]

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

    def sort(self, id=0):
        def cmp(a_id, b_id):
            a = self.new_iter(a_id)
            b = self.new_iter(b_id)
            return self.sort_func(self, a, b)
        self.ids[id].child_ids.sort(key=functools.cmp_to_key(cmp))
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

#    def do_row_changed(self, path, iter):
#        pass

#    def do_row_deleted(self, path):
#        pass

#    def do_row_has_child_toggled(self, path, iter):
#        pass

#    def do_row_inserted(self, path, iter):
#        pass
