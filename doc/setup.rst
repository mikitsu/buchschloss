Setup
=====

Quick setup
-----------

.. note::
    After completing the quick setup and playing around, you should at least look
    at the various configuration options and consider reading the rest of this page
    if you still want to use BuchSchloss after having seen it.

.. code-block:: shell

    python3 -m venv env && . env/bin/activate
    git clone --depth 1 https://github.com/mik2k2/buchschloss && cd buchschloss
    python -m pip install -r requirements.txt
    export BUCHSCHLOSS_CONFIG=exampleconfig.cfg
    touch the.db
    printf 'y\n\n' | python buchschloss/models.py
    python -m buchschloss gui2

Normal setup
------------

The basics
^^^^^^^^^^

First, make sure you have at least Python 3.6.
You will probably want to use a virtual environment (``python3 -m venv MyVirtualEnv``).
At least the ``buchschloss`` directory and``requirements.txt`` are needed.
The easiest way to get them is to clone everything (I might create a tarball sometime).
Before you carry on, install requirements (``python -m pip install -r requirements.txt``)
and create a `configuration file`_ (``touch`` the database file) and
set the environment variable ``BUCHSCHLOSS_CONFIG`` to its path.

.. _configuration file: #configuration

To create the database and initialize it with basic data, run ``python buchschloss/models.py``.
If you run it from somewhere else, it won't be able to read your config file and
ask you where the database should be created and which maximum level you intend to use.

(System) Users and permissions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Unless you run this on a kiosk-style system, you'll probably not want to the the
(system) user which normal people use read/write access to the database
or to config files (which may contain secrets).
A set that takes care of this is to create a separate ``buchschloss`` user who owns all the files.
Permissions need to be at least read/write for database and logs and read for config and source.
You can then add a simple sudoers line like ``normaluser ALL=(buchschlossuser) /path/to/wrapper-script.sh``
with a simple wrapper script (since ``.`` is in ``sys.path``) like

.. code-block:: shell

    #!/bin/sh
    cd /path/to/buchschloss
    virtualenv/with/python -m buchschloss "$@"

.. note::
    I have absolutely no idea on how to achieve something similar on Windows. Sorry.

Backups and Logs
^^^^^^^^^^^^^^^^

If you don't already do whole-disk backups (or whatever backups already include the database),
you'll probably want to back up your database.
While there are lots of possibilities, you can achieve something
similar to what used to be built in with cURL (and GPG for encryption).
You can then schedule them with any scheduler you like, e.g. cron:

.. code-block::

    0 8 * * * curl ...  # every day at 8:00

or systemd timers (with a appropriate service unit):

.. code-block:: ini

    [Unit]
        Description=BuchSchloss backups at 8:00 every day
    [Timer]
        OnCalendar=*-*-* 8:0:0
    [Install]
        WantedBy=timers.target

Log rotation is specified in the configuration file.
If you want to handle it yourself, you can log to STDOUT and redirect, but
this will make terminal UIs challenging.

Configuration
-------------

The configuration file is written in `ConfigObj's`_ INI-similar syntax.
Since I like nesting, there are lots of nested sections.
For details (or the names of) all options, see the file ``buchschloss/config/configspec.cfg``,
which also contains admissible types.

The top-level section ``core`` contains settings fo the main program,
like database location, date format (why here?) or logging.
The ``scripts`` section contains startup/repeating scripts as well as configuration for Lua scripts.
The UI sections contain UI-specific data.
Options that apply to all of them may be put into the ``ui`` top-level section.
The ``lua`` section (not the subsection of ``scripts``) contains requests limiting
as well as a whitelist (the one in the example file should be OK).

The ``utils`` section contains, among others, the location of the name file.
The name file is a JSON or ConfigObj file which contains nice user-facing messages.
I'm very sorry, but the most I can do is hope the example file is vaguely complete.
You'll get a logged warning if something isn't found, though, and I absolutely welcome additions.


.. _ConfigObj's: https://pypi.org/project/configobj/
