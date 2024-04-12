"""Abstract (UI-agnostic) form definitions"""

import enum
from typing import ClassVar
from .. import utils
from . import lib
from .lib import Widget

__all__ = [
    'Widget',
    'FormTag',
    'Form',
]


class FormTag(enum.Enum):
    SEARCH = '"search" action'
    NEW = '"new" action'
    EDIT = '"edit" action'
    VIEW = '"view" action'


class Form(lib.Form):
    """Use utils.get_name"""
    form_name: ClassVar[str]

    def __init_subclass__(cls, **kwargs):
        """Set cls.form_name"""
        cls.form_name = cls.__name__.replace('Form', '')
        super().__init_subclass__(**kwargs)  # noqa -- it might accept kwargs later

    def get_name(self, name):
        """redirect to utils.get_name inserting a form-specific prefix"""
        if isinstance(self.tag, FormTag):
            items = ('form', self.form_name, self.tag.name, name)
        else:
            items = ('form', self.form_name, name)
        return utils.get_name('::'.join(items))
