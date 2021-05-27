"""specific widgets and FormWidget classes"""
import functools
import operator
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import Label, Button
from functools import partial
from collections import abc

from ..misc import tkstuff as mtk

from .. import utils
from .. import config
from . import formlib


class SeriesInput(formlib.FormWidget):
    """Provide Entry widgets for a series name and number"""
    def __init__(self, form, master, name):
        super().__init__(form, master, name)
        self.widget = tk.Frame(self.form.frame)
        self.subwidgets = {
            'series': formlib.Entry(self.form, self.widget, 'series', 'none'),
            'series_number': formlib.Entry(
                self.form, self.widget, 'series_number', 'none',
                transform=int, extra_kwargs={'width': 2},
            ),
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


def options_from_search(action_ns, allow_none=False, condition=()):
    """Return a formlib.DropdownChoices tuple that gets choices from a search

    :param action_ns: is the ActionNamespace to search in
    :param allow_none: specifies whether an empty input is considered valid
    :param condition: specifies the condition with which to search
    """
    return (
        formlib.DropdownChoices,
        lambda: (*[(None, '')]*allow_none,
                 *((o.id, str(o)) for o in action_ns.search(condition))),
        {},
    )


ISBNEntry = (formlib.Entry, 'error', {'transform': utils.check_isbn})
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


class MultiChoicePopup(formlib.MultiChoicePopup):
    """provide thw ``wraplength`` argument and set ``max_height`` and ``sep``"""
    max_height = config.gui2.popup_height
    sep = config.gui2.option_sep

    def __init__(self, *args, button_options=None, **kwargs):
        kwargs['button_options'] = {
            **(button_options or {}),
            'wraplength': config.gui2.widget_size.main.width // 2,
        }
        super().__init__(*args, **kwargs)


def search_multi_choice(action_ns, condition=()):
    """Return a MultiChoicePopup tuple that gets choices from a search

    :param action_ns: is the ActionNamespace to search in
    :param condition: is an optional condition to apply to the search
    """
    return (
        MultiChoicePopup,
        lambda: [(o.id, str(o)) for o in action_ns.search(condition)],
        {},
    )


class FlagEnumMultiChoice(MultiChoicePopup):
    """Use a FlagEnum as option source"""
    def __init__(self, form, master, name, flag_enum):
        """Get the options from ``flag_enum``"""
        self.enum = flag_enum
        options = [(e, form.get_name('' + e.name)) for e in flag_enum]
        super().__init__(form, master, name, options)

    def get_simple(self):
        """convert individual codes to a FlagEnum instance"""
        return functools.reduce(operator.or_, super().get_simple(), self.enum(0))

    def set_simple(self, data):
        """convert a FlagEnum instance to individual codes"""
        super().set_simple([v for v in self.enum if v in data])


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
