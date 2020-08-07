# BuchSchloss

Welcome!

This is a management program written for my school library.

### Usage

If you *really* want to use this, follow the instructions below:

1. Make sure you have Python >= 3.6
1. (optional) create a new virtual environment and activate it. If you don't, you may have to adjust the following commands
1. download and unpack the latest code (``master`` branch if you're feeling adventurous, some (hopefully) stable release if not)
1. write a bare-bones config file (you can use ``exampleconfig.cfg`` as an example)
1. ``$ python buchschloss/models.py`` to create the database (SQLite)
1. ``$ export BUCHSCHLOSS_CONFIG=/path/to/your/config.file`` or start the following commands with ``$ env BUCHSCHLOSS_CONFIG=/path/to/your/config.file ``
1. test your config file with ``$ python -m buchschloss config``
    1. TODO: insert probable errors and how to get rid of them here
1. when it's valid, start the simple command-line interface with ``$ python -m buchschloss cli``
1. Type ``login SAdmin`` at the ``----- >`` prompt
1. Type ``Pa$$w0rd`` when asked for a password
1. the prompt should change to ``Member[SAdmin](level_4) > ``
1. you can now do everything! Type ``help commands`` to see the available commands

TODO: write something that explains how to actually do stuff

### Overview

The actual files are in the ``buchschloss`` directory. Inside, there is:

- ``core.py`` the main application providing the interface used by the user interfaces
- ``models.py`` definition of the database models; can be run as a script to initialize the database
- ``utils.py`` stuff that doesn't belong anywhere else
- ``cli.py`` a simple command-line interface providing a thin wrapper around the core API
- ``gui2/`` a package of the current GUI, written with ``tkinter``
    - ``widgets.py`` special widgets used
    - ``validation.py`` entry validation logic
    - ``actions.py`` the code that actually calls the actions exposed by ``core``
    - ``main.py`` the graphical application
    - ``__init__.py`` glue
- ``lua/`` subpackage for lua scripting support
    - ``__init__.py`` main execution, sandboxing and lua-based cli interface
    - ``objects.py`` object wrappers exported to lua
    - ``builtins.lua`` abstraction of core APIs

### Documentation

I am more-or-less in the process of documenting the internal parts (see ``doc/``).


### Tests

As of now, only some basic functions are tested, 
notably excluding (in the sense of not being tested) the GUI.
I will try to add relevant tests whenever I change something.