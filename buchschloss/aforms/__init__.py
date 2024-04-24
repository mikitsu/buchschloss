"""Abstract (UI-agnostic) form definitions"""

from .defs import FormTag, AForm
from .lib import Widget, Form

__all__ = [
    'Widget',
    'FormTag',
    'Form',
]


def instantiate(impl_cls):
    return {form_cls.__name__: type(form_cls.__name__, (form_cls, impl_cls), {'all_widgets': {}})
            for form_cls in AForm.leaf_children}
