"""Form and FormWidget classes"""
import tkinter as tk
import tkinter.messagebox as tk_msg


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
