"""Form handling"""

import markupsafe

from .. import aforms
from . import widgets


class FormTmpl(aforms.Form):
    def make_widget(self, name, w_elem, w_args, w_kwargs):
        return getattr(widgets, w_elem.value)(self, name, *w_args, **w_kwargs)

    def render(self, data):
        return markupsafe.Markup(''.join((
            '<form method="POST">',
            *(w.render(data) for w in self.widget_dict.values()),
            '<input type="submit">' if self.tag is not aforms.FormTag.VIEW else '',
            '</form>'
        )))

    def validate(self, data):
        errs = []
        res = {}
        for k, w in self.widget_dict.items():
            try:
                res[k] = w.validate(data)
            except widgets.ValidationError as e:
                errs += e.args
        if errs:
            raise widgets.ValidationError(*errs)
        return res


def get(name):
    return instances[name.title() + 'Form']


def render(name, tag, data={}):
    return get(name)(tag).render(data)


def validate(name, tag, data):
    return get(name)(tag).validate(data)


instances = aforms.instantiate(FormTmpl)
