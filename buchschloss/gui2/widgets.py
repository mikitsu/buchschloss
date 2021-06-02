"""specific widgets and form helpers"""
import functools
import operator
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as tk_msg
from functools import partial
from typing import Callable, Any, Optional

from ..misc import tkstuff as mtk

from .. import core
from .. import utils
from .. import config
from . import formlib
from . import common


WRAPLENGTH = config.gui2.widget_size.main.width // 2


class OptionsFromSearch(formlib.DropdownChoices):
    """A formlib.DropdownChoices tuple that gets choices from a search"""
    def __init__(self, form, master, name,
                 action_ns, allow_none=False, setter=False, condition=(), default=None):
        """Create a new instance.

        :param action_ns: is the ActionNamespace to search in
        :param allow_none: specifies whether an empty input is considered valid
        :param setter: makes this widget call ``.set_data`` on its form
          with results of ``action_ns.view_ns`` when a selection is made.
          This is especially/only useful for ID fields when editing.
        :param condition: specifies the condition with which to search
        :param default: is passed on

        The parameters ``allow_none`` and ``setter`` are mutually exclusive.
        """
        self.action_ns = action_ns
        values = [(o['id'], o.string) for o in action_ns.search(condition)]
        if allow_none:
            if setter:
                raise ValueError('``setter`` and ``allow_none`` are mutually exclusive')
            values.insert(0, (None, ''))
        if setter:
            self._update_values = self._update_values_with_set
        super().__init__(form, master, name, values, default=default)
        if setter:
            self.widget.bind('<<ComboboxSelected>>', self._do_set)

    def _update_values_with_set(self, new_value):
        r = super()._update_values(new_value)
        if len(self.widget['values']) == 1:
            self._do_set()
        return r

    def _do_set(self, event=None):  # noqa
        """Call .set() on the form with a .view_ns result"""
        result = self.action_ns.view_ns(self.get())
        self.form.set_data({k: v for k, v in result.items() if k != self.name})


class SeriesInput(formlib.FormWidget):
    """Provide Entry widgets for a series name and number"""
    def __init__(self, form, master, name):
        super().__init__(form, master, name)
        self.widget = tk.Frame(self.form.frame)
        self.series = formlib.Entry(self.form, self.widget, 'series', 'none')
        self.series_number = formlib.Entry(
            self.form, self.widget, 'series_number', 'none',
            transform=int, extra_kwargs={'width': 2},
        )
        self.series.widget.pack(side=tk.LEFT)
        self.series_number.widget.pack(side=tk.LEFT)

    def get(self):
        """Return series name"""
        return self.series.get()

    def set(self, data):
        """Set series name"""
        self.series.set(data)

    def validate(self):
        """Validate name and number individually and together"""
        val_num = self.series_number.validate()
        if val_num is not None:
            return val_num
        if self.get() is None and self.series_number.get() is not None:
            return self.form.get_name('error::series_number_without_series')

    class NumberDummy(formlib.FormWidget):
        """Dummy form widget for series numbers. Must be used with series"""
        widget = None

        def __init__(self, form, master, name, series_key='series'):
            super().__init__(form, master, name)
            for func in ('get', 'set', 'validate'):
                def redirect(*args, __func=func):
                    """Call function on series subwidget"""
                    return getattr(self.form.widget_dict[series_key], __func)(*args)
                setattr(self, func, redirect)


class ConfirmedPasswordInput(formlib.FormWidget):
    """Provide two password fields and check the entered password are the same"""
    def __init__(self, form, master, name):
        super().__init__(form, master, name)
        self.widget = tk.Frame(self.master)
        self.password_1 = tk.Entry(self.widget, show='*')
        self.password_2 = tk.Entry(self.widget, show='*')
        self.password_1.pack()
        self.password_2.pack()

    def get(self):
        """raise ValueError if the password don't match"""
        p1, p2 = self.password_1.get(), self.password_2.get()
        if p1 != p2:
            raise ValueError("the passwords don't match")
        return p1

    def set(self, data):
        """set both fields to the given value"""
        for w in (self.password_1, self.password_2):
            w.delete(0, tk.END)
            w.insert(0, data)

    def validate(self):
        """check whether the passwords match"""
        p1, p2 = self.password_1.get(), self.password_2.get()
        if p1 != p2:
            return self.form.get_name('error::password_mismatch')
        return None


class ISBNEntry(formlib.Entry):
    """Entry adaption for ISBN, with optional data filling"""
    def __init__(self, form, master, name, fill):
        """If ``fill`` is True, automatically fill data"""
        super().__init__(form, master, name, 'error', transform=utils.check_isbn)
        if fill:
            self.widget.bind('<FocusOut>', self.fill)

    def fill(self, event=None):
        """Fill data based on the ISBN"""
        with common.ignore_missing_messagebox():
            f = self.form.frame
            if str(f) not in str(f.winfo_toplevel().focus_get()):
                # going somewhere else
                return
        error = self.validate()
        if error is not None:
            tk_msg.showerror(message=error)
            return
        if not tk_msg.askyesno(utils.get_name('book::isbn'),
                               utils.get_name('interactive_question::isbn_autofill')):
            return
        try:
            data = utils.get_book_data(self.get())
        except core.BuchSchlossBaseError as e:
            tk_msg.showerror(e.title, e.message)
        else:
            self.form.set_data(data)


NonEmptyEntry = (formlib.Entry, 'error', {'max_history': 0})
NonEmptyREntry = (formlib.Entry, 'error', {})
ClassEntry = (formlib.Entry, 'error', {'regex': config.gui2.class_regex})
IntEntry = (formlib.Entry, 'error', {'transform': int})
NullIntEntry = (formlib.Entry, 'none', {'transform': int})
NullEntry = (formlib.Entry, 'none', {'max_history': 0})
NullREntry = (formlib.Entry, 'none', {})
ScriptNameEntry = (formlib.Entry, 'error', {'regex': r'^[a-zA-Z0-9 _-]*$'})
PasswordEntry = (formlib.Entry, 'keep', {'extra_kwargs': {'show': '*'}})


class Text(formlib.FormWidget):
    """Provide a tk.Text input widget"""
    widget: tk.Text

    def __init__(self, form, master, name):
        super().__init__(form, master, name)
        self.widget = tk.Text(self.master)

    def get(self):
        """return text in the widget"""
        return self.widget.get('0.0', tk.END)

    def set(self, data):
        """set the text to the given value"""
        self.widget.delete('0.0', tk.END)
        self.widget.insert('0.0', data)


class Checkbox(formlib.FormWidget):
    """A checkbox entry. Optionally with third state."""
    widget: ttk.Checkbutton

    def __init__(self, form, master, name, allow_none=False, active=True):
        super().__init__(form, master, name)
        self.var = tk.BooleanVar()
        self.widget = ttk.Checkbutton(self.master, variable=self.var)
        if allow_none:
            self.widget.state(['alternate'])
        if not active:
            self.widget.state(['disabled'])

    def get(self):
        """Return checkbutton state"""
        if 'alternate' in self.widget.state():
            return None
        return self.var.get()

    def set(self, data):
        """Set the widget to the given value. ``allow_none`` is not enforced"""
        self.var.set(data)
        if data is None:
            self.widget.state(['alternate'])


class MultiChoicePopup(formlib.MultiChoicePopup):
    """provide the ``wraplength`` argument and set ``max_height`` and ``sep``"""
    max_height = config.gui2.popup_height
    sep = config.gui2.option_sep

    def __init__(self, *args, button_options=None, **kwargs):
        kwargs['button_options'] = {**(button_options or {}), 'wraplength': WRAPLENGTH}
        super().__init__(*args, **kwargs)


class SearchMultiChoice(MultiChoicePopup):
    """MultiChoicePopup that gets choices from a search"""
    def __init__(self, form, master, name, action_ns, condition=()):
        """Use search results as values.

        :param action_ns: is the ActionNamespace to search in
        :param condition: is an optional condition to apply to the search
        """
        # This isn't a function returning a tuple that uses
        # the function providable for options to allow ViewForm
        # to treat this differently than other MultiChoicePopups
        values = [(o['id'], o.string) for o in action_ns.search(condition)]
        super().__init__(form, master, name, values)


class FlagEnumMultiChoice(MultiChoicePopup):
    """Use a FlagEnum as option source"""
    def __init__(self, form, master, name, flag_enum):
        """Get the options from ``flag_enum``"""
        self.enum = flag_enum
        options = [(e, form.get_name('' + e.name)) for e in flag_enum]
        super().__init__(form, master, name, options)

    def get(self):
        """convert individual codes to a FlagEnum instance"""
        return functools.reduce(operator.or_, super().get(), self.enum(0))

    def set(self, data):
        """convert a FlagEnum instance to individual codes"""
        super().set([v for v in self.enum if v in data])


class DisplayWidget(formlib.FormWidget):
    """Widget that only shows data"""
    sep = config.gui2.option_sep

    def __init__(self, form, master, name, display='str'):
        """Create a new DisplayWidget

        :param display: specifies the type of data.
          Currently, ``'str'`` and ``'list'`` are supported.
        """
        assert display in ('str', 'list')
        super().__init__(form, master, name)
        self.display = display
        self.widget = tk.Label(self.master, wraplength=WRAPLENGTH)

    def set(self, data):
        """Set the label text to ``data``"""
        if self.display == 'list':
            data = self.sep.join(data)
        self.widget['text'] = data

    def get(self):
        """return the currently displayed text"""
        data = self.widget['text']
        if self.display == 'list':
            data = data.split(self.sep)
        return data


class LinkWidget(formlib.FormWidget):
    """Display a button that opens an info display when clicked"""
    def __init__(self, form, master, name,
                 view_func: Callable[[tk.Widget, Any], None],
                 attr: Optional[str] = None,
                 display: Callable[[Any], str] = operator.attrgetter('string'),
                 multiple: bool = False,
                 ):
        assert callable(view_func), (form, name, view_func)
        super().__init__(form, master, name)
        self.attr = attr
        self.display = display
        self.multiple = multiple
        self.data = None
        self.view_func = view_func
        self.widget = tk.Frame(self.master)

    def set(self, data):
        """update the displayed data"""
        self.data = None
        if data is None:
            return
        if not self.multiple:
            data = [data]
        common.destroy_all_children(self.widget)
        for item in data:
            if self.attr is None:
                arg = item
            else:
                try:
                    arg = getattr(item, self.attr)
                except core.BuchSchlossPermError as e:
                    tk.Label(self.widget, text=e.message).pack()
                    continue
            tk.Button(
                self.widget,
                wraplength=WRAPLENGTH,
                command=partial(self.view_func, self.master, arg),
                text=self.display(item),
            ).pack()

    def get(self):
        """return the previously set data"""
        return self.data


class Header:
    def __init__(self, master, login_data, info_text, reset_data, exit_data):
        self.container = mtk.ContainingWidget(
            master,
            (tk.Button, login_data),
            (tk.Label, {'text': info_text}),
            (tk.Button, reset_data),
            (tk.Button, exit_data)
        )

    def set_info_text(self, new):
        self.container.widgets[1].config(text=new)

    def set_login_text(self, new):
        self.container.widgets[0].config(text=new)

    def __getattr__(self, name):
        return getattr(self.container, name)


class ActionChoiceWidget(mtk.ContainingWidget):
    def __init__(self, master, actions, **kw):
        widgets = [(tk.Button, {'text': utils.get_name('action::' + txt), 'command': cmd,
                             'padx': 50})
                   for txt, cmd in actions]
        super().__init__(master, *widgets, **kw)


@mtk.ScrollableWidget(height=config.gui2.widget_size.main.height,
                      width=config.gui2.widget_size.main.width)
class SearchResultWidget(mtk.ContainingWidget):
    def __init__(self, master, results, view_func):
        widgets = [(tk.Label, {'text': utils.get_name('{}_results').format(len(results))})]
        for r in results:
            widgets.append((tk.Button, {
                'text': r,
                'wraplength': config.gui2.widget_size.main.width,
                'command': partial(view_func, r)}))
        super().__init__(master, *widgets, direction=(tk.BOTTOM, tk.LEFT))
