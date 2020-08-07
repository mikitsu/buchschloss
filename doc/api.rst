
BuchSchloss API documentation
=============================

Introduction
------------

This document explains the internal structure. It aims to give an overview of
the whole program and specifically of the API required for writing a UI.

Note on books, Books and ``Book`` s
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When capitalized, Book, Person, Library etc. will refer to the program's representation
of their real-world counterparts (written in lower case). When referring to variables,
they will be written in code style, like ``Book`` or ``Person``.

Overview
--------

BuchSchloss includes the following submodules:

- ``core`` provides the general API for the user interfaces
- ``models`` provides (more or less) direct access to the database.
  It is only used by ``core``.
- ``config`` reads and (partially) validates user configuration files.
  It is used throughout BuchSchloss. It can be specified as UI
  to check configuration and optionally display it.
- ``utils`` is a place to put stuff that belongs nowhere else.
  Like ``config``, it is used everywhere
- ``cli`` provides a simple command-line interface to users.
  It is a very thin layer above the ``core`` API
- ``gui2`` provides the only (and ugly) graphical user interface.
  It provides more abstraction that ``cli`` and seems to be easier to use.
- ``lua`` was meant to be a better command-line interface and has morphed
  into scriptability for BuchSchloss using Lua_.
- ``misc`` is just a copy of my old misc_ project. I should probably include it
  as a git submodule when I find some time.

.. _Lua: https://www.lua.org
.. _misc: https://github.com/mik2k2/misc-utils

Generally, ``__main__.py`` loads a UI, which then imports ``core`` to actually do stuff.
Note that circular imports are used quite a lot (I have no idea on how to change
dependencies between submodules in a way that makes sense and avoids circular imports),
so the import order is important.

data overview
-------------

The following data types are present:

- Book: this represents a book. It saves bibliographic data, such as ISBN, author,
  title, a Library (see below), any number of Groups (see below) and, if applicable,
  the Person who has currently borrowed the book [#borrow-in-book]_.
- Person: this represents someone who can borrow some books. Next to personal details,
  available Libraries and information on borrowing restrictions is stored.
- Library: Libraries contain a group of books whose borrowing conditions are the same.
  Each Library also stores a "pay_required" (old name, should change to "restricted")
  value.
- Group: Groups are used to simplify Library-changing of large numbers of Books.
  A Group can be activated, automatically transferring all Books to a Library.
- Borrow: not as evident on the UI level as the other data pieces.
  Saves a borrowing action: Book and Person, the return date and whether
  the Book has been returned
- Member: this saves data on administratively active people, who are allowed to
  borrow books to People, create new Books and, in general, change stuff
- Script: a Lua script with special permissions and its code

.. [#borrow-in-book] The current Borrow instance is actually a property
    which executes a query, but you can pretend it is stored.

.. note::

    The database contains a few more tables, specifically two tables to
    provide the many-to-many relationship between (Groups and Books) and
    (People and Libraries) and a "misc" table for persistent storage of general stuff

UI interface
------------

A UI submodule (i.e. ``cli``, ``gui2``, ``lua`` and also ``config``) contains a callable
``start`` that will be called without arguments at startup time.
When called, it should set up and run the UI's event loop
(``tk.mainloop()`` for ``gui2`` and a ``while True:`` for ``cli``  and ``lua``).

``core`` interface
------------------

The ``core`` module contains so-called "action namespaces" for each of the data types
described in above in "data overview". These include functions for creating, reading,
searching and updating the corresponding data type. In addition to the general functions,
data types have specific functions. Every function also takes a keyword-only
``login_context`` argument that will not be listed here. See the section on permissions
and authentication/authorization for more information on it.

The data type independent interface for all ``ActionNamespace`` s is:

- ``view_ns(id, /)`` for getting a namespace with all data saved about a specific instance.
- ``view_str(id, /)`` for getting a dictionary with string keys and string values
  (with few exceptions). This is useful for displaying data to an end-user
- ``view_repr(id, /)`` for getting a string representation. This is fully equivalent to
  ``str(view_ns(<id>))``, but just gets the required fileds from the database
- ``search(condition)`` for searching. Refer to the docstring for
  information on the condition format.

All namespaces also include a ``new`` function and all apart from ``Borrow`` also have
an ``edit`` function. Special functions are ``Group.activate``, ``Borrow.restitute``,
``Member.change_password`` and ``Script.execute``.

Next to the action namespaces, the ``core`` module exposes the ``login`` function
for Members (not in the ``Member`` namespace) and ``BuchSchlossBaseError`` for
errors. Every UI should catch ``BuchSchlossBaseError`` s and display them to the
user in some way.

See the :ref:`reference for the core module<core-ref>` for details.

permissions, authentication and authorization
---------------------------------------------

The ``login`` function returns a ``LoginContext`` object. This object needs to be
passed to all other exposed functions. For unauthenticated access by users, ``core``
also provides a ``guest_lc`` attribute. For internal access by a module,
there are two different attributes: ``internal_priv_lc`` and ``internal_unpriv_lc``.
The privileged variant has full access to everything and shouldn't be required for a UI,
while the unprivileged variant should be used for running startup scripts and is,
apart from the name, fully equivalent to ``guest_lc`` (you should still use the proper one).

All functions check whether the passed login context is permitted to perform the
requested operation. Some functions also require reauthentication in form of
a ``current_password`` argument when accessed with a login context returned by ``login``.
These functions are hardcoded and for convenience their ``__qualname__`` s are also
available at ``core.auth_required.functions``.

Permission levels can be configured at will, and while the maximum level is currently
capped at 10, this can be easily changed.
