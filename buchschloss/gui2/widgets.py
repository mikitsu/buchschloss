"""specific widgets and form helpers"""
import functools
import enum
import operator
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as tk_msg
from functools import partial

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
                 action_ns, allow_none=False, setter=False, condition=()):
        """Create a new instance.

        :param action_ns: is the ActionNamespace to search in
        :param allow_none: specifies whether an empty input is considered valid
        :param setter: makes this widget call ``.set_data`` on its form
          with results of ``action_ns.view_ns`` when a selection is made.
          This is especially/only useful for ID fields when editing.
        :param condition: specifies the condition with which to search

        The parameters ``allow_none`` and ``setter`` are mutually exclusive.
        """
        self.action_ns = action_ns
        values = [(o.id, str(o)) for o in action_ns.search(condition)]
        if allow_none:
            if setter:
                raise ValueError('``setter`` and ``allow_none`` are mutually exclusive')
            values.insert(0, (None, ''))
        super().__init__(form, master, name, values)
        if setter:
            self.widget.bind('<<ComboboxSelected>>', self._do_set)
            self._update_values = self._update_values_with_set

    def _update_values_with_set(self, new_value):
        super()._update_values(new_value)
        if len(self.widget['values']) == 1:
            self._do_set()

    def _do_set(self, event=None):  # noqa
        """Call .set() on the form with a .view_ns result"""
        result = self.action_ns.view_ns(self.get_simple())
        self.form.set_data({k: getattr(result, k) for k in dir(result)})


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
        error = self.validate_simple()
        if error is not None:
            tk_msg.showerror(message=error)
            return
        if not tk_msg.askyesno(utils.get_name('book::isbn'),
                               utils.get_name('interactive_question::isbn_autofill')):
            return
        try:
            data = utils.get_book_data(self.get_simple())
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
PasswordEntry = (formlib.Entry, 'ignore', {'extra_kwargs': {'show': '*'}})


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
        kwargs['button_options'] = {**(button_options or {}), 'wraplength': WRAPLENGTH}
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

    def set_simple(self, data):
        """Set the label text to ``data``"""
        if self.display == 'list':
            data = self.sep.join(data)
        self.widget['text'] = data

    def get_simple(self):
        """return the currently displayed text"""
        data = self.widget['text']
        if self.display == 'list':
            data = data.split(self.sep)
        return data


class LinkWidget(formlib.FormWidget):
    """Display a button that opens an info display when clicked"""
    def __init__(self, form, master, name, view_func):
        super().__init__(form, master, name)
        self.data = self.id = None
        self.widget = tk.Button(
            self.master,
            command=lambda: view_func(self.id),
            wraplength=WRAPLENGTH,
        )

    def set_simple(self, data):
        """update the displayed data"""
        self.data = data
        self.id = data.id
        self.widget['text'] = str(data)

    def get_simple(self):
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
                'command': partial(view_func, r.id)}))
        super().__init__(master, *widgets, direction=(tk.BOTTOM, tk.LEFT))


class FormTag(enum.Enum):
    SEARCH = '"search" action'
    NEW = '"new" action'
    EDIT = '"edit" action'
    VIEW = '"view" action'


class BaseForm(formlib.Form):
    """Base class for forms, handling get_name, default content and autocompletes"""
    form_name: str

    def __init__(self, frame, tag, submit_callback):
        super().__init__(frame, tag, submit_callback)
        self.set_data(config.gui2.entry_defaults.get(self.form_name).mapping)

    def __init_subclass__(cls, **kwargs):
        """Handle autocompletes and set cls.form_name"""
        cls.form_name = cls.__name__.replace('Form', '')
        # This will put every widget spec into the standard form, required below
        super().__init_subclass__(**kwargs)  # noqa -- it might accept kwargs later

        for k, v in config.gui2.get('autocomplete').get(cls.form_name).mapping.items():
            if k in cls.all_widgets:
                for *_, w_kwargs in cls.all_widgets[k].values():
                    w_kwargs.setdefault('autocomplete', v)

    def get_name(self, name):
        """redirect to utils.get_name inserting a form-specific prefix"""
        return utils.get_name('::'.join(('form', self.form_name, name)))


class SearchForm(BaseForm):
    """Add search options (and/or) + exact matching"""
    all_widgets = {
        'search_mode': {FormTag.SEARCH: (
            formlib.RadioChoices, [(c, utils.get_name(c)) for c in ('and', 'or')], {})},
        'exact_match': {FormTag.SEARCH: Checkbox},
    }

    def get_data(self):
        """ignore empty data"""
        if self.tag is FormTag.SEARCH:
            return {k: v for k, v in super().get_data() if v or isinstance(v, bool)}
        else:
            return super().get_data()

    def validate(self):
        """ignore errors from empty widgets"""
        errors = super().validate()
        # NOTE: the password entry will raise ValueError if the passwords don't
        # match, but it shouldn't be used in searches anyway.
        # All other widgets shouldn't raise exceptions in .get()
        if self.tag is FormTag.SEARCH:
            data = self.get_data()
            for k in errors.keys() - data.keys():
                del errors[k]


class AuthedForm(BaseForm):
    """add a 'current_password' field"""
    all_widgets = {
        'current_password': {
            FormTag.SEARCH: None,
            None: PasswordEntry,
        }
    }


class EditForm(BaseForm):
    """Adapt forms for the EDIT action.

    On FormTag.EDIT:
    Use OptionsFromSearch with setter=True for the first widget.
    Modify ``.get_data`` to include the value of the first widget under ``'*args'``.
    """
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.id_name, widget_spec = next(iter(cls.all_widgets.items()))
        if FormTag.EDIT in widget_spec:
            raise TypeError("can't use SetForEditForm if FormTag.EDIT is specified")
        widget_spec[FormTag.EDIT] = (OptionsFromSearch, getattr(core, cls.form_name), {})

    def get_data(self):
        """put the value of the ID widget under ``'*args'``"""
        data = super().get_data()
        if self.tag is FormTag.EDIT:
            data['*args'] = (data.pop(self.id_name),)
        return data


class ViewForm(BaseForm):
    """insert DisplayWidgets where a specific widget for FormTag.VIEW is not specified

    If the default widget (or any other widget if the default is None)
    is MultiChoicePopup (or a subclass), use ``'list'`` for the DisplayWidget.
    Otherwise, use ``'str'``.
    """
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for ws in cls.all_widgets.values():
            current = next(w for w in (ws[None], *ws.values()) if w is not None)[0]
            display = 'list' if issubclass(current, MultiChoicePopup) else 'str'
            ws.setdefault(FormTag.VIEW, (DisplayWidget, display, {}))
