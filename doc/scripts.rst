Lua scripting
=============

Lua scripting can be used to enhance BuchSchloss. Scripts can be used as GUI
actions, either supplementing existing actions or doing completely new stuff.
They can be started at regular intervals, so they can perform e.g. cleanup jobs.
Since it is possible to always run them with the same level,
you can write a script to give people special privileges when some certain conditions
are met. Examples of some scripts can be found in the ``scripts/`` directory.

Scripts can use a general API for manipulating data which imitates the
Python API for user interfaces, as well as an improved abstraction for most
data types and specialized APIs for script-specific configuration data,
user interaction (both subject to availability), web requests and persistent storage
(both subject to configured `permissions <#permissions-and-setlevel>`_).
A special case of scripts are book data scripts, which are used to get data
about a book based on its ISBN, as they have a special configuration place and
(ab)use the UI API for data passing.

Direct Lua UI
-------------

The Lua environment can also be started as UI (``python -m buchschloss lua``).
In this case, only the `main APIs <#the-main-api>`_ (including abstractions) will be available.
The login context can be set at the beginning of the session. To be able to use
authentication-protected functions, a global ``getpass()`` function is also provided.
Due to technical incompetence or laziness, multi-line expressions/statements
are not supported.

Permissions and setlevel
------------------------

There are currently three types of permissions scripts can have,
stored as a :class:`core.ScriptPermissions<buchschloss.core.ScriptPermissions>` instance.

The ``AUTH_GRANTED`` permission allows a script to execute functions that otherwise
require a user to retype their password. These functions include Member and Script
editing, so in general a script shouldn't need it.

The ``REQUESTS`` permission gives the script access to the `requests API <#the-requests-api>`_
(a very thin and mostly just option-restricting wrapper around the
`Python requests library <https://requests.readthedocs.io>`_).
This permission is needed if the script has to access the internet. Notably, book data
scripts will require it.

The ``STORE`` permission allows a script to store data in the database in JSON format
and provides the `storage API <#the-storage-api>`_. This data can be viewed via ``Script.view_ns``,
so it shouldn't include particularly secret information. To configure a script,
use the appropriate section in the configuration file.

Scripts may also have a ``setlevel`` attribute which will set the script's execution
login context to that level, regardless of the invoker's level. This can be used
to grant users extra capabilities when specific conditions are met or to use
otherwise unavailable functions when the script is run as startup or periodic srcipt,
as these are started with an unprivileged invoker.

The main API
------------

The basic script API lives in the ``buchschloss`` table. It includes subtables named
as the action namespaces in the Python API, i.e. ``Book``, ``Person``, ``Library``,
``Group``, ``Borrow``, ``Member`` and ``Script``. Each of these subtables include the
corresponding functions. Arguments should be passed as a table. This allows both positional
arguments and keyword arguments to be used. The functions map one-to-one to the
Python functions (see the :ref:`reference<core-ref>`), with the exception that
the ``login_context`` argument is automatically provided.

To be easier to work with, especially from the command line, a simple abstraction
is provided for ``Book``, ``Person``, ``Library``, ``Group`` and ``Borrow``.
Values may be retrieved by indexing with the ID, so e.g. ``Book[1].title`` will provide
the title of the book with ID 1. Searching is available through calling:
``Person{}`` will provide a table of all ``Person`` objects
and ``Borrow{'is_back','eq',false}`` will provide all not-yet-returned borrows.
Creating is unchanged, but must be accessed through Lua "method syntax"[#lua-method-syntax-name]_,
i.e. ``Book:new{...}``. Editing has the minor difference of being called on a viewing
object [#views-are-lazy]_, so to edit the Book with the ID 3, you would call ``Book[3]:edit{...}``.
Special functions (i.e. only ``Group.activate``) are also called on the viewing
object: ``Group.gname:activate{...}`` (or ``Group['gname']:activate{...}``).

For convenience, the builtin function ``check_level`` is also provided.
It takes a level to compare against as first argument and an optional second argument that decides
whether to show an alert on failure (``true`` by default). It compares the *script invoker's*
level to the passed one and returns ``true`` if the invoker's level is lower.
While this may sound unintuitive, it allows you to write ``if check_level(req_level) then return end``
at the beginning of functions to check for a level. Use this if you want to restrict access to
script-specific functions. Errors with standard functions will be correctly shown to the user
-- and the script has no idea which levels are actually required.

.. [#lua-method-syntax-name] Is that the correct name?
.. [#views-are-lazy] Since these objects are lazy, not data will be retrieved if
   you only use it for editing

The requests API
----------------

If correctly configured, i.e. having the ``REQUESTS`` permission, a script will be able
to access a global variable ``requests``. Currently, the only supported method is ``get``.
It takes a URL and an optional response-type parameter. The URL will be checked against
a regular expression defined in the ``[lua]`` configuration section. GET parameters have to
be included in the URL.

The response-type parameter may be ``'auto'``, the default, in which case an appropriate type
is extracted from the ``Content-Type`` header. This is not recommended.
Other recognized values are ``'json'``, which will return a table with the response data
parsed as JSON and ``'html'`` or ``'xml'`` which will return a BeautifulSoup wrapper described below.
All unrecognized response-types will return the response data as text.

The BeautifulSoup_ wrapper provides access to ``select`` and ``select_one``,
which take a CSS selector and return all or a single found tag, respectively,
as well as ``text``, which is the tag's text content and ``attrs``, which is a
table of the tag's attributes.

.. _BeautifulSoup: https://www.crummy.com/software/BeautifulSoup/bs4/

The storage API
---------------

If configured, a script will have access to persistent storage in the database.
To use this storage, two functions are provided in the ``buchschloss`` table:

- ``get_storage`` returns the currently stored data as a table
- ``set_storage`` takes data to store

Stored data must be JSON-representable. Essentially, this means that you should stick
to string keys and not try to store weird stuff (like functions etc.).

.. note::
    - There is no locking mechanism. If the same script is ever run simultaneously
      while modifying data, bad stuff will happen.
    - Data is viewable via ``Script.view_ns`` and writable via ``Script.edit``.

The UI API
----------

If a user interface is available, scripts will be passed a ``ui`` global table with the
following functions:

- ``alert`` will show the user a message. The given message will automatically be passed
  through ``get_name`` (see below)
- ``ask`` will ask the user a yes/no question and return a boolean.
  The question is also passed through ``get_name``
- ``display`` can be used to display (more) complex data. It will try to best display
  the passed data preserving hierarchies. Use this for displaying lists or mappings.
- ``get_data`` can be used to get data of different types. It accepts a table listing
  ``{<key>, <type>}`` pairs or ``{<key>, <type>, <extra>}`` triplets.
  ``<key>`` is the field name. A version passed through ``get_name`` will be displayed.
  ``<type>`` may be one of ``'int'``, ``'bool'``, ``'str'`` or ``'choices'`` (as a string).
  An input widget matching the given type is displayed.
  For ``'choices'``, ``<extra>`` is a table of data namespaces to choose from.
  When the user has provided the requested data,
  a table mapping the names to the data, provided as the requested type, is returned.
  If the user exits the data selection, ``nil`` is returned.
- ``get_name`` provides access to the configured name file. Lookups are automatically
  prefixed with ``'script-data::<script name>::``. You may use ``{}`` formatting.
- ``get_level`` provides access to level names. It takes a level number and
  returns the corresponding name.

Configuring scripts
-------------------

Scripts can be configured in the main config file (or a file included by it) by putting data
under the section ``[scripts][lua][<script name>]``. These values will be passed
to the script in a global ``config`` table.

Setting up scripts
------------------

Once Lua scripts have been added to the database, they can be executed in different ways:

- Via automatic startup: For scripts which do something that doesn't need UI interaction,
  like registering with a server or saving statistics to storage. This can be configured
  under ``[scripts][startup]``.
- Via periodic execution: For scripts which should execute regularly,
  e.g. checking for late books. If runs are missed, exactly one execution is performed
  at startup time. In this case, UI interaction may not be possible. In other cases,
  it should.
- Via UI startup: For scripts that want to run on startup, but need to interact with users.
  They are configured in the individual UI sections, but you'll probably want to run them
  with every UI, so they can go in ``[ui][startup scripts]``.
- Via gui2 actions: For scripts that should run on explicit user choice. Typically,
  these will provide extra functions. See the ``leseclub.lua`` script for an example.

Book data scripts
-----------------

Book data scripts are a special case. They provide book information based on an ISBN.
See the ``scripts/`` directory for examples and a template. These scripts are configured
in ``[utils][book data scripts]`` in order of lowest to highest authority, i.e. later
scripts may overwrite values of earlier scripts.

The ISBN to get data for is passed via ``ui.get_data``. Regardless of passed parameters,
a table with the ISBN as number under the ``'isbn'`` key is returned. To return data,
call ``ui.display`` with a table of data. You may call ``ui.display`` multiple times.
The table should map any keys ``Book.new`` accepts to values.

.. note::
    The fact the ``ui`` API is used to move data around means you won't be able
    to interact with the user, because of technical reasons
    not even through ``ask`` and ``alert``.
