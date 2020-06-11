
BuchSchloss API documentation
=============================

Introduction
------------

This document explains the internal structure. It aims to give an overview of
the whole program and specifically of the API required for writing a UI.

Note on books, Books and ``Book``s
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
    Like, ``config``, it is used everywhere
- ``cli`` provides a simple command-line interface to users.
    It is a very thin layer above the ``core`` API
- ``gui2`` provides the only (and ugly) graphical user interface.
    It provides more abstraction that ``cli`` and seems to be easier to use.
- ``cli2`` was ment to be a better command-line interface and has morphed
    into scriptability for BuchSchloss using Lua_. I am still developing it
    in cli2-lua_, so I won't discuss it here.
- ``misc`` is just a copy of my misc_ project. I should probably include it
    as a `git submodule`_ when I find some time.

.. _Lua: https://lua.org
.. _cli2-lua: https://github.com/mik2k2/buchschloss/tree/cli2-lua
.. _misc: https://github.com/mik2k2/misc
.. _git submodule: https://git-scm.com/book/en/v2/Git-Tools-Submodules

Generally, ``__main__.py`` loads a UI, which then imports ``core`` to actually do stuff.
Note that circular imports are used quite a lot (I have no idea on how to change
dependencies between submodules in a way that makes sense and avoids circular imports),
so the import order is important.

data overview
-------------

The following data types are present:

- Book: this represents a book. It saves bibliographic data, such as ISBN, author,
    title, a Library (see below), any number of Groups (see below) and, if applicable,
    the Person who has currently borrowed the book.
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

.. note::

    The database contains a few more tables, specifically two tables to
    provide the many-to-many relationship between (Groups and Books) and
    (People and Libraries) and a "misc" table for persistent storage of general stuff

UI interface
------------

A UI submodule (i.e. ``cli``, ``gui`` and also ``config``) contains a callable
``start`` that will be called without arguments at startup time.
When called, it should set up and run the UI's event loop
(``tk.mainloop()`` for ``gui2`` and a ``while True:`` for ``cli``).

``core`` interface
------------------

The ``core`` module contains so-called "action namespaces" for each of the data types
described in above in "data overview". These include functions for creating, reading,
searching and updating the corresponding data type. In addition to the general functions,
data types have specific functions. Every function also takes a keyword-only
``login_context`` argument that will not be listed here. See the section on permissions
and authentication/authorization for more information on it.

The data type independent interface for all ``ActionNamespace``s is:

- ``view_ns(id, /)`` for getting a namespace with all data saved about a specific instance.
- ``view_str(id, /)`` for getting a dictionary with string keys and string values
    (with few exceptions). This is useful for displaying data to an end-user
- ``view_attr(id, name, /)`` for getting the value of a single attribute.
    It is fully equivalent to ``view_ns(id).name`` but only gets the single needed
    attribute for the database, which should be more efficient (not that I ever
    experienced anything to appear slow).
- ``search(condition)`` for searching. Refer to the docstring for
    information on the condition format.

All namespaces also include a ``new`` function and all apart from ``Borrow`` also have
an ``edit`` function. Special functions are ``Group.activate``, ``Borrow.restitute``
and ``Member.change_password``.

Next to the action namespaces, the ``core`` module exposes the ``login`` function
for Members (not in the ``Member`` namespace) and ``BuchSchlossBaseError`` for
errors. Every UI should catch ``BuchSchlossBaseError``s and display them to the
user in some way.

permissions, authentication and authorization
---------------------------------------------

The ``login`` function returns a ``LoginContext`` object. This object needs to be
passed to all other exposed functions. For unauthenticated access by users, ``core``
also provides a ``guest_ls`` attribute. For internal access by a module (although that
shouldn't be required for a UI), the ``internal_lc`` attribute cn be used.

All functions check whether the passed login context is permitted to perform the
requested operation. As of now, the required permissions are hardcoded. Some functions
also require reauthentication when accessed with a login context returned by ``login``.

Currently, there are five permission levels:

- level 0 provides access to viewing and searching Books, Libraries, and Groups
- level 1 provides access to level 0 functions, viewing and searching People and Borrows,
    borrowing Books (i.e. creating Borrows) and marking Borrows as returned
- level 2 provides access to level 1 functions and creating and editing Books
- level 3 provides access to level 2 functions and creating and editing
    People, Libraries and Groups as well as activating Groups. Note that Group activation
    is only changing Book Libraries and thus could be accomplished with level 2
    permissions.
- level 4 provides access to level 3 functions and creating, viewing and modifying
    Members as well as changing other Members passwords
