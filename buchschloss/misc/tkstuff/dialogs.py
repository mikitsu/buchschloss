"""An extension to tkinter.simpledialog"""

import tkinter as tk
import tkinter.simpledialog as tk_dia
import misc.tkstuff as mtk
import misc.tkstuff.forms as mtkf


class UserExitedDialog(Exception):
    """The User exited the dialog without selecting an option"""


class ResultlessDialogMixIn:
    """remove the `self.result = None` set in tkinter.simpledialog.Dialog.__init__"""
    def body(self, master):
        # this doesn't really belong here, but, short of rewriting the
        # whole __init__ method, ther is no other way to do this
        del self.result
        return super().body(master)


class UserExitDialogMixIn(ResultlessDialogMixIn):
    """set `result` to UserExitedDialog when the user exits the dialog
        without selecting an option e.g. by closing the window

        raising would happen in a tkinter thread and not be propagated"""
    def cancel(self, event=None):
        super().cancel(event=event)
        if not hasattr(self, 'result'):
            self.result = UserExitedDialog()


class AskableDialogMixIn:
    """add an `ask` method that allows getting the result
        without manual creation of a dialog

        If the dialog has an instance of UserExitedDialog as result,
            it is raised"""
    @classmethod
    def ask(cls, *args, **kwargs):
        """Create a dialog with the specified arguements and return it's result"""
        dia = cls(*args, **kwargs)
        if isinstance(dia.result, UserExitedDialog):
            raise dia.result
        return dia.result


class ExtendedDialog(AskableDialogMixIn, UserExitDialogMixIn, tk_dia.Dialog):
    """Combine AskaleDialogMixIn and UserExitDialogMixIn with
        tkinter.simpledialog.Dialog"""


class FormDialog(ExtendedDialog):
    """A dialog for forms"""
    # note: some methods call their super() version
    # even if it does nothing. This is to prevent bugs
    # caused by accidentally not putting it there
    # when bahaviour is added
    
    def __init__(self, parent, form, title=None):
        """Create a new FormDialog

            `form` is a misc.tkstuff.forms.Form object that is used to
                create a widget to use in the dialog
            `parent` and `title` are passed"""
        self.form_onsubmit = form._Form__formwidget_options.get('onsubmit')
        self.form = form
        super().__init__(parent, title=title)

    def body(self, master):
        """Create and .pack the form. Called by tkinter.simpledialog.Dialog.__init__"""
        self.form_widget = self.form(master, onsubmit=self.ok)
        self.form_widget.pack()
        return super().body(master)

    def buttonbox(self):
        """Buttons are handled by the form"""
        pass

    def apply(self):
        """Put the form's data into `self.result`"""
        if self.form_onsubmit is not None:
            self.form_onsubmit(self.form_widget.data)
        self.result = self.form_widget.data
        return super().apply()


class WidgetDialog(ExtendedDialog):
    """A dialog for getting input from any widget

        The dialog will offer the final data in `.result`.
        If the widget has a `.validate()` method, it will
        be used to ensure validity of the entered data and,
        if applicable, convert the result to the desired format.
        The method is expected to return two items:
            1. a boolean indicating whether the data is valid
            2. the data, if valid, otherwise any item
        """
    # note: some methods call their super() version
    # even if it does nothing. This is to prevent bugs
    # caused by accidentally not putting it there
    # when bahaviour is added
    
    def __init__(self, parent, widget, widget_kw={},
                 title=None, getter=None, text=None):
        """Create a new WidgetDialog

            `widget` is the widget class
            `widegt_kw` are keyword arguments forthe widget.
                Positional arguments may be provided under the key '*args'
            `getter` is the name ofthe method that gets input from the
                widget. If it is one of the defaults supported by
                misc.tkstuff.get_getter (currently 'get' and 'curselection'),
                it must not be provided
            `text` is an optional text to be displayed above `widget` in a Label
                If you need additional configuration (e.g. position, font),
                consider using a misc.tkstuff.LabeledWidget
            `parent` and `title` are passed to tkinter.simpledialog.Dialog
            """
        self.widget_cls = widget
        self.widget_kw = widget_kw
        self.getter = mtk.get_getter(widget, getter)
        self.text = text
        super().__init__(parent, title)

    def body(self, master):
        """Create the Dialog body. called by tkinter.simpledialog.Dialog.__init__"""
        if self.text is not None:
            tk.Label(master, text=self.text).pack()
        self.widget = self.widget_cls(master,
                                      *self.widget_kw.pop('*args', ()),
                                      **self.widget_kw)
        self.widget.pack()
        return super().body(master)

    def validate(self):
        """Try validation of the data with the widget's `.validate()` method""" 
        super().validate()
        try:
            validator = self.widget.validate
        except AttributeError:
            return True
        else:
            v, self.result = validator()
            return v

    def apply(self):
        if not hasattr(self, 'result'):
            self.result = self.getter(self.widget)
        return super().apply()


