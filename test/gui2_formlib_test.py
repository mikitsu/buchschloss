"""Test gui2.formlib"""
import types
import runpy
import os

# giant dance to prevent importing buchschloss.gui2 (uses tk)
# TODO: rewrite gui2 so that it doesn't start on import
formlib = types.SimpleNamespace(**runpy.run_path(
    os.path.join(os.path.dirname(__file__), '..', 'buchschloss', 'gui2', 'formlib.py')))


def test_merge():
    class NotAForm:
        pass

    class NotBForm:
        pass

    class NotDerivedForm(NotAForm):
        pass

    class AForm(formlib.Form):
        all_widgets = {
            'field-1': 'widget class (AForm)',
            'field-2': ('widget class (AForm)', {'kwargs': 'AForm'}),
            'field-3': {
                'tag-1': 'widget class (AForm)',
                'tag-2': None,
                None: ('widget class (AForm)', {'kwargs': 'AForm'}),
            }
        }

    class BForm(NotDerivedForm, formlib.Form, NotBForm):
        all_widgets = {
            'field-1': ('widget class (BForm)', {'kwargs': 'BForm'}),
            'field-4': 'widget class (BForm)',
            'field-2': None,
        }

    class DerivedForm1(NotAForm, AForm):
        all_widgets = {
            'field-5': 'widget class (DerivedForm1)',
            'field-2': 'widget class (DerivedForm1)',
        }

    class DerivedForm2(BForm, DerivedForm1):
        all_widgets = {
            'field-6': 'widget class (DerivedForm2)',
        }

    assert AForm.all_widgets == {
        'field-1': {None: ('widget class (AForm)', {})},
        'field-2': {None: ('widget class (AForm)', {'kwargs': 'AForm'})},
        'field-3': {
                'tag-1': ('widget class (AForm)', {}),
                'tag-2': None,
                None: ('widget class (AForm)', {'kwargs': 'AForm'}),
            }
    }
    assert DerivedForm1.all_widgets == {
        'field-1': {None: ('widget class (AForm)', {})},
        'field-2': {None: ('widget class (DerivedForm1)', {})},
        'field-3': {
            'tag-1': ('widget class (AForm)', {}),
            'tag-2': None,
            None: ('widget class (AForm)', {'kwargs': 'AForm'}),
        },
        'field-5': {None: ('widget class (DerivedForm1)', {})},
    }
    assert DerivedForm2.all_widgets == {
        'field-1': {None: ('widget class (BForm)', {'kwargs': 'BForm'})},
        'field-2': {None: None},
        'field-3': {
            'tag-1': ('widget class (AForm)', {}),
            'tag-2': None,
            None: ('widget class (AForm)', {'kwargs': 'AForm'}),
        },
        'field-4': {None: ('widget class (BForm)', {})},
        'field-5': {None: ('widget class (DerivedForm1)', {})},
        'field-6': {None: ('widget class (DerivedForm2)', {})},
    }
