# Spacer

A workspace manager. A file manager that behaves like a launcher. This means
that after launching a application through Spacer, its window will close and
app will start. The cool thing about it is that when starting Spacer again, it
will load last state of the window, so you can say that Spacer was in a way
_minimized_. What makes it a workspace manager is that state is shared only in a
single window managers workspace. This app is desingned with tiling window
managers in mind.

Code depends on [PyGObject](https://pygobject.readthedocs.io/) and
[GTK+ 3](https://www.gtk.org/)
