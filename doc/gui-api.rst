
The gui2 package
================

The ``gui2`` sub-package provides the graphical user interface.
It is divided into the following modules:

- ``main`` provides the entry point and basic coordination.
- ``common`` provides an ActionNamespace wrapper that automatically
  adds the ``login_context`` and a context manager to ignore a strange tk error.
- ``forms`` provides form definitions. Forms are the central source of input in the GUI.
- ``formlib`` provides the API forms are built on
- ``actions`` provides the action handlers

Forms
-----

Forms are the central source of input.
A form is defined by subclassing :class:`~.Form`,
and adding the ``all_widgets`` attribute.
It can be customized (e.g. to remove/change the "Submit" button)
by overriding the following methods:

- :meth:`~.get_name`
  transforms an internal field name into the display name
- :meth:`~.get_submit_widget` returns a widget to display in toe submit area
  or ``None`` to not display anything
- :meth:`~.Form.validate` checks whether the entered data is valid and returns
  a dict mapping field names to an error message.

.. autoclass:: buchschloss.gui2.formlib.Form
    :members: get_name, get_submit_widget, validate, get_data, set_data, display_errors

The form widget classes are subclasses of :class:`~.FormWidget`.
They provide a uniform way to access data regardless of the actual widgets used.
The tk widget is set as ``.widget``.
Data getting and setting is performed via :meth:`~.get` and :meth:`~.set`.
As a single widget may provide more than one piece of information,
these methods operate with dictionaries.
For the typical use-case with each widget providing one piece of information,
:meth:`~.get_simple` and :meth:`~.set_simple` are provided.
They each return/take a single value, which is taken from/put into
a dict by the default implementation of :meth:`~.get` and :meth:`~.set`.

In the simplest case, a ``FormWidget`` corresponds to exactly one tk widget.
In that case, the ``widget`` attribute is the tk widget and :meth:`~.get_simple`/
:meth:`~.set_simple` delegate to the widget's getter and setter.

.. autoclass:: buchschloss.gui2.formlib.FormWidget
    :members: get, get_simple, set, set_simple, validate
