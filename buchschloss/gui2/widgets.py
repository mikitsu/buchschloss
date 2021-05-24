"""specific widgets and FormWidget classes"""
import enum
import functools
import operator
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import Label, Button
from functools import partial
from collections import abc
import typing as T

from ..misc import tkstuff as mtk
from ..misc.tkstuff import dialogs as mtkd

from . import validation
from . import common
from .. import utils
from .. import config
from .. import core
from . import formlib


class SeriesInput(formlib.FormWidget):
    """Provide Entry widgets for a series name and number"""
    def __init__(self, form, master, name):
        super().__init__(form, master, name)
        self.widget = tk.Frame(self.form.frame)
        self.subwidgets = {
            'series': formlib.Entry(self.form, self.widget, 'series', 'none'),
            'series_number': formlib.Entry(self.form, self.widget, 'series_number', 'none',
                                   transform=int, extra_kwargs={'width': 2}),
        }
        for w in self.subwidgets.values():
            w.widget.pack(side=tk.LEFT)

    def get(self):
        """Return series name and number, under 'series' and 'series_number'"""
        return {k: v for w in self.subwidgets.values() for k, v in w.get()}

    def set(self, data):
        """Set series name and number"""
        for w in self.subwidgets.values():
            w.set(data)

    def validate(self):
        """Validate name and number individually and together"""
        r = {k: v for w in self.subwidgets.values() for k, v in w.validate()}
        if all((not r,
                self.subwidgets['series_number'].get_simple() is not None,
                self.subwidgets['series'].get_simple() is None)):
            r['series'] = self.form.get_name('error::series_number_without_series')
        return r


class ConfirmedPasswordInput(formlib.FormWidget):
    """Provide two password fields and check the entered password are the same"""
    def __init__(self, form, master, name):
        super().__init__(form, master, name)
        self.widget = tk.Frame(self.master)
        self.password_1 = tk.Entry(self.widget, show='*')
        self.password_2 = tk.Entry(self.widget, show='*')
        self.password_1.pack()
        self.password_2.pack()

    def get_simple(self):
        """raise ValueError if the password don't match"""
        p1, p2 = self.password_1.get(), self.password_2.get()
        if p1 != p2:
            raise ValueError("the passwords don't match")
        return p1

    def set_simple(self, data):
        """set both fields to the given value"""
        for w in (self.password_1, self.password_2):
            w.delete(0, tk.END)
            w.insert(0, data)

    def validate_simple(self):
        """check whether the passwords match"""
        p1, p2 = self.password_1.get(), self.password_2.get()
        if p1 != p2:
            return self.form.get_name('error::password_mismatch')
        return None


ISBNEntry = (formlib.Entry, 'error', {'transform': validation.ISBN_validator})
NonEmptyEntry = (formlib.Entry, 'error', {'max_history': 0})
NonEmptyREntry = (formlib.Entry, 'error', {})
ClassEntry = (formlib.Entry, 'error', {'regex': config.gui2.class_regex})
IntEntry = (formlib.Entry, 'error', {'transform': int})
NullIntEntry = (formlib.Entry, 'none', {'transform': int})
NullEntry = (formlib.Entry, 'none', {'max_history': 0})
NullREntry = (formlib.Entry, 'none', {})
ScriptNameEntry = (formlib.Entry, 'error', {'regex': r'^[a-zA-Z0-9 _-]*$'})
PasswordEntry = (formlib.Entry, 'ignore', {'extra_kwargs': {'show': '*'}})


class ActionChoiceWidget(mtk.ContainingWidget):
    def __init__(self, master, actions, **kw):
        widgets = [(Button, {'text': utils.get_name('action::' + txt), 'command': cmd,
                             'padx': 50})
                   for txt, cmd in actions]
        super().__init__(master, *widgets, **kw)


class OptionsFromSearch(formlib.FormWidget):
    """Choose from the result of a search"""
    widget: ttk.Combobox

    def __init__(self, form, master, name, action_ns, allow_none=False, condition=()):
        super().__init__(form, master, name)
        self.all_values: T.Dict[str, T.Optional[str]] = {'': None} if allow_none else {}
        self.id_map: T.Dict[str, T.Any] = {'': None} if allow_none else {}
        for obj in common.NSWithLogin(action_ns).search(condition):
            self.all_values[str(obj)] = str(obj.id)
            self.id_map[str(obj.id)] = obj.id
        self.widget = ttk.Combobox(
            master,
            values=tuple(self.all_values.keys()),
            validate='all',
            validatecommand=(self.master.register(self.update_values), '%P'),
        )

    def set_simple(self, value):
        """handle DataNS"""
        if isinstance(value, core.DataNamespace):
            value = value.id
        self.widget.set(value)

    def get_simple(self):
        """Return ID with correct type. May raise KeyError."""
        return self.id_map[self.widget.get()]  # TODO: this was .get() -- still important?

    def validate_simple(self):
        """Override to supply the signature expected in forms: (valid, value)"""
        try:
            self.get_simple()
        except KeyError:
            return self.form.get_name(f'{self.name}::error::invalid_object_selected')
        else:
            return None

    def update_values(self, new_value):
        """update displayed values based on entered text

        Only display options of which the entered text is a substring.
        Auto-fill the ID if there is only one match.
        """
        possibilities = [v for v in self.all_values if new_value in v]
        if len(possibilities) == 0:
            return False  # don't allow edit
        elif len(possibilities) == 1:
            self.set_simple(self.all_values[possibilities[0]])
        self.widget['values'] = possibilities
        return True


class Text(formlib.FormWidget):
    """Provide a tk.Text input widget"""
    widget: tk.Text

    def __init__(self, form, master, name):
        super().__init__(form, master, name)
        self.widget = tk.Text(self.master)

    def get_simple(self):
        """return text in the widget"""
        return self.widget.get('0.0', tk.END)

    def set_simple(self, data):
        """set the text to the given value"""
        self.widget.delete('0.0', tk.END)
        self.widget.insert('0.0', data)


@mtk.ScrollableWidget(height=config.gui2.widget_size.main.height,
                      width=config.gui2.widget_size.main.width)
class InfoWidget(mtk.ContainingWidget):
    def __init__(self, master, data):
        wraplength = config.gui2.widget_size.main.width / 2
        widgets = []
        for k, v in data.items():
            widgets.append((Label, {'text': k}))
            if v is None:
                widgets.append((Label, {}))
            elif isinstance(v, str):
                widgets.append((Label, {'text': v, 'wraplength': wraplength}))
            elif isinstance(v, abc.Sequence):
                if len(v) and isinstance(v[0], type) and issubclass(v[0], tk.Widget):
                    v = [v]
                for w in v:
                    if 'text' in w[1]:
                        w[1].setdefault('wraplength', wraplength)
                    widgets.append(w)
                if not len(v) % 2:
                    widgets.append((Label, {}))  # padding to keep `k` on left
            else:
                raise ValueError('`{}` could not be handled'.format(v))
        super().__init__(master, *widgets, horizontal=2)


class Checkbox(formlib.FormWidget):
    """A checkbox entry. Optionally with third state."""
    widget: ttk.Checkbutton

    def __init__(self, form, master, name, allow_none=False):
        super().__init__(form, master, name)
        self.var = tk.BooleanVar()
        self.widget = ttk.Checkbutton(self.master, variable=self.var)
        if allow_none:
            self.widget.state(['alternate'])

    def get_simple(self):
        """Return checkbutton state"""
        if self.widget.state() == ('!alternate',):
            return None
        assert self.widget.state() == ()
        return self.var.get()

    def set_simple(self, data):
        """Set the widget to the given value. ``allow_none`` is not enforced"""
        self.var.set(data)
        if data is None:
            self.widget.state(['alternate'])


class ActivatingListbox(tk.Listbox):
    """a Listbox that allows initial items, possibly already activated
        additional options: exportselection=False, selectmode=tk.MULTIPLE"""

    def __init__(self, master, cfg={}, values=(), activate=(), **kwargs):
        super().__init__(master, cfg, exportselection=False,
                         selectmode=tk.MULTIPLE, **kwargs)
        self.insert(0, *values)
        for i in activate:
            self.select_set(i)


def get_scrolled_listbox(master, listbox=tk.Listbox, **listbox_kwargs):
    """a Listbox that includes its Scrollbar"""
    inst: T.Union[listbox, mtk.WrappedWidget] = \
        mtk.WrappedWidget(master, (listbox, listbox_kwargs), (tk.Scrollbar, {}))
    inst.scrollbar = inst.container.widgets[1]
    inst['yscrollcommand'] = inst.scrollbar.set
    inst.scrollbar['command'] = inst.yview
    return inst


class ScrolledListbox(tk.Listbox):
    """wrapper around get_scrolled_listbox for functions needing a class"""
    def __new__(cls, *args, **kwargs):
        return get_scrolled_listbox(*args, **kwargs)


class MultiChoicePopup(tk.Button):
    """Button that displays a multi-choice listbox popup dialog on click"""
    def __init__(self, master, cnf={}, options=(), sep=';', **kwargs):
        """create a new MultiChoicePopup

            ``root`` is the master of the generated popup
            ``options`` is a sequence of (<code>, <display>) tuples
                <display> will be shown to the user, while <code>
                will be used when .get is called
            ``sep`` is the separator used to join results for display
        """
        kwargs.setdefault('wraplength', config.gui2.widget_size.main.width / 2)
        super().__init__(master, cnf, command=self.action, **kwargs)
        if not options or isinstance(options[0], str):
            self.codes = self.displays = options
        else:
            self.codes, self.displays = zip(*options)
        self.active = ()
        self.sep = sep

    def get(self):
        """get the last selected items"""
        return [self.codes[i] for i in self.active]

    def set(self, values):
        """set the items to be selected"""
        self.active = [self.codes.index(x) for x in values]
        self.set_text()

    def action(self, event=None):
        """display the popup window, set self.active and update button text"""
        options = {'values': self.displays, 'activate': self.active}
        if len(self.displays) > config.gui2.popup_height:
            options.update(listbox=ActivatingListbox, height=config.gui2.popup_height)
            widget = ScrolledListbox
        else:
            options.update(height=len(self.displays))
            widget = ActivatingListbox
        try:
            self.active = mtkd.WidgetDialog.ask(
                self.master, widget, options, getter='curselection')
        except mtkd.UserExitedDialog:
            pass
        self.set_text()

    def set_text(self):
        """set the text to the displays separated by semicolons"""
        self['text'] = self.sep.join(self.displays[i] for i in self.active)


class SearchMultiChoice(MultiChoicePopup):
    """MultiChoicePopup that gets values from searches"""

    def __init__(self, master, cnf={}, *,
                 action_ns: T.Type[core.ActionNamespace],
                 **kwargs):
        kwargs.setdefault('wraplength', config.gui2.widget_size.main.width / 2)
        options = [(o.id, str(o)) for o in
                   common.NSWithLogin(action_ns).search(())]
        super().__init__(master, cnf, options=options, **kwargs)

    def set(self, values):
        """update text.

            If ``values`` is a non-empty string,
            split it on ';' before passing to super()
        """
        if isinstance(values, str):
            if values:
                values = values.split(self.sep)
            else:
                values = ()
        super().set(values)


class FlagEnumMultiChoice(MultiChoicePopup):
    """Display FlagEnum options"""
    def __init__(self, master, cnf={}, *,
                 flag_enum: T.Type[enum.Flag],
                 get_name_prefix: str = '',
                 **kwargs):
        """create a new FlagEnumMultiChoice based on ``flag_enum``"""
        self.enum = flag_enum
        options = [(v.value, utils.get_name(get_name_prefix + k))
                   for k, v in flag_enum.__members__.items()]
        super().__init__(master, cnf, options, **kwargs)

    def get(self):
        return functools.reduce(operator.or_, map(self.enum, super().get()), self.enum(0))

    def set(self, value):
        # is there any way to properly do this?
        to_set = []
        for v in self.enum.__members__.values():
            if v in value:
                to_set.append(v.value)
        super().set(to_set)


class Header:
    def __init__(self, master, login_data, info_text, reset_data, exit_data):
        self.container = mtk.ContainingWidget(
            master,
            (Button, login_data),
            (Label, {'text': info_text}),
            (Button, reset_data),
            (Button, exit_data)
        )

    def set_info_text(self, new):
        self.container.widgets[1].config(text=new)

    def set_login_text(self, new):
        self.container.widgets[0].config(text=new)

    def __getattr__(self, name):
        return getattr(self.container, name)


@mtk.ScrollableWidget(height=config.gui2.widget_size.main.height,
                      width=config.gui2.widget_size.main.width)
class SearchResultWidget(mtk.ContainingWidget):
    def __init__(self, master, results, view_func):
        widgets = [(Label, {'text': utils.get_name('{}_results').format(len(results))})]
        for r in results:
            widgets.append((Button, {
                'text': r,
                'wraplength': config.gui2.widget_size.main.width,
                'command': partial(view_func, r.id)}))
        super().__init__(master, *widgets, direction=(tk.BOTTOM, tk.LEFT))
