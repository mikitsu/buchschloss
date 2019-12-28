"""Some utilities for tkinter

Most of these are developed "on the go", so only the methods I actually
use(d) will be overridden (if applicable)
"""

import tkinter as tk
import tkinter.ttk as ttk
# __init__ imports the modules __init__ method
# get the instance with __self__
from .. import __init__
misc = __init__.__self__
del __init__

GEOMETRY_MANAGERS = ('grid', 'pack', 'place')
GEOMETRY_MANAGERS_FORGET = [(n, n + '_forget') for n in GEOMETRY_MANAGERS]


class ContainingWidget(tk.Widget):
    """Provide a widget that includes other widgets.

    Currently applies .grid(), .pack() and .place() and their respective .*_forget()
    Other calls and attribute lookups are delegated to the base widget
    """

    def __init__(self, master, *widgets,
                 direction=(tk.RIGHT, tk.BOTTOM),
                 horizontal=0,
                 vertical=0,
                 base=tk.Frame):
        """Create a multiwidget

        `widgets` are (<class>, <kwargs>) of the contined widgets
            if positional arguemnts are needed, they may be included
            under the key '*args' (clash-safe)
        `direction` is a tuple of two elements, respectively one of
            (TOP, BOTTOM) or (RIGHT, LEFT) or the inverse
            and indicates in which direction the contained widgets
            will be displayed: the first element specifies the
            first direction, when the maximum number of widgets for this
            direction is reached, the next row/column is selected by the
            second element
            e.g.: 
                (RIGHT, BOTTOM) will fill out left to right, then top to bottom
                (TOP, RIGHT) will fill out bottom to top, then left to right
            note the second element is ignored if the number of widgets for
            the first direction is unlimited
        `horizontal` and `vertical` specify the maximum number of widgets in
            their respective direction. They must allow space for all widgets
            and it is advised to set at most one of them. A value of 0 means
            an unlimited number of widgets may be positioned in that direction.
        `base` is the widget to use as container
        """
        self.base = base(master)
        self.base.container_widget = self
        self.widgets = tuple(w[0](self.base,
                                  *w[1].pop('*args', ()),
                                  **w[1]) for w in widgets)
        self.direction = direction
        self.horizontal = horizontal
        self.vertical = vertical

    def __getattr__(self, name):
        if name == 'container_widget':
            raise AttributeError('{!r} has no attribute "container_widget"'.format(self))
        return getattr(self.base, name)

    @misc.temp_function
    @staticmethod
    def _geo_wrapper(name, forget):
        def wrapper(self, *args, rcoords=None, **kwargs):
            getattr(self.base, name)(*args, **kwargs)
            return self.grid_subwidgets(rcoords)
        wrapper.__name__ = name
        wrapper.__doc__ = """.{}() the base widget and .grid() the subwidgets.

                            respect the directions given in __init__
                            pass *args and **kwargs to the base widget
                            """.format(name)

        def forgetter(self, exclude=None):
            getattr(self.base, forget)()
            for widget in self.widgets:
                if widget is not exclude:
                    widget.grid_forget()
        forgetter.__name__ = forget
        forgetter.__doc__ = ".{}() the base widget and .grid_forget() the subwidgets".format(forget)
        return wrapper, forgetter

    for name, forget in GEOMETRY_MANAGERS_FORGET:
        locals()[name], locals()[forget] = _geo_wrapper(name, forget)
    del _geo_wrapper

    def grid_subwidgets(self, rcoords):
        """.grid() the subwidgets according to `self.direction`,
                `self.horizontal` and `self.vertical`

            `rcoords` specifies a widget (identity comparison) that
                will not have .grid() called upon it. Instead, the x and y
                coordinates of its position on the grid will be returned
        """
        # x and y Start,  Increment and Return
        xr, yr = -1, -1
        if tk.RIGHT in self.direction:
            xs = 0
            xi = 1
        elif tk.LEFT in self.direction:
            if self.horizontal:
                xs = self.horizontal - 1
            else:
                xs = len(self.widgets) - 1
            xi = -1
        if tk.TOP in self.direction:
            if self.vertical:
                ys = self.vertical - 1
            else:
                ys = len(self.widgets) - 1
            yi = -1
        elif tk.BOTTOM in self.direction:
            ys = 0
            yi = 1
        try:
            xs, ys
        except NameError:
            raise ValueError('`direction` must be of the form specified in __init__')
        x, y = xs, ys
        for widget in self.widgets:
            if widget is rcoords:
                xr, yr = x, y
            else:
                widget.grid(row=y, column=x)
            if self.direction[0] in (tk.RIGHT, tk.LEFT):
                x += xi
            elif self.direction[0] in (tk.TOP, tk.BOTTOM):
                y += yi
            if y in (-1, self.vertical or None):
                y = ys
                x += xi
            if x in (-1, self.horizontal or None):
                x = xs
                y += yi
        return xr, yr


class BaseProxyWidget(tk.Widget):
    """Provide a widget that delegates some lookups to a .container
        in a way compatible with ContainingWidget

        the delegated lookups are:
        - .grid, .pack, .place and their .*_forget counterparts
        - .destroy

        the methods are wrapped in the following way:
            The first call gets sent to .container, the second one is actually
            handled by the superclass.

        i.e. The method will first be passed to self.container and executed
            on super() at the second call
    """

    def __init__(self, *args, container=None, **kwargs):
        """Create a new ProxyWidget. `container` is the container,
            other arguments are passed along"""
        self.proxy_init(container)
        super().__init__(*args, **kwargs)

    def proxy_init(self, container):
        self.__dict__.setdefault('container_list', [])
        if container is not None:
            self.container = container
            self.container_list.append(container)

    @misc.temp_function
    @staticmethod
    def _geo_wrapper(name, forget):
        def wrapper(self, *args, **kwargs):
            self.__visible = True
            container_list = reversed(self.container_list)
            x, y = getattr(next(container_list), name
                           )(*args, rcoords=self, **kwargs)
            for container in container_list:  # is an iterator
                x, y = container.grid(row=y, column=x, rcoords=self)
            if (x, y) != (-1, -1):
                super().grid(row=y, column=x)

        def forgetter(self):
            container_list = reversed(self.container_list)
            getattr(next(container_list), forget)(self)
            for container in container_list:
                container.grid_forget(self)
            super().grid_forget()
        wrapper.__name__ = name
        forgetter.__name__ = forget
        return wrapper, forgetter

    for name, forget in GEOMETRY_MANAGERS_FORGET:
        locals()[name], locals()[forget] = _geo_wrapper(name, forget)
    del _geo_wrapper


class ProxyWidget(BaseProxyWidget):
    pass


class BaseWrappedWidget(BaseProxyWidget):
    """Provide a widget that is contained inside a
        ContainingWidget along others but provides normal access"""

    def __new__(cls, master, main_widget, *auxiliary_widgets, container_kw={}):
        """Create a new WrappedWidget.

        The resulting widget is a subclass of the main widget.
        The containing widget (and, through it, the auxiliary widgets)
            is accessible through .container

        `main_widget` and each of the `auxiliary_widgets`
            are (<class>, <kwargs>)
        """
        main_cls, main_kw = main_widget
        if main_cls in cls.mro():
            # multiple wrapping
            bases = (main_cls,)
        elif cls in main_cls.mro():
            bases = (cls,)
        else:
            bases = (cls, main_cls)
        if main_cls.__new__ is object.__new__:
            def __new__(cls, *si, **nk):
                return object.__new__(cls)
        else:
            __new__ = main_cls.__new__
        main_cls = type('Wrapped' + main_cls.__name__,
                        bases,
                        {'__new__': __new__})
        container = ContainingWidget(master,
                                     (main_cls, main_kw),
                                     *auxiliary_widgets,
                                     **container_kw)
        self = container.widgets[0]
        self.proxy_init(container)
        type(self).__init__ = lambda *si, **nk: None
        return self


class WrappedWidget(BaseWrappedWidget):
    pass


class LabeledWidget(BaseWrappedWidget):
    """Convenience class for widgets to be displayed with a Label

        Provide a .labels dict to provide direct access to all labels
        New labels may be added with the add_label method
    """
    def __new__(cls, master, widget, text,
                position=tk.LEFT,
                label_id='label',
                **options):
        """Create a new WrappedWidget with a Label with the selected text.

            `position` describes the position of the Label relative to the
                wrapped widget and may be one of {tk.TOP, tk.BOTTOM, tk.LEFT, tk.RIGHT}
                if the option 'direction' is present, it overrides the automatic
                direction chosen for the position.
            `options` are passed
        """
        kw = {'direction': (position, (tk.TOP if position in (tk.LEFT, tk.RIGHT) else tk.BOTTOM))}
        kw.update(options)
        self = super().__new__(cls, master, widget, (tk.Label, {'text': text}),
                               container_kw=kw)
        labels = {label_id: self.container.widgets[1]}
        try:
            self.labels.update(labels)  # we already have a LabeledWidget somewhere
        except AttributeError:
            self.labels = labels
        return self


class ScrollableWidget:
    """Provide a scrollable widget.

        create a ContainingWidget with a canvas and a scrollbar and add the
        given widget to the canvas. Attach the appropriate methods.

        This class is to be used as a decorator/wrapper:

            >>> @ScrollableWidget(...)
            ... class MyWidget(tk.Widget):
            ...     def stuff(self, *args):
            ...         self.magic(*args)

            >>> ScrollableLabel = ScrollableWidget(...)(tk.Label)

        +-------------------------------------------------+
        | WARNING: multiple calling of a geometry manager |     
        |          *will*  *mess*  *things*  *up*         |
        +-------------------------------------------------+
    """

    def __init__(self, direction=tk.VERTICAL, width=None, height=None):
        self.direction = {tk.VERTICAL: 'y', tk.HORIZONTAL: 'x'}[direction]
        self.width = width
        self.height = height

    def __call__(self, wrapped_cls):
        class NewClass(ProxyWidget, wrapped_cls):
            def __new__(cls, master, *a, **kw):
                container = ContainingWidget(master,  # attention: order matters and is used
                                             (tk.Canvas, {'width': self.width,
                                                          'height': self.height}),
                                             (tk.Scrollbar, {})
                                             )
                canvas, scrollbar = container.widgets
                canvas.config(**{self.direction + 'scrollcommand': scrollbar.set})
                scrollbar.config(command=getattr(canvas, self.direction + 'view'))
                if wrapped_cls.__new__ is object.__new__:
                    inst = object.__new__(cls)
                else:
                    inst = wrapped_cls.__new__(cls, canvas, *a, **kw)
                inst.scroll_direction = self.direction
                inst.container = container
                inst.__init__(master, *a, container=container, **kw)
                return inst

            def __init__(self, master, *args, **kwargs):
                canvas = self.container.widgets[0]
                super().__init__(canvas, *args, **kwargs)
                canvas.create_window((0, 0), window=self)

            def set_scrollregion(self):
                canvas = self.container.widgets[0]
                sw, sh = self.winfo_width(), self.winfo_height()
                canvas.config(scrollregion=(-sw // 2, -sh // 2, sw // 2, sh // 2))

            @misc.temp_function
            @staticmethod
            def _geo_wrapper(name, forget):
                def wrapper(self, *args, **kwargs):
                    getattr(super(), name)(*args, **kwargs)
                    if isinstance(self, ContainingWidget):
                        self.grid_subwidgets(None)
                    if isinstance(self, BaseWrappedWidget):
                        x, y = self.master.container_widget.grid_subwidgets(self)
                        tk.Grid.grid(self, row=y, column=x)
                    sticky = {'y': tk.NS, 'x': tk.EW}[self.scroll_direction]
                    self.container.widgets[1].grid(row=0, column=1, sticky=sticky)
                wrapper.__name__ = name

                def wrapper_forget(self):
                    getattr(self.container, forget)()
                wrapper_forget.__name__ = forget
                return wrapper, wrapper_forget

            for name, forget in GEOMETRY_MANAGERS_FORGET:
                locals()[name], locals()[forget] = _geo_wrapper(name, forget)
            del _geo_wrapper

        NewClass.__name__ = 'Scrollable' + wrapped_cls.__name__
        NewClass.__qualname__ = '.'.join(NewClass.__qualname__.rsplit('.', 1)[:-1]
                                         + [NewClass.__name__])
        return NewClass


def get_getter(widget, getter=None):
    if getter is None:
        try:
            return widget.get
        except AttributeError:
            try:
                return widget.curselection
            except AttributeError:
                raise AttributeError('No valid method was found'
                                     ' on {!r}'.format(widget)
                                     + ' Please specify the name of the method.')
    else:
        return getattr(widget, getter)


def get_setter(widget, setter=None):
    if setter is None:
        try:
            return widget.set
        except AttributeError:
            if hasattr(widget, 'insert') and hasattr(widget, 'delete'):
                def setter(value):
                    widget.delete(0, tk.END)
                    widget.insert(0, value)
            elif (hasattr(widget, 'selection_set')
                  and hasattr(widget, 'selection_clear')):
                def setter(value):
                    widget.selection_clear(0, tk.END)
                    widget.selection_set(value)
            else:
                raise AttributeError('No valid combination of methods was found'
                                     ' on {!r}'.format(widget)
                                     + ' Please specify the name of the method.')
            return setter
    else:
        return getattr(widget, setter)


class ValidatedWidget(tk.Widget):
    """A widget which validates its input"""
    @classmethod
    def new_cls(cls, widget, validator, getter=None):
        """Create a new widget class

            create a dynamic subclass of ValidatedWidget and the passed `widget`
            `validator` should take the widget's input
                and may also be set on instances separately
            `getter` provides the name of the function to use for getting
                input from the widget. If it is None, .get() and
                .curselection() are tried
        """

        def __init__(self, *args, validator=None, **kw):
            """Initialize self.

                if `validator` is not None, it overrides the default set in the class
                all other arguments are passed to `widget.__init__`
            """
            if validator is not None:
                self.validator = validator
            widget.__init__(self, *args, **kw)
        return type('Validated{}Widget'.format(widget.__name__),
                    (cls, widget),
                    {'__new__': object.__new__,
                        '__init__': __init__,
                        'getter': get_getter(widget, getter),
                        'validator': staticmethod(validator)}
                    )

    @classmethod
    def new(cls, master, widget, widgetkw, validator, getter=None):
        """Create a new widget.

            the class is created by cls.new_cls() and then initialized
                with the given arguments
        """
        return cls.new_cls(widget, validator, getter)(master, **widgetkw)

    def validate(self):
        return self.validator(self.getter())


class RadioChoiceWidget(ContainingWidget):  # yay, no class creation magic, just __init__
    def __init__(self, master, *choices, default=0, **container_kw):
        """Create a new RadioChoiceWidget.

            `choices` are (<code>, <display>). <code> is returned by .get()
                <display> is show to the user
            if `default` is not None, the `default`th (0-index) one will be selected
            `container_kw` will be passed along and may
                e.g. be used to specify directions
        """
        self.var = tk.Variable(master)
        rbtn = []
        for code, text in choices:
            rbtn.append((tk.Radiobutton, {'value': code, 'text': text, 'variable': self.var}))
        super().__init__(master, *rbtn, **container_kw)
        if default is not None:
            self.widgets[default].select()

    def get(self):
        return self.var.get()


class VarWidget:
    """A widget with attached variable, exposed through methods on the widget"""

    @staticmethod
    def new_cls(widget, variable_type=tk.Variable, variable_name='variable'):
        """Create a new subclass and return it

            `widget` is the widget class
            `varibale_type` is the class to use for the variable
            `variable_name` ist the name of the keyword argument
                to be passed the variable
        """

        def __init__(self, master, *args, **kwargs):
            self.variable = variable_type(master)
            kwargs[variable_name] = self.variable
            super(r, self).__init__(master, *args, **kwargs)

        r = type('{}WithVar'.format(widget.__name__),
                 (widget,),
                 {'__init__': __init__,
                  'get': lambda s: s.variable.get(),
                  'set': lambda s, v: s.variable.set(v)}
                 )
        return r

    @classmethod
    def new(cls, master, widget, widget_kw, **var_kw):
        """Create a new widget instance directly

            `master` is passed
            `widget` is the widget class
            `widget_kw` is a mapping of keyword-arguments for the widgets
                the key '*args' may contain positional arguments
            `var_kw` are keyword arguments to be passed to VarWidget.new_cls
        """
        return cls.new_cls(widget, **var_kw)(
            master, *widget_kw.pop('*args', ()), **widget_kw)


class OptionChoiceWidget(ttk.OptionMenu):
    """An OptionMenu with a its own variable"""

    def __init__(self, master, values, default=0, var_type=tk.Variable, **kw):
        """Create a new OptionChoiceWidget

            `master` is passed
            `values` is a sequence of (<code>, <display>) where <code>
                is returned bu .get() and <display> is shown to the user.
                alternatively, it may be a sequence of strings in which case
                the strings are shown and .get() returns the index
            `default` is the index of the element to show by default
                or a string (like "please select") to show before any selection
            `var_type` is a callable (e.g. class) used to create the variable
            `kw` are passed
        """
        if values:
            if isinstance(values[0], str):
                values = enumerate(values)
        self.codes = {}
        vals_to_pass = []
        for c, d in values:
            self.codes[d] = c
            vals_to_pass.append(d)
        if not isinstance(default, str):
            default = vals_to_pass[default]
        self.variable = var_type(master)
        super().__init__(master, self.variable, default, *vals_to_pass, **kw)

    def get(self):
        """get the current value code"""
        return self.codes[self.variable.get()]

    def set(self, value):
        """set the current value code"""
        # this is more expensive, but I don't expect high usage
        self.variable.set({v: k for k, v in self.codes.items()}[value])


class VariableEntry(VarWidget.new_cls(tk.Entry, variable_name='textvariable'),
                    tk.Entry):  # for benefit of automatic checks
    """Entry with attached variable"""


class RememberingEntry(VariableEntry):
    """An Entry widget that remembers inputs by key pairs and allows pre-filling

        When the widget loses focus, the currently entered value is added
            to a list. The list is stored under a given key and is used
            by all RememberingEntry instances with the same key.

        Note modifications to the list of previous values will mess things
            up if changed while the widget has focus.

        `MAX_LIST_LENGTH` is the maximum length the list will have.
    """
    MAX_LIST_LENGTH = 5
    __saved_data_master = {}

    def __init__(self, master=None, cnf={}, rem_key=None, evt_next='<Next>',
                 evt_prev='<Prior>', **kw):
        """Create a new RememberingEntry

            `rem_key` is the key used to store previous entries
            `evt_next` is the event pattern for going to the next entry
            `evt_prev` is the event pattern for going to the previous entry
        """
        super().__init__(master, cnf, **kw)
        self.__saved_data = self.__saved_data_master.setdefault(rem_key, [])
        self.__index = -1
        self.bind(evt_next, self.__fill_next)
        self.bind(evt_prev, self.__fill_prev)
        self.bind('<FocusOut>', self.__focus_out)
        self.bind('<FocusIn>', self.__focus_in)

    def __fill_next(self, evt=None):
        if self.__index > 0:
            self.__index -= 1
            self.set(self.__saved_data[self.__index])

    def __fill_prev(self, evt=None):
        if self.__index < len(self.__saved_data) - 1:
            self.__index += 1
            self.set(self.__saved_data[self.__index])

    def __focus_out(self, evt=None):
        val = self.get()
        if val not in self.__saved_data:
            self.__saved_data.insert(0, val)
            if len(self.__saved_data) > self.MAX_LIST_LENGTH:
                self.__saved_data.pop()

    def __focus_in(self, evt=None):
        self.__index = -1


class AutocompleteEntry(VariableEntry):
    """entry widget that autocompletes based on the last typed characters"""
    def __init__(self, master, cnf={}, autocompletes=None,
                 autocomplete_event=None, **kwargs):
        """Create a new AutocompleteWidget

            ``autocompletes`` is a mapping from last entered characters to
                text to complete (without the leading characters)
        """
        super().__init__(master, cnf, **kwargs)
        if autocompletes is None:
            autocompletes = {}
        if autocomplete_event is None:
            autocomplete_event = '<Control-space>'
        self.autocompletes = autocompletes
        self.bind(autocomplete_event, self.autocomplete)

    def autocomplete(self, event=None):
        """attempt to autocomplete"""
        position = self.index(tk.INSERT)
        curval = self.get()[:position]
        for k, v in self.autocompletes.items():
            if k == curval[-len(k):]:
                self.insert(position, v)
                self.icursor(position + len(v))
                break
