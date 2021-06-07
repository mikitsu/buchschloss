
The gui2 package
================

The ``gui2`` sub-package provides the graphical user interface.
It is divided into the following modules:

- ``main`` provides the entry point and basic coordination.
- ``common`` provides an ActionNamespace wrapper that automatically
  adds the ``login_context`` and a context manager to ignore a strange tk error.
- ``formlib`` provides the API forms are built on
- ``widgets`` provides specialized FormWidgets and custom tk widgets
- ``actions`` provides the action handlers and form definitions

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
Data getting and setting is performed via :meth:`~.FormWidget.get` and :meth:`~.FormWidget.set`.
A form widget may provide validation of data via its :meth:`~.FormWidget.validate` method.

.. autoclass:: buchschloss.gui2.formlib.FormWidget
    :members: get, set, validate

.. autoclass:: buchschloss.gui2.formlib.Entry
    :members: __init__, get, set, validate

.. autoclass:: buchschloss.gui2.formlib.RadioChoices
    :members: __init__, get, set

.. autoclass:: buchschloss.gui2.formlib.DropdownChoices
    :members: error_message, __init__, get, set, validate

.. autoclass:: buchschloss.gui2.formlib.MultiChoicePopup
    :members: __init__, get, set
