"""Widget definitions for forms"""

import uuid
import re

import flask
from markupsafe import Markup, escape

from .. import core, utils, aforms
from . import logins


class ValidationError(Exception):
    pass


class BaseWidget:
    def __init__(self, form, name):
        self.form = form
        self.name = name

    def _error(self, reason):
        raise ValidationError(self.form.get_name(f'{self.name}::error::{reason}'))

    def validate(self, data):
        assert self.form.tag is not aforms.FormTag.VIEW
        return self._simple_validate(data[self.name])

    def _simple_validate(self, value):
        assert False
        return value

    def render(self, data):
        return Markup(
            f'<label>{escape(self.form.get_name(self.name))}:'
            f'<div>{self._simple_render(data.get(self.name))}</div></label>')


class Entry(BaseWidget):
    def __init__(self, form, name, on_empty, *, regex=None, transform=str, extra_kwargs={}, **kwargs):
        super().__init__(form, name)
        assert kwargs.keys() <= {'autocomplete', 'max_history'}
        assert extra_kwargs.keys() <= {'show'}, extra_kwargs
        self.on_empty = on_empty
        self.regex = regex
        self.transform = transform
        if extra_kwargs.get('show') == '*':
            self.input_type = 'password'
        elif transform is int:
            self.input_type = 'number'
        else:
            self.input_type = 'text'

    def _simple_render(self, value):
        # TODO: use (more?) HTML validation
        return (
            f'<input name="{self.name}" type="{self.input_type}" value="{escape(value or "")}"'
            + (' required' if self.on_empty == 'error' else '') + '>'
        )

    def _simple_validate(self, data):
        if not data:
            if self.on_empty == 'error':
                self._error('empty')
            elif self.on_empty == 'none':
                return None
        if self.regex is not None and re.search(self.regex, data) is None:
            self._error('regex')
        try:
            return self.transform(data)
        except ValueError:
            self._error('transform')


class ChoiceWidget(BaseWidget):
    def __init__(self, form, name, choices, default=0, new=False):
        super().__init__(form, name)
        if new:
            assert all(isinstance(x, str) for x in choices), choices
        assert default in (0, None)
        self.choices = choices if choices and isinstance(choices[0], tuple) else [(x, x) for x in choices]
        self.default = self.choices[0][0] if self.choices and default == 0 else None
        self.new = new
        assert all(isinstance(x, (int, str)) for x, _ in self.choices), self.choices

    def _simple_validate(self, value):
        if self.new:
            return value
        try:
            return next(v for v, _ in self.choices if str(v) == value)
        except StopIteration:
            print('ERROR', value, self.choices)
            raise ValidationError


class RadioChoices(ChoiceWidget):
    def _simple_render(self, value=None):
        if value is None:
            value = self.default
        return ''.join(
            f'<label><input type="radio" name="{self.name}" value="{escape(val)}"'
            + (' checked' if str(val) == str(value) and value is not None else '')
            + f'>{escape(display)}</label>'
            for val, display in self.choices
        )


class DropdownChoices(ChoiceWidget):
    def __init__(self, form, name, choices, default=0, search=True, new=False):
        choices = choices(**logins.lc_kwargs()) if callable(choices) else choices
        super().__init__(form, name, choices, default, new)
        # self.search = search  TODO: implement

    def _simple_render(self, value=None):
        if value is None:
            value = self.default
        options = ''.join(
            f'<option value="{name}" {"selected" if str(name) == str(value) and value is not None else ""}>{escape(display)}</option>'
            for name, display in self.choices
        )
        if self.new:
            list_id = uuid.uuid4()
            return (
                f'<input type="text" name="{self.name}" list="{list_id}">'
                f'<datalist id="{list_id}">{options}</datalist>'
            )
        else:
            return f'<select name="{self.name}">{options}</select>'


class MultiChoicePopup(DropdownChoices):
    def validate(self, data):
        return [super()._simple_validate(v) for v in data.getlist(self.name)]

    def render(self, data):
        return super().render({self.name: data.getlist(self.name)})

    def _simple_render(self, values):
        if self.new:
            input_id, list_id, button_id, selected_id = (uuid.uuid4() for _ in range(4))
            js_args = f'"{self.name}", "{input_id}", "{button_id}", "{selected_id}"'
            return (
                f'<input id="{input_id}" type="text" list="{list_id}">'
                f'<button id="{button_id}" type="button">+</button>'
                f'<datalist id="{list_id}">'
                + ''.join(f'<option value="{name}">{escape(display)}</option>' for name, display in self.choices) +
                '</datalist>'
                f'<ul id="{selected_id}"></ul>'
                f'<script>register_multichoice({js_args})'
                + ''.join(f'; insert_multichoice({js_args}, "{val}")' for val in values)
                + '</script>'
            )
        else:
            raise AssertionError  # TODO: implement



class OptionsFromSearch(DropdownChoices):
    def __init__(self, form, name, action_ns, *, allow_none=False, setter=False, condition=(), **kwargs):
        values = sorted((o['id'], o.string) for o in action_ns.search(condition, **logins.lc_kwargs()))
        assert not setter  # TODO: implement or change or whatever
        if allow_none:
            values.insert(0, (None, ''))
        kwargs.setdefault('default', None)
        super().__init__(form, name, values, **kwargs)


def FallbackOFS(form, name, action_ns, allow_none=False, fb_default=None):
    def __init__(self, *args, **kwargs):
        assert False  # TODO: implement


class SeriesInput(DropdownChoices):
    def __init__(self, form, name):
        assert name == 'series'
        series = core.Book.get_all_series(**logins.lc_kwargs())
        super().__init__(form, name, series, new=True)

    def _simple_render(self, data):
        return super()._simple_render() + '<input type="number" size="3" name="series_number">'


class SeriesInputNumber(Entry):
    def __init__(self, form, name):
        assert name == 'series_number'
        super().__init__(form, name, 'none', transform=int)

    def render(self, data):
        return ''

    def validate(self, data):
        if not data['series'] and data['series_number']:
            self._error('number_without_series')
        return super().validate(data)


class ConfirmedPasswordInput:
    def __init__(self, *args, **kwargs):
        assert False  # TODO: implement


class ISBNEntry(Entry):
    def __init__(self, form, name, fill):
        super().__init__(form, name, 'error', transform=utils.check_isbn)

    def _simple_render(self, value=None):
        return super()._simple_render(value) + '<script>register_isbn_autofill()</script>'


class Text(BaseWidget):
    def _simple_render(self, value):
        return f'<textbox name="{self.name}">{escape(value)}</textbox>'

    def _simple_validate(self, value):
        return value


class SearchMultiChoice(MultiChoicePopup):
    def __init__(self, *args, **kwargs):
        raise AssertionError  # TODO: implement


class Checkbox(BaseWidget):
    def __init__(self, form, name, allow_none=False, active=True):
        super().__init__(form, name)
        assert not allow_none  # TODO: implement
        self.active = active

    def _simple_render(self, value=False):
        return ''.join((
            f'<input name="{self.name}" type="checkbox"',
            " checked" if value else "",
            " disabled" if not self.active else "",
            '>',
        ))

    def validate(self, data):
        return self.name in data


class DisplayWidget(BaseWidget):
    def __init__(self, form, name, display='str', get_name=None):
        assert get_name is None  # TODO: implement
        assert display in ('str', 'list')
        super().__init__(form, name)
        self.display = display

    def _simple_render(self, value):
        if not value:
            return ''
        if self.display == 'str':
            return f'<span>{escape(value)}</span>'
        elif self.display == 'list':
            return '<ul><li>' + '</li><li>'.join(map(escape, value)) + '</li></ul>'


class LinkWidget(BaseWidget):
    def __init__(self, form, name, view_key, attr=None, multiple=False):
        super().__init__(form, name)
        self.view_key = view_key
        self.attr = attr
        self.multiple = multiple

    def _simple_render(self, value):
        if value is None:
            return ''
        def mklink(item):
            if self.attr is None:
                arg = item
            else:
                try:
                    arg = item[self.attr]
                except core.BuchSchlossPermError as e:
                    return f'<span class="link-error">{escape(e.message)}</span>'
            return f'<a href="{flask.url_for("view", what=self.view_key.lower(), id=arg["id"])}">{escape(item.string)}</a>'
        if self.multiple:
            return ''.join((
                '<ul>',
                *(f'<li>{mklink(x)}</li>' for x in value),
                '</ul>',
            ))
        else:
            return mklink(value)
