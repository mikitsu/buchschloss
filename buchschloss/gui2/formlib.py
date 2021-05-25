"""Generic form classes

:class:`~.Form` and :class:`~.FormWidget` provide the basics
while the other classes implement form widgets in a generic, but useful, way
"""
import re
import tkinter as tk
from tkinter import ttk
import tkinter.messagebox as tk_msg

__all__ = ['Form', 'FormWidget', 'Entry', 'RadioChoices', 'DropdownChoices']


class Form:
    """Display a form.

    Forms are specified by subclassing and setting the ``all_widgets`` attribute.
    It is merged with the superclasses' attributes.
    To remove a specification by a superclass, explicitly set it to ``None``.
    The ``all_widgets`` attribute is a dict of the form::

        {
            field: {
                tag: widget_spec,
                tag_2: widget_spec_2,
                ...,
                None: default_widget_spec,
            },
            field_2: tag_dict_2,  # may also be a widget spec
            ...
            field_n: tag_dict_n,  # may also be a widget spec
        }

    Where ``field`` is a field name (passed to widgets and used as default result key),
    ``tag`` is a form tag (see below) with ``None`` indicating the default
    and a ``widget_spec`` specifies a ``FormWidget`` either as a class, in which
    case the instance will be created without arguments or as a ``(class, *args, kwargs)``
    tuple, in which case the instance will be created with ``*args`` and  ``**kwargs``.
    It may also be ``None``, in which case no widget is created.

    .. note::
        In all cases, relevant tk widget information (i.e.: master widget) is passed.
        The optional arguments are for further specification.

        Information for widget keyword arguments is not merged when subclassing.

    When instantiating a form, a tag value is given.
    This tag is available as ``.tag`` (for use in e.g. validation functions)
    and is used to choose the appropriate widget for a field.
    """
    all_widgets = {}
    error_text_config = {'fg': 'red'}

    def __init_subclass__(cls):
        """Merge the new and old ``all_widgets`` handling convenience shorthands"""
        # first, handle convenience shorthands
        for field, tag_spec in cls.all_widgets.items():
            if not isinstance(tag_spec, dict):
                tag_spec = {None: tag_spec}
            cls.all_widgets[field] = {
                tag: ws if isinstance(ws, (tuple, type(None))) else (ws, {})
                for tag, ws in tag_spec.items()
            }
            cls.all_widgets[field].setdefault(None, None)
        # second, merge
        all_widgets = {}
        for superclass in reversed(cls.__mro__):  # is there a way to get direct parents?
            if not issubclass(superclass, Form):
                continue
            for field, tag_spec in superclass.all_widgets.items():
                all_widgets.setdefault(field, {}).update(tag_spec)
        cls.all_widgets = all_widgets

    def __init__(self, frame, tag, submit_callback):
        self.frame = frame
        self.tag = tag
        self.submit_callback = submit_callback
        self.widget_dict = {
            name: widget[0](self, self.frame, name, *widget[1:-1], **widget[-1])
            for name, tag_alternatives in self.all_widgets.items()
            for widget in [tag_alternatives.get(tag, tag_alternatives[None])]
            if widget is not None
        }
        i = -1
        for i, (name, widget) in enumerate(self.widget_dict.items()):
            tk.Label(self.frame, text=self.get_name(name)).grid(row=i, column=0)
            widget.widget.grid(row=i, column=1)
        submit = self.get_submit_widget()
        if submit is not None:
            submit.grid(row=i+1, column=0, columnspan=3)
        self._error_display_widgets = ()

    def handle_submit(self):
        """Check and possibly display errors or call callback"""
        for error_display in self._error_display_widgets:
            error_display.grid_forget()
        errors = self.validate()
        if errors:
            self.display_errors(errors)
        else:
            self.submit_callback(self.get_data())

    def get_data(self):
        """Get entered data from widgets"""
        data = {}
        for widget in self.widget_dict.values():
            data.update(widget.get())
        return data

    def set_data(self, data):
        """Set the given data"""
        for widget in self.widget_dict.values():
            widget.set(data)

    def display_errors(self, errors):
        """Display the encountered errors as a popup and next to the fields"""
        # consider splitting popup and text into separate functions
        self._error_display_widgets = []
        complete_message = []
        for field, message in errors.items():
            complete_message.append(f'{self.get_name(field)}: {message}')
            w = tk.Label(self.frame, text=message, **self.error_text_config)
            w.grid(row=self.widget_dict[field].widget.grid_info()['row'], column=3)
            self._error_display_widgets.append(w)
        tk_msg.showerror(self.get_name('error'), complete_message)

    def validate(self):
        """Check for and return errors. Default: rely on widget validation"""
        errors = {}
        for widget in self.widget_dict.values():
            errors.update(widget.validate())
        return errors

    @staticmethod
    def get_name(name):
        """Make an internal field name human-readable. Default: return unchanged"""
        return name

    def get_submit_widget(self):
        """Return a 'submit' button"""
        return tk.Button(
            self.frame,
            text=self.get_name('submit'),
            command=self.handle_submit,
        )


class FormWidget:
    """Class to be used with Form

    A FormWidget wraps a tk input widget and provides a uniform interface to Form.
    This is the base class. Use the specific subclasses.
    """
    form: Form
    master: tk.Widget
    name: str
    widget: tk.Widget

    def __init__(self, form, master, name):
        self.form = form
        self.master = master
        self.name = name

    def get(self):
        """Return all values this widget provides in a dict.

        This default implementation returns ``{self.name: self.get_simple()}``
        """
        return {self.name: self.get_simple()}

    def get_simple(self):
        """Return a single value this widget provides"""
        raise NotImplementedError("implement .get_simple() if you don't override .get()")
    
    def set(self, data):
        """Set this widgets value to those provided (ignore unknown keys)
        
        This default implementation calls ``self.set_simple(data[self.name])``
        if ``self.name in data``
        """
        if self.name in data:
            self.set_simple(data[self.name])
    
    def set_simple(self, data):
        """Set a single value this widget provides"""
        raise NotImplementedError(
            "implement .set_simple() if you don't override .set()")
    
    def validate(self):
        """Validate this widget's data and return None or a dict of error messages
        
        This default implementation returns ``{self.name: self.validate_simple()}``
        if ``self.validate_simple() is not None`` and ``{}`` otherwise
        calling ``.validate_simple()`` only once.
        """
        v = self.validate_simple()
        return {} if v is None else {self.name: v}

    def validate_simple(self):
        """Validate this widgets data and return None or an error message"""
        raise NotImplementedError(
            "implement .validate_simple() if you don't override .validate()")


class Entry(FormWidget):
    """Wrap tk.Entry with options

    - cycling through previous values
    - options for handling of empty inputs
    - validation via regex
    """
    widget: tk.Entry
    _history_dict = {}

    def __init__(self, form, master, name,
                 on_empty,
                 regex=None,
                 transform=None,
                 max_history=1_000,
                 autocomplete=None,
                 extra_kwargs=None,
                 ):
        """Wrapped tk.Entry with history, autocomplete and regex validation

        :param form: is the form this widget is used in (passed up)
        :param name: is the name of this widget in the form (passed up)
        :param on_empty: is a string specifying what to do when a value is empty:
          ``'error'`` will treat it as an error, ``'none'`` will transform it
          into ``None`` and ``'keep'`` will leave it unchanged, i.e. ``''``
        :param regex: is an optional regular expression to apply to input
        :param transform: is an optional function that will be applied to values.
          A ValueError from this function will be treated as validation failure.
        :param autocomplete: may map characters to completion text,
          e.g. {'so': 'me text'}
        :param max_history: specifies how many previous inputs to store.
          Set to 0 to disable history.
        :param extra_kwargs: arguments to pass to the tk Entry widget
        """
        super().__init__(form, master, name)
        if on_empty not in ('error', 'none', 'keep'):
            raise ValueError("on_empty must be 'error', 'none' or 'keep'")
        self.on_empty = on_empty
        self.regex = re.compile(regex) if isinstance(regex, str) else regex
        self.transform = lambda v: v if transform is None else transform
        self.autocomplete = autocomplete or {}
        self.widget = tk.Entry(self.master, **(extra_kwargs or {}))
        if max_history:
            self.history = self._history_dict.setdefault((type(self.form), self.name), [])
            self.max_history = max_history
            self.history_index = -1
            self.widget.bind('<FocusOut>', self._update_history)
            self.widget.bind('<Next>', lambda e: self._history_move(1))
            self.widget.bind('<Prior>', lambda e: self._history_move(-1))
        if autocomplete:
            self.widget.bind('<Control-space>', self._do_autocomplete)

    def get_simple(self):
        """delegate to self.widget.get() and handle on_empty=='none'"""
        v = self.widget.get()
        return None if not v and self.on_empty == 'none' else self.transform(v)

    def set_simple(self, data):
        """delete current and insert new"""
        self.widget.delete(0, tk.END)
        self.widget.insert(0, data)

    def validate_simple(self):
        """handle on_empty='error' and validate_re"""
        v = self.get_simple()
        if self.on_empty == 'error' and not v:
            return self.form.get_name(f'{self.name}::error::empty')
        if self.regex is not None and self.regex.search(v) is None:
            return self.form.get_name(f'{self.name}::error::regex')
        try:
            self.get_simple()
        except ValueError:
            return self.form.get_name(f'{self.name}::error::transform')
        return None

    def _do_autocomplete(self, event=None):  # noqa -- tkinter callback
        """Perform auto-completion based on self.autocomplete"""
        position = self.widget.index(tk.INSERT)
        current = self.widget.get()[:position]
        for k, v in self.autocomplete.items():
            if current.endswith(k):
                self.widget.insert(position, v)
                self.widget.icursor(position + len(v))
                break

    def _update_history(self, event=None):  # noqa -- tkinter callback
        """Add content to history and reset index"""
        self.history_index = -1
        v = self.widget.get()
        if self.history and v == self.history[0]:
            return
        else:
            self.history.insert(0, v)
            if len(self.history) > self.max_history:
                self.history = self.history[:-1]

    def _history_move(self, direction):
        """move one item up (direction == 1) or down (direction == -1)"""
        if 0 <= self.history_index + direction < len(self.history):
            self.history_index += direction
            self.set_simple(self.history[self.history_index])


class RadioChoices(FormWidget):
    """Select one radio button"""
    def __init__(self, form, master, name, choices, default=0, pack_side=tk.LEFT):
        """Create the widget

        :param choices: is an iterable of ``code, display`` pairs. ``code`` is
          the value returned by ``.get()`` and ``display`` is shown to the user.
        :param default: is the index of the choice to pre-select or None to not
          select any choice
        :param pack_side: is used as argument when ``.pack()``ing the radio buttons
        """
        super().__init__(form, master, name)
        self.widget = tk.Frame(self.master)
        self.var = tk.Variable()
        self.radios = [
            tk.Radiobutton(self.widget, value=code, text=text, variable=self.var)
            for code, text in choices
        ]
        for i, radio in enumerate(self.radios):  # this elegantly avoids IndexError
            if i == default:
                radio.select()
            radio.pack(side=pack_side)

    def get_simple(self):
        """return the code for the currently selected value"""
        return self.var.get()

    def set_simple(self, data):
        """select the radio button with the given code"""
        self.var.set(data)

    def validate_simple(self):
        """always valid"""
        return None


class DropdownChoices(FormWidget):
    """Select an element from a drop-down menu (Combobox)"""
    widget: ttk.Combobox
    error_message = 'selection ambiguous'

    def __init__(self, form, master, name, choices, default=0, search=True, new=False):
        """Create the widget

        :param choices: is a sequence of ``code, display`` pairs or single strings.
          In the latter case, each element will be used for both. ``code`` is the
          value returned by ``.get()`` and ``display`` is shown to the user.
          For dynamic uses, ``choices`` may also be a zero-argument callable providing
          a sequence as described above.
        :param default: is the index of the choice to pre-select or None to not
          select any choice
        :param search: specifies whether to allow searching the values by typing into
          the Combobox. This will allow typing text with strict validation.
          Until a value can be uniquely identified, None is returned in ``.get()``
          and validation fails with the message in ``self.error_message``, unless
          ``new`` is true
        :param new: specifies whether to allow user-created inputs that are not
          in the given choices. If true, allow typing any text and return the typed text
          if it doesn't match a value entry.
        """
        self.allow_new = new
        super().__init__(form, master, name)
        if callable(choices):
            choices = choices()
        if choices and not isinstance(choices[0], str):  # avoid zip(*())
            self.codes, self.all_values = zip(*choices)
        else:
            self.codes = self.all_values = tuple(choices)
        kwargs = {}
        if search:
            kwargs['validate'] = 'all'
            kwargs['validatecommand'] = (self.master.register(self._update_values), '%P')
        elif not new:
            kwargs['state'] = 'readonly'
        self.widget = ttk.Combobox(self.master, values=self.all_values, **kwargs)
        if default is not None:
            self.widget.current(default)

    def get_simple(self):
        """return the code for the currently selected value"""
        value = self.widget.get()
        try:
            return self.codes[self.all_values.index(value)]
        except ValueError:
            if self.allow_new:
                return value
            else:
                return None

    def set_simple(self, data):
        """select the value with the given code"""
        self.widget['values'] = self.all_values
        self.widget.current(self.codes.index(data))
        if '_update_values' in self.widget['validatecommand']:
            self._update_values(self.get())

    def validate_simple(self):
        """check if the choice is unambiguous if not self.allow_new"""
        if self.allow_new or self.widget.current() != -1:
            return None
        else:
            return self.error_message

    def _update_values(self, new_value):
        """update displayed values based on entered text

        If not self.allow_new, block text that doesn't match anything
        and auto-fill completely when the choice is unambiguous
        """
        possibilities = [v for v in self.all_values if new_value in v]
        if not self.allow_new:
            if not possibilities:
                return False
            elif len(possibilities) == 1:
                self.widget.set(possibilities[0])
        self.widget['values'] = possibilities
        return True
