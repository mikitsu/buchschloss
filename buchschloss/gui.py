"""Graphical User Interface"""
print('started', __package__)
from tkinter import *
from tkinter.ttk import *
import tkinter.messagebox as msg
import tkinter.simpledialog as dia
import tkinter.font as tk_font

from functools import wraps, partial
from types import SimpleNamespace
import datetime
import typing as T
import sys
import logging

from . import utils
from buchschloss import config
from buchschloss.core import *

print('imported')


def log_call(f):
    @wraps(f)
    def new(*args, **kwargs):
        logging.warning(f'function {f.__name__} called with {args} and {kwargs}')
        r = f(*args, **kwargs)
        logging.warning(f'returned {r}')
        return r

    return new


# -------------------- Utilities --------------------


class ExtendedOptionMenu(OptionMenu):
    def __init__(self, master=None, *values, default=None, **kwargs):
        if default is None and values:
            default = values[0]
        self.__var = StringVar(master, default)
        super().__init__(master, self.__var, default, *values, **kwargs)

    def curselection(self):
        return self.__var.get()

    def set(self, value):
        self.__var.set(value)


class PasswordEntry(Entry):
    def __init__(self, *args, **kwargs):
        kwargs.update({'show': '*'})
        super().__init__(*args, **kwargs)


def display_error(f):
    """Wrapper for functions potentially raising BuchSchlossBaseError.

    Catch BuchSchlossBaseError and display it in a tk.messagebox error dialog
    return False if an error was raised
    If the wrapped function returns None, return True"""

    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            r = f(*args, **kwargs)
        except BuchSchlossBaseError as e:
            msg.showerror(e.title, e.message)
            return False
        except Exception:
            msg.showerror(message='Es ist ein unerwarteter Fehler aufgetreten')
            raise
        if r is None:
            return True
        else:
            return r
    return wrapper


def is_final(path=True, display_msg=True):
    """Wrapper for functions performing final tasks.

    reset the gui after finishing, wrap with display_error
    if `display_msg` is True, display a success message if the function returns a truthy model
    if `path` is True, if will also be wrapped with @takes_path and
    resetting will use forget_along_path() instead of reset(), saving resources"""

    def wrapper_maker(f):
        f = display_error(f)
        expressions = []
        if path:
            expressions.extend(['_d.__setitem__("v", f(*args, **kwargs))',
                                'cleanup(kwargs["top"])',
                                'forget_along_path(kwargs["path"])'])
        else:
            expressions.extend(['_d.__setitem__("v", f(*args, **kwargs))',
                                'reset()'])
        if display_msg:
            expressions.append('(msg.showinfo(None, "Die Aktion wurde erolgreich durchgeführt.")'
                               ' if _d["v"] else None)')
        wrapper = eval('lambda *args, f=f, _d={}, **kwargs: (' + ','.join(expressions) + ')')
        if path:
            wrapper.__name__ = f.__name__
            wrapper = takes_path(wrapper)
        return wraps(f)(wrapper)

    return wrapper_maker


@display_error
def int_entry(widget):
    """Try to get an integer model from the passed Entry widget.
    Raise a BuchSchlossBaseError on failure"""
    c = widget.get()
    try:
        r = int(c.replace(' ', ''))
        return r
    except ValueError:
        raise BuchSchlossBaseError('keine Zahl',
                               'Die Zeichenfolge %s konnte nicht in eine Zahl umgewandelt werden.' % c)


def list_entry(value: str, delimiter=';'):
    return value.split(delimiter) if value else []


def follow_path(path: T.Iterable, top: dict = None):
    """follow the given path into the given dict, starting with top

    a top model of None evaluates to `widgets['middle']`
    If the path is a str, it will be .split()"""
    if isinstance(path, str):
        path = path.split()
    if top is None:
        top = widgets['middle']
    for p in path:
        top = top[p]
    return top


def get_path_steps(path: T.Iterable, top: dict = None):
    """yield all dicts along the given path, including top.

    a top model of None evaluates to widgets['middle']"""
    if isinstance(path, str):
        path = path.split()
    if top is None:
        top = widgets['middle']
    for p in path:
        if isinstance(top, dict):
            yield top
            top = top[p]
        else:
            break


def entry_default(path: T.Iterable):
    """set the contents of entry widgets to their default values"""
    for k, v in follow_path(path).items():
        if isinstance(v, Entry) and ' '.join((path, k)) in config.ENTRY_DEFAULTS:
            v.delete(0, END)
            v.insert(0, config.ENTRY_DEFAULTS[' '.join((path, k))])


def forget_all(top: T.Iterable = None):
    """run .grid_forget() on all elements and sub-elements starting from `top`.

    if `top` is a `str`, it is set to the result of `follow_path(top)`
    if `top` is None, if is set to `widgets['middle']`"""
    if top is None:
        top = widgets['middle']
    if isinstance(top, str):
        top = follow_path(top)
    for v in top.values():
        if isinstance(v, dict):
            forget_all(v)
        elif isinstance(v, Widget):
            v.grid_forget()


def forget_along_path(path: str):
    """run .grid_forget() on all widgets along the given path and then call show_all('')"""
    for d in get_path_steps(path):
        for w in d.values():
            if isinstance(w, Widget):
                w.grid_forget()
    show_all('')


def show_sub(top: dict) -> dict:
    """grid the `show` element of each subelement of top"""
    x = 0
    for a in top.values():
        if isinstance(a, dict):
            a['show'].grid(row=0, column=x)
            x += 1
    return top


def show_to(path: str) -> dict:
    """Show all `base` widgets on the given path after `forget_all()`"""
    forget_all()
    d = widgets['middle']
    for a in path.split():
        d = d[a]
        d['base'].grid()
    return d


def show_all(path):
    """return `show_sub(show_to(path))` if the path consists of dicts (excl. base & show),
    otherwise `grid_order(show_to(path), path)`"""
    top = show_to(path)
    if any(isinstance(v, dict) for v in tuple(top.values())[:3]):  # with base and show, we need 3
        return show_sub(top)
    else:
        return grid_order(top, path)


def cleanup(top: dict):
    """Clear entry widgets and destroy temporary ones"""
    to_pop = []
    for k, v in top.items():
        if type(v) in (Entry, Listbox):
            v.delete(0, END)
        if k.startswith('tmp_'):
            v.destroy()
            to_pop.append(k)
    for a in to_pop:
        top.pop(a)


def reset(top: dict = None, _first=True):
    """Reset everything under `top`.

    Run forget_all(top), cleanup() for every dict under `top` and `show_all('')`."""
    if top is None:
        top = widgets['middle']
    forget_all(top)
    for v in (v for v in top.values() if isinstance(v, dict)):
        cleanup(v)
        reset(v, False)
    if _first:
        show_all('')


def show_top():
    """display the top part of the gui"""
    follow_path('top base', widgets).pack(anchor=N)
    for x, k in enumerate('btn_login login space_1 btn_abort space_2 btn_exit'.split()):
        widgets['top'][k].grid(row=0, column=x)


def grid_order(top: dict, order: T.Iterable, btn=True, x=0):
    """order the passed widgets along with their correspondent `_txt` parts, horizontally
    return the y-model of the last row

    `top` is the dict containing the widgets to .grid()
    `order` is an iterable of the widget names
        if it is a string, it is set to `follow_path(order, FIELDS)`
        if this yields a dictionary, order is set to the sum of the values converted to a list
    if `btn` is True, top['btn_do'] is .grid() at the end"""
    if isinstance(order, str):
        order = follow_path(order, FIELDS)
        if isinstance(order, dict):
            order = order['**grid_order**']
    y = 0
    for k in order:
        if k != 'btn_do':  # present in FIELDS if other buttons are defined
            top[k + '_txt'].grid(row=y, column=x)
            top[k].grid(row=y, column=x + 1) #  , ipadx=50)  TODO: do we want padding?
            y += 1
    if btn:
        top['btn_do'].grid(row=y, columnspan=2)
        y += 1
    return y


def takes_path(f):
    """Add `path` based on `f.__name__` and `top`
    (`show_to(path)` if `f.__name__.endswith('_start')`
    and `follow_path(path)` if `f.__name__.endswith('_final')`"""

    @wraps(f)
    def new(*args, **kwargs):
        path = ' '.join(f.__name__.split('_')[:-1])
        if f.__name__.endswith('_start'):
            top = show_to(path)
        elif f.__name__.endswith('_final'):
            top = follow_path(path)
        else:
            raise ValueError('f.__name__ needs to end with "_start" or "_final"')
        return f(*args, top=top, path=path, **kwargs)

    return new


# -------------------- Action Handlers --------------------


@display_error
def action_login():
    """Try to log the user in"""
    top = widgets['top']
    if top['btn_login'].config('text')[-1] == 'Ausloggen':
        logout()
        top['btn_login'].config(text='Einloggen')
        top['login'].config(text='nicht eingeloggt')
    else:
        uname = dia.askstring('Login', 'Nutzername:')
        if uname is None:
            return
        passwd = dia.askstring('Login', 'Passwort:', show='*')
        if passwd is None:
            return
        login(uname, passwd)
        top['btn_login'].config(text='Ausloggen')
        top['login'].config(text='eingeloggt als %s (%s)' % (uname, get_level(),))
    forget_all(widgets['top'])
    show_top()


@takes_path
def new_person_start(top=None, path=None):
    """Show the widgets to create a new Person"""
    entry_default(path)
    grid_order(top, path)


@is_final()
def new_person_final(top=None, path=None):
    """Create a new Person"""
    # TODO: convert stuff to right types
    s_nr = int_entry(top['id'])
    max_borrow = int_entry(top['max_borrow'])
    first_name = top['first_name'].get()
    last_name = top['last_name'].get()
    class_ = top['class_'].get()
    libraries = list_entry(top['libraries'].get())
    new_person(s_nr=s_nr, first_name=first_name, last_name=last_name,
               class_=class_, max_borrow=max_borrow, libraries=libraries)


@display_error
def new_book_autofill(event):
    """Try to use utils.get_book_data"""
    if not msg.askyesno('Buch erstellen', 'Soll anhand der ISBN versucht werden,'
                                          ' einige Daten automatisch einzufllen?'):
        return
    top = follow_path('new book')
    isbn = int_entry(top['isbn'])
    for k, v in utils.get_book_data(isbn).items():
        top[k].delete(0, END)
        top[k].insert(0, v)


@takes_path
def new_book_start(top=None, path=None):
    """Show the widgets for creating a Book"""
    entry_default(path)
    grid_order(top, path)


@is_final(display_msg=False)
def new_book_final(top=None, path=None):
    """Create a Book"""
    data = {}
    for k in follow_path(path, FIELDS):
        data[k] = top[k].get()
    data['groups'] = set(list_entry(top['groups'].get()))  # TODO: this right?
    b_id = new_book(**data)
    msg.showinfo('Buch erstellt', 'Das Buch hat die ID %i' % b_id)


@is_final(path=False)
def new_library_group_final(what):
    """create a `what` (library or group)"""
    top = follow_path(['new', what])
    try:
        people = [int(v.strip()) for v in top.get('people', SimpleNamespace(get=lambda: ""))
            .get().split(';') if v]
        books = [int(v.strip()) for v in top['books'].get().split(';') if v]
    except ValueError:
        raise BuchSchlossBaseError('neue %s' % utils.get_name(what),
                               'Es gab ein Fehler beim Umwandeln in eine Zahl.')
    errors = new_library_group(what, top['name'].get(), books, people)
    if errors:
        raise BuchSchlossBaseError('neue ' + utils.get_name(what), 'Es sind folgende Fehler aufgeterten:\n\n'
                                   + '\n'.join(errors))


@is_final()
def new_member_final(top=None, path=None):
    """Create a new Member"""
    name = top['name'].get()
    password = top['password'].get()
    level_str = top['level'].curselection()
    if level_str not in config.MEMBER_LEVELS[1:-1]:
        raise BuchSchlossBaseError('Unerlaubter Wert',
                               '"%s" ist kein erlauter Wert für die Stufe. Bitte wähle aus dem Drop-Down-Menü'
                                   % level_str)
    level = config.MEMBER_LEVELS.index(level_str)
    if password != top['password_2'].get():
        top['password'].delete(0, END)
        top['password_2'].delete(0, END)
        raise BuchSchlossBaseError('Passwörter', 'Die Passwörter stimmen nicht überein.')
    new_member(name, password, level)


@display_error
def view_final(what, pk=None):
    """View `what`. if pk is None, ask for the ID"""

    def end():
        cleanup(top)
        reset()

    top = show_to('view ' + what)
    name = utils.get_name(what)
    if pk is None:
        pk = dia.askinteger(name + '-Inspektion', 'Bitte gib die %s an.'
                            % ({'book': 'ID des Buches', 'person': 'Schülerausweis-Nr. des Schülers'}[what],))
        if pk is None:
            return end()
    if what == 'book':
        try:
            data = view_book(pk)
        except BuchSchlossBaseError:
            end()
            raise
        data['concerned_people'] = data['concerned_people'].replace(';', ';\n')
        for k, v in data.items():
            if k in top['left']:
                top['left'][k].config(text=str(v))
            elif k in top['right']:
                top['right'][k].config(text=str(v))
        top['left']['base'].grid(row=0, column=0)
        top['right']['base'].grid(row=0, column=1)
        grid_order(top['left'], 'view book left', btn=False)
        grid_order(top['right'], 'view book right', btn=False, x=2)
        if data['borrowed_by_id'] is not None:
            func = partial(view_final, 'person', data['borrowed_by_id'])
            top['right']['borrowed_by'].config(command=func)
    elif what == 'person':
        try:
            data = view_person(pk)
        except BuchSchlossBaseError:
            end()
            raise
        for k in follow_path('view person', FIELDS)[Label]:
            if k != 'borrows':
                top[k].config(text=data[k])
        for i, (txt, b_id) in enumerate(zip(data['borrows'], data['borrow_book_ids'])):
            top['tmp_borrow_%i' % i] = Button(top['borrows'], text=txt,
                                              command=partial(view_final, 'book', b_id))
            top['tmp_borrow_%i' % i].grid()
        grid_order(top, 'view person', btn=False)
    else:
        raise ValueError('Invalid model "%s" for ``what`` in view_final' % (what,))


@display_error
def edit_person_start(s_nr=None):
    """Prepare and show widgets for edition a Person"""

    def cmd_pay_date():
        edit_person(s_nr, pay_date=datetime.date.today())

    top = show_to('edit person')
    if s_nr is None:
        s_nr = dia.askinteger('Verwaltung', 'Bitte gib die Schülerausweisnummer an.')
        if s_nr is None:
            return reset()
    data = view_person(s_nr)
    for k in FIELDS['edit']['person'][Label]:
        top[k].config(text=data[k])
    for k in FIELDS['edit']['person'][Entry]:
        top[k].insert(0, data[k])
    top['tmp_pay_date'] = Button(top['base'], text='Nutzer hat bezahlt', command=cmd_pay_date)
    grid_order(top, 'edit person')
    top['tmp_pay_date'].grid(row=3, column=2)


@is_final()
def edit_person_final(top=None, path=None):
    """Edit a Person"""
    s_nr = int(top['id'].cget('text'))
    max_borrow = int_entry(top['max_borrow'])
    if not max_borrow:
        return False
    r = edit_person(s_nr,
                    max_borrow=max_borrow,
                    libraries=top['libraries'].get().split(';'),
                    class_=top['class_'].get(),
                    )
    if r:
        raise BuchSchlossBaseError(None, 'Es sind folgende Fahler aufgetreten:'
                                   + '\n'.join(r))


@display_error
def edit_book_start(b_id=None):
    """Prepare editing a Book"""
    top = show_to('edit book')
    if b_id is None:
        b_id = dia.askinteger('Buch verwalten', 'Bitte gib die ID des Buches an.')
        if b_id is None:
            return reset()
    data = view_book(b_id)
    for k in FIELDS['edit']['book'][Label]:
        top[k].config(text=data[k])
    for k in FIELDS['edit']['book'][Entry]:
        top[k].insert(0, data[k])
    grid_order(top, 'edit book')


@is_final()
def edit_book_final(top=None, path=None):
    """Edit a book."""
    b_id = int(top['id'].cget('text'))
    r = edit_book(b_id,
                  shelf=top['shelf'].get(),
                  library=top['library'].get(),
                  groups=top['groups'].get().split(';'))
    if r:
        raise BuchSchlossBaseError('Buch bearbeiten', 'Beim Bearbeiten sind folgende Fehler aufgeterten\n\n'
                                   + '\n'.join(r))


def edit_library_group_start(what: str):
    top = show_to('edit %s' % what)
    y = grid_order(top, 'edit %s' % what, False)
    top['btn_container']['base'].grid(row=y, column=0, columnspan=2)
    for btn in FIELDS['edit'][what]['btn_container'][Button]:
        top['btn_container'][btn].pack(side=LEFT)


@is_final(path=False)
def edit_library_group_final(what: str, action: str):
    top = follow_path(['edit', what])
    name = top['name'].get()
    try:
        books = map(int, list_entry(top['books']))
        if what == 'library':
            people = map(int, list_entry(top['people'].get()))
        else:
            people = ()
    except ValueError:
        raise BuchSchlossBaseError('', 'Die Zeichenfolge konnte nicht in eine Zahl umgewandelt werden')
    edit_library_group(what, action, name, people=people, books=books)


def edit_activate_group_start_old():
    top = show_to('edit activate_group')
    y = grid_order(top, ('name', 'library'), False)
    top['on'].grid(row=y, column=0)
    top['off'].grid(row=y, column=1)


@is_final(path=False)
def edit_activate_group_final():
    top = follow_path('edit activate_group')
    errors = activate_group(
        top['name'].get(),
        list_entry(top['src_library'].get()),
        top['dest_library'].get()
    )
    if errors:
        raise BuchSchlossBaseError('Gruppe aktivieren',
                               'Es sind folgende Fehler aufgetreten\n\n'
                                   + '\n'.join(errors))


@takes_path
@display_error
def edit_member_start(name=None, path=None, top=None):
    """Prepare editing a Member"""

    def cmd_change_password():
        current = dia.askstring('Passwort ändern', 'Bitte gib dein Passwort ein.', show='*')
        new = current and dia.askstring('Passwort ändern', 'Bitte gib das neue Passwort ein.', show='*')
        new2 = new and dia.askstring('Passwort ändern', 'Bitte wiederhole das neue Passwort.', show='*')
        if not new2:
            return
        if new == new2:
            change_password(name, current, new)
            msg.showinfo('Passwort ändern', 'Das passwort wurde geändert.')
        else:
            msg.showerror('Passwort ändern', 'Die Passworter stimmen nicht überein')

    if name is None:
        name = dia.askstring('Mitglied verwalten', 'Bitte gib den Namen an.')
        if name is None:
            return reset()
    top['change_password'].config(command=cmd_change_password)
    top['name'].config(text=name)
    try:
        top['level'].set(config.MEMBER_LEVELS[view_member(name)['level']])
    except:
        forget_along_path(path)
        raise
    grid_order(top, path)
    top['change_password'].grid(row=1, column=2)


@is_final()
def edit_member_final(top=None, path=None):
    """Edit a Member."""
    name = top['name'].cget('text')
    try:
        level = config.MEMBER_LEVELS.index(top['level'].curselection())
    except IndexError:
        raise BuchSchlossBaseError('Mitglied Verwalten', 'Bitte wähle eine Stufe aus der Drop-Down-Liste.')
    edit_member(name, level=level)


def borrow_start():
    """Prepare borrowing: display the latest borrowers"""
    top = show_to('borrow')
    y = grid_order(top, FIELDS['borrow'])
    latest = misc_data.latest_borrowers  # avoid constantly reading from DB TODO: caching?
    for i in range(min(config.no_latest_borrowers_show, len(latest))):
        p_data = view_person(latest[i])
        top['tmp_btn_latest_borrows_%i' % i] = Button(top['base'], text=p_data['__str__'],
                                                      command=partial(borrow_final, p_data['id']))
        top['tmp_btn_latest_borrows_%i' % i].grid(row=y, column=i % 2)
        if i % 2:
            y += 1


@is_final()
def borrow_final(s_nr=None, top=None, path=None):
    """Borrow a Book.

    If id is None, read from the GUI"""
    if s_nr is None:
        s_nr = int_entry(top['id'])
    b_id, time = int_entry(top['b_id']), int_entry(top['time'])
    if any(isinstance(x, bool) for x in (s_nr, b_id, time)):
        return False
    borrow(b_id, s_nr, time)


@is_final()
def restitute_final(top=None, path=None):
    """Return a Book."""
    restitute(int_entry(top['b_id']), int_entry(top['id']))


# TODO: add search -- done in gui2


def end_app():
    if msg.askokcancel('Beenden', 'Möchtest du wirklich das Programm beenden?'):
        if (sys.stderr.error_happened and
                msg.askokcancel('Fehler',
                                'Während des Betriebs ist ein unerwarteter Fehller aufgetreten. '
                                'Soll Michael eine Email mit der Fehlermeldung erhalten?')):
            try:
                utils.send_mailgun('Error in Schuelerbuecherei', '\n\n\n'.join(sys.stderr.error_texts))
            except utils.requests.RequestException as e:
                msg.showerror('Fehler', 'Es ist ein unerwarteter Fehler beim Versenden aufgetreten:\n' + str(e))
        root.destroy()
        sys.exit()


new_library_final = partial(new_library_group_final, 'library')
new_group_final = partial(new_library_group_final, 'group')
edit_library_final = partial(edit_library_group_final, 'library')
edit_group_final = partial(edit_library_group_final, 'group')
# -------------------- Widgets & Data --------------------


root = Tk()
default_font = tk_font.nametofont('TkDefaultFont')
default_font.config(**config.gui_font)
root.option_add('*font', default_font)


def add_fields(dest: dict, source: 'FieldsType', base: T.Type[Widget], tree: tuple,
               default_widget=None, include_txt=frozenset()):
    """Add widgets to `dest` recursively from `source`."""

    def do_include_txt(widget, name):
        if widget in include_txt:
            dest[k][name + '_txt'] = Label(dest[k]['base'], text=utils.get_name(name) + ':')
            g_o.append(name)

    default_widget = source.pop('**default_widget**', default_widget)
    include_txt |= source.pop('**include_txt**', set())
    include_txt -= source.pop('**exclude_txt**', set())
    for k, v in source.items():
        if isinstance(k, type) and issubclass(k, Widget):
            continue
        elif not isinstance(k, str):
            print('We got this here: {!r}'.format(k))
        if k == '**with_args**':
            for n, (w, a, kw) in v.items():
                dest[n] = w(dest['base'], *a, **kw)
            continue
        dest[k] = {'base': Label(base)}
        show_cmd = globals().get(
            '_'.join((*tree, k, 'start')), lambda x=' '.join((*tree, k)): show_all(x))
        if isinstance(v, dict):
            show_cmd = v.pop('**show_cmd**', show_cmd)
            dest[k]['show'] = Button(base, command=show_cmd, text=utils.get_name(k))
            if any(issubclass(w, Widget) for w in v if isinstance(w, type)):
                v_old = v.copy()
                v_old.setdefault(Button, {'btn_do': globals().get(
                    '_'.join(tree + (k, 'final',)))})
                g_o = v.setdefault('**grid_order**', [])
                v = {'**grid_order**': g_o}
                for widget, data in v_old.items():
                    if widget == '**with_args**':
                        for n, (w, a, kw) in data.items():
                            dest[k][n] = w(dest[k]['base'], *a, **kw)
                            do_include_txt(w, n)
                    elif isinstance(widget, str) and widget.startswith('**') and widget.endswith('**'):
                        continue
                    elif isinstance(widget, type) and issubclass(widget, Button):
                        for n, c in data.items():
                            dest[k][n] = Button(dest[k]['base'], text=utils.get_name(n), command=c)
                            do_include_txt(widget, n)
                    elif isinstance(widget, type) and issubclass(widget, Widget):
                        for n in data:
                            dest[k][n] = widget(dest[k]['base'])
                            do_include_txt(widget, n)
                    else:
                        v[widget] = data
            else:
                dest[k]['show'].config(text=utils.get_name(k))
            add_fields(dest[k], v, dest[k]['base'], tree + (k,), default_widget, include_txt)
        elif callable(default_widget):
            dest[k]['show'] = Button(base, text=utils.get_name(k), command=show_cmd)
            dest[k]['btn_do'] = Button(dest[k]['base'], text=utils.get_name('btn_do'),
                                       command=lambda x=globals().get('_'.join(tree + (k, 'final',))): x())
            for name in v:
                dest[k][name] = default_widget(dest[k]['base'])
                dest[k][name + '_txt'] = Label(dest[k]['base'], text=utils.get_name(name) + ':')


_person_common = 'id last_name first_name class_ libraries'.split()
FieldsType = T.Dict[str, T.Union['FieldsType', T.Type[Widget], T.Iterable[str],
                                 T.Dict[T.Type[Widget], T.Union[T.Iterable[str],
                                                                T.Dict[str, T.Callable]]]]]
FIELDS: FieldsType = {
    '**default_widget**': Entry,
    '**include_txt**': {Label, Entry, ExtendedOptionMenu, PasswordEntry},
    'new': {
        'person': _person_common + ['max_borrow'],
        'book': config.BOOK_DATA + 'library groups shelf'.split(),
        'library': 'name books people'.split(),
        'group': 'name books'.split(),
        'member': {Entry: ['name'],
                   PasswordEntry: ['password', 'password_2'],
                   '**with_args**': {'level': (ExtendedOptionMenu, config.MEMBER_LEVELS[1:-1], {}),
                                     },
                   },
    },
    'view': {
        '**default_widget**': Label,
        'book': {
            '**show_cmd**': partial(view_final, 'book'),
            '**include_txt**': {Button},
            'left': config.BOOK_DATA,
            'right': {
                '**grid_order**': ['borrowed_by'],
                Label: 'id shelf library groups status return_date'.split(),
                Button: {'borrowed_by': None},  # idea: view lib/group => button
                '**grid_order_include**': ['borrowed_by'],
            },
        },
        'person': {
            '**show_cmd**': partial(view_final, 'person'),
            Label: _person_common + ['borrows', 'pay_date']},
    },
    'edit': {
        'person': {
            Label: 'id last_name first_name'.split(),
            Entry: 'class_ max_borrow libraries'.split(),
        },
        'book': {
            Label: 'id isbn title author'.split(),
            Entry: 'library groups shelf'.split(),
        },
        'activate_group': {
            Entry: ['name', 'src_library', 'dest_library'],
        },
        'library': {
            '**show_cmd**': partial(edit_library_group_start, 'library'),
            Entry: ['name', 'books', 'people'],
            'btn_container': {
                Button: {k: partial(edit_library_group_final, 'library', k)
                         for k in ['add', 'remove', 'delete']},
            },
        },
        'group': {
            '**show_cmd**': partial(edit_library_group_start, 'group'),
            Entry: ['name', 'books'],
            'btn_container': {
                Button: {k: partial(edit_library_group_final, 'library', k)
                         for k in ['add', 'remove', 'delete']},
            },
        },
        'member': {
            Label: ['name'],
            Button: {'change_password': None, 'btn_do': edit_member_final},
            '**with_args**': {'level': (ExtendedOptionMenu, config.MEMBER_LEVELS, {}),
                              },
        },
    },
    # will be done in gui2
    #'search': {
    #    'person':  _person_common,
    #    'book': config.BOOK_DATA,
    #    '**with_args**': {
    #        'radio_and': (Radiobutton, (), {'model': 'and', 'text': 'UND'}),
    #        'radio_or': (Radiobutton, (), {'model': 'or', 'text': 'ODER'}),
    #    },
    #},
    'borrow': 'id b_id time'.split(),
    'restitute': ['b_id', 'id'],
}
widgets = {k: {'base': Label(root)} for k in ['top', 'middle']}  # create from fields

base = widgets['top']['base']
widgets['top'].update({
    #'tmp_btn_eval': Button(base, text='eval', command=
    #lambda: msg.showinfo('Result', str(eval(dia.askstring(None, 'eval'))))),
    'btn_login': Button(base, text='Einloggen', command=action_login),
    'login': Label(base, text='Nicht eingeloggt'),
    'space_1': Label(base, width=8),
    'btn_abort': Button(base, text='Abbrechen', command=reset),
    'space_2': Label(base, width=2),
    'btn_exit': Button(base, text='Programm beenden',
                       command=end_app)
})
print('defined')
add_fields(widgets['middle'], FIELDS, widgets['middle']['base'], ())
print('added fields')
# fine-tune some stuff that isn't done in add_fields
widgets['middle']['new']['book']['isbn'].bind('<FocusOut>', new_book_autofill)

# -------------------- Stuff to do last --------------------
# TODO: add late handling function
root.wm_protocol('WM_DELETE_WINDOW', end_app)


def start():
    sys.stderr = DummyErrorFile()
    root.attributes('-fullscreen', True)
    label_intro = Label(root, **config.intro)
    label_intro.pack(expand=True)

    def init():
        label_intro.destroy()
        show_top()
        widgets['middle']['base'].pack(anchor=S)
        show_all('')

    root.after(3000, init)
    mainloop()
