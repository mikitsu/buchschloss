"""widgets"""

import tkinter as tk
from tkinter import Entry, Label
from tkinter.ttk import Button
from functools import partial
from collections import abc

import misc.tkstuff as mtk
from misc.tkstuff.blocks import PasswordEntry, CheckbuttonWithVar

from . import validation
from .. import utils
from .. import config


class ActionChoiceWidget(mtk.ContainingWidget):
    def __init__(self, master, actions, **kw):
        widgets = [(Button, {'text': utils.get_name(txt), 'command': cmd})
                   for txt, cmd in actions]
        super().__init__(master, *widgets, **kw)


@mtk.ScrollableWidget(height=config.GUI2_INFO_HEIGHT, width=config.GUI2_INFO_WIDTH)
class InfoWidget(mtk.ContainingWidget):
    def __init__(self, master, data):
        widgets = []
        for k, v in data.items():
            widgets.append((Label, {'text': k}))
            if v is None:
                widgets.append((Label, {}))
            elif isinstance(v, str):
                widgets.append((Label, {'text': utils.break_string(v, config.INFO_LENGTH)}))
            elif isinstance(v, abc.Sequence):
                if len(v) and isinstance(v[0], type) and issubclass(v[0], tk.Widget):
                    widgets.append(v)
                else:
                    widgets.extend(v)
                    if not len(v) % 2:
                        widgets.append((Label, {}))  # padding to keep `k` on left
            else:
                raise ValueError('`{}` could not be handled'.format(v))
        super().__init__(master, *widgets, horizontal=2)


class ListEntryMixin:
    def __init__(self, master, cnf={}, sep=';', **kw):
        self.sep = sep
        super().__init__(master, cnf, **kw)

    def get(self):
        v = super().get()
        if v:
            return v.split(self.sep)
        else:
            return []


class OptionalCheckbuttonWithVar(CheckbuttonWithVar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state(['alternate'])
        self.is_alternate = True
        self.variable.trace('w', lambda *a, s=self:setattr(s, 'is_alternate', False))

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


@mtk.ScrollableWidget(height=config.GUI2_SEARCH_HEIGHT, width=config.GUI2_SEARCH_WIDTH)
class SearchResultWidget(mtk.ContainingWidget):
    def __init__(self, master, results, view_func):
        widgets = [(Label, {'text': utils.get_name('{}_results').format(len(results))})]
        for r in results:
            widgets.append((Button, {'text': utils.break_string(str(r), config.RESULT_LENGTH),
                                     'command': partial(view_func, r.id)}))
        super().__init__(master, *widgets, direction=(tk.BOTTOM, tk.LEFT))


ListEntry = type('ListEntry', (ListEntryMixin, Entry), {})
ListREntry = type('ListREntry', (ListEntryMixin, mtk.RememberingEntry), {})
ISBNEntry = mtk.ValidatedWidget.new_cls(Entry, validation.ISBN_validator)
NonEmptyEntry = mtk.ValidatedWidget.new_cls(Entry, validation.nonempty)
NonEmptyREntry = mtk.ValidatedWidget.new_cls(mtk.RememberingEntry, validation.nonempty)
ClassEntry = mtk.ValidatedWidget.new_cls(Entry, validation.class_validator)
IntListEntry = mtk.ValidatedWidget.new_cls(ListEntry, validation.int_list)
IntEntry = mtk.ValidatedWidget.new_cls(Entry, validation.type_int)
NullEntry = mtk.ValidatedWidget.new_cls(Entry, validation.none_on_empty)
NullREntry = mtk.ValidatedWidget.new_cls(mtk.RememberingEntry, validation.none_on_empty)


class NonEmptyPasswordEntry(PasswordEntry, NonEmptyEntry):
    pass
