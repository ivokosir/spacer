#!/usr/bin/env python3
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from fileview import FileView


class ScrolledWindow(Gtk.ScrolledWindow):
    def do_get_preferred_width(self):
        return (200, 300)

    def do_get_preferred_height(self):
        return (250, 400)


def main():
    fileview = FileView()
    scrolledwindow = ScrolledWindow()
    scrolledwindow.add(fileview)
    window = Gtk.Window(title='Spacer')
    window.connect('delete-event', Gtk.main_quit)
    window.add(scrolledwindow)
    window.show_all()

    Gtk.main()

if __name__ == '__main__':
    main()
