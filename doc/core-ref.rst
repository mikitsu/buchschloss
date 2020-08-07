.. _core-ref:

``core`` module reference
=========================

.. autofunction:: buchschloss.core.login

.. autoclass:: buchschloss.core.ScriptPermissions

``ActionNamespace``
-------------------

.. autoclass:: buchschloss.core.ActionNamespace
    :members: new, view_str, view_ns, search

.. autoclass:: buchschloss.core.Book
    :members: new, edit, view_str

.. autoclass:: buchschloss.core.Person
    :members: new, edit, view_str

.. autoclass:: buchschloss.core.Group
    :members: new, edit, activate, view_str

.. autoclass:: buchschloss.core.Library
    :members: new, edit, view_str

.. autoclass:: buchschloss.core.Borrow
    :members: new, restitute, view_str

.. autoclass:: buchschloss.core.Member
    :members: new, edit, change_password, view_str

.. autoclass:: buchschloss.core.Script
    :members: new, edit, execute, view_str
