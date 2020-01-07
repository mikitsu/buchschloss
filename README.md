# BuchSchloss

Welcome!

This is a management program written for my school library.

### Usage

If you *really* want to use this, follow the instructions below:

1. Make sure you have Python >= 3.6
2. (optional) create a new virtual environment and activate it. If you don't, you may have to adjust the following commands
3. download and unpack the latest code (``master`` branch if you're feeling adventurous, some (hopefully) stable release if not)
4. write a bare-bones config file (you can use ``exampleconfig.cfg`` as an example)
5. ``$ export BUCHSCHLOSS_CONFIG=/path/to/your/config.file``
6. test your config file with ``$ python -m buchschloss config``
    1. TODO: insert probable errors and how to get rid of them here
7. when it's valid, start the simple command-line interface with ``$ python -m buchschloss cli``
8. Type ``login SAdmin`` at the ``----- >`` prompt
9. Type ``Pa$$w0rd`` when asked for a password
10. the prompt should change to ``Member[SAdmin](level_4) > ``
11. you can now do everything! Type ``help commands`` to see the available commands

TODO: write something that explains how to actually do stuff
