"""widgets"""

import tkinter as tk
from tkinter import Entry, Label, Button
from functools import partial
from collections import abc
import typing as T

from ..misc import tkstuff as mtk
from ..misc.tkstuff import dialogs as mtkd
from ..misc.tkstuff.blocks import PasswordEntry, CheckbuttonWithVar

from . import validation
from .. import utils
from .. import config
from .. import core


class ListEntryMixin(Entry):
    def __init__(self, master, cnf={}, sep=';', **kw):
        self.sep = sep
        super().__init__(master, cnf, **kw)

    def get(self):
        v = super().get()
        if v:
            return v.split(self.sep)
        else:
            return []


ListEntry = type('ListEntry', (ListEntryMixin, Entry), {})
ListREntry = type('ListREntry', (ListEntryMixin, mtk.RememberingEntry), {})
ISBNEntry = mtk.ValidatedWidget.new_cls(Entry, validation.ISBN_validator)
NonEmptyEntry = mtk.ValidatedWidget.new_cls(Entry, validation.nonempty)
NonEmptyREntry = mtk.ValidatedWidget.new_cls(mtk.RememberingEntry, validation.nonempty)
ClassEntry = mtk.ValidatedWidget.new_cls(Entry, validation.class_validator)
IntListEntry = mtk.ValidatedWidget.new_cls(ListEntry, validation.int_list)
IntEntry = mtk.ValidatedWidget.new_cls(Entry, validation.type_int)
NullIntEntry = mtk.ValidatedWidget.new_cls(Entry, validation.int_or_none)
NullEntry = mtk.ValidatedWidget.new_cls(Entry, validation.none_on_empty)
NullREntry = mtk.ValidatedWidget.new_cls(mtk.RememberingEntry, validation.none_on_empty)


class SeriesEntry(mtk.ContainingWidget):
    """Entry combining a name for the series and an integer input for the number"""

    def __init__(self, master, **kw):
        self.number_dummy = core.Dummy(set=self.set_number,
                                       get=lambda: 1,
                                       validate=lambda: (1, 0))
        widgets = [
            (NullREntry, {'rem_key': 'book-series'}),
            (NullIntEntry, {'width': 2}),
        ]
        super().__init__(master, *widgets, **kw)

    def validate(self):
        """check whether the series number is valid

            - if it is a number
            - if it is only given in combination with a series
        """
        # Validation always succeeds
        _, series = self.widgets[0].validate()
        number_valid, series_number = self.widgets[1].validate()
        if not number_valid:
            return False, utils.get_name('error::gui2::series_number_must_be_int')
        if series is None and series_number is not None:
            return False, utils.get_name('error::gui2::number_without_series')
        return True, (series, series_number)

    def set_number(self, number):
        mtk.get_setter(self.widgets[1])(number)

    def set(self, value):
        mtk.get_setter(self.widgets[0])(value)

    def get(self):
        return mtk.get_getter(self.widgets[0])()


class ActionChoiceWidget(mtk.ContainingWidget):
    def __init__(self, master, actions, **kw):
        widgets = [(Button, {'text': utils.get_name('actions::' + txt), 'command': cmd,
                             'padx': 50})
                   for txt, cmd in actions]
        super().__init__(master, *widgets, **kw)


class OptionsFromSearch(mtk.OptionChoiceWidget):
    """an option widget that gets its options from search results"""

    def __init__(self, master, *, action_ns: core.ActionNamespace,
                 attribute='name', allow_none=False, **kwargs):
        self.__attribute = attribute
        values = [(getattr(o, attribute), str(o)) for o in
                  action_ns.search((), login_context=core.internal_lc)]
        if allow_none:
            values.insert(0, (None, ''))
        super().__init__(master, values=values, **kwargs)

    def set(self, value):
        return super().set(getattr(value, self.__attribute, value))


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


class OptionalCheckbuttonWithVar(CheckbuttonWithVar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state(['alternate'])
        self.is_alternate = True
        self.variable.trace('w', lambda *a, s=self: setattr(s, 'is_alternate', False))

    def get(self):
        if self.is_alternate:
            return None
        else:
            return super().get()

    def set(self, value):
        if value is None:
            self.state(['alternate'])
            self.is_alternate = True
        else:
            super().set(value)


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
    # TODO: move to misc

    def __init__(self, master, cnf={}, options=(), **kwargs):
        """create a new MultiChoicePopup

            ``root`` is the master of the generated popup
            ``options`` is a sequence of (<code>, <display>) tuples
                <display> will be shown to the user, while <code>
                will be used when .get is called
        """
        super().__init__(master, cnf, command=self.action, **kwargs)
        if not options or isinstance(options[0], str):
            self.codes = self.displays = options
        else:
            self.codes, self.displays = zip(*options)
        self.active = ()

    def get(self):
        """get the last selected items"""
        return [self.codes[i] for i in self.active]

    def set(self, values):
        """set the items to be selected"""
        self.active = [self.codes.index(x) for x in values]

    def action(self, event=None):
        """display the popup window, set self.value and update button text"""
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


class SearchMultiChoice(MultiChoicePopup):
    """MultiChoicePopup that gets values from searches"""

    def __init__(self, master, cnf={}, *,
                 action_ns: core.ActionNamespace,
                 **kwargs):
        kwargs.setdefault('wraplength', config.gui2.widget_size.main.width / 2)
        options = [(o, str(o)) for o in
                   action_ns.search((), login_context=core.internal_lc)]
        super().__init__(master, cnf, options=options, **kwargs)

    def action(self, event=None):
        """update the text"""
        super().action(event)
        self.set_text()

    def set(self, values):
        """update text.

            If ``values`` is a non-empty string,
            split it on ';' before passing to super()
        """
        if isinstance(values, str):
            if values:
                values = values.split(';')
            else:
                values = ()
        super().set(values)
        self.set_text()

    def set_text(self):
        """set the text to the displays separated by semicolons"""
        self['text'] = ';'.join(self.displays[i] for i in self.active)


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


class NonEmptyPasswordEntry(PasswordEntry, NonEmptyEntry):
    pass
