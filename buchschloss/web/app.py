"""Main application entry point"""

import werkzeug.datastructures
import flask
from flask import request

from .. import core, aforms, utils, config
from . import forms, logins, widgets

app = flask.Flask('buchschloss.web')
app.secret_key = config.web.secret_key
# TODO: implement
# any_ans = 'any("book", "person", "library", "member", "script")'
any_ans = 'any("book", "library")'


def render_tmpl(form, tmpl='base.html', **kwargs):
    return flask.render_template(tmpl, form=form, current_login=logins.get_lc(), logged_in=logins.get_lc() is not core.guest_lc, get_name=utils.get_name, **kwargs)


@app.route('/')
def index():
    return render_tmpl(None, 'index.html', actions=[('book', 'new')])


@app.route('/login', methods=('GET', 'POST'))
def login():
    msgs = []
    if request.method == 'POST':
        try:
            logins.login(request.form['name'], request.form['password'])
        except core.BuchSchlossBaseError as e:
            msgs = [('error', e.message)]
        else:
            return flask.redirect('/')
    return render_tmpl(forms.render('login', None), messages=msgs)


@app.route('/logout')
def logout():
    logins.logout()
    return flask.redirect('/')


@app.route('/view/<any("book", "person"):what>/<int:id>')
# TODO: implement
# @app.route('/view/<any("library", "member", "script"):what>/<id>')
@app.route('/view/<any("library", "member"):what>/<id>')
def view(id, what):
    try:
        data = getattr(core, what.title()).view_ns(id, **logins.lc_kwargs())
    except core.BuchSchlossBaseError as e:
        flask.flash(e.message, 'error')
        return flask.redirect('/')
    form = forms.render(what, aforms.FormTag.VIEW, data)
    return render_tmpl(form)


# TODO: this excludes (old) 10-digit ISBNs with X as checksum
# is that a problem?
@app.route('/api/ad-hoc/get-book-data/<int:isbn>')
def get_book_data(isbn):
    return utils.get_book_data(isbn)


@app.route(f'/new/<{any_ans}:what>', methods=('GET', 'POST'))
def new(what):
    msgs = []
    if request.method == 'POST':
        try:
            kwargs = forms.validate(what, aforms.FormTag.NEW, request.form)
            r = getattr(core, what.capitalize()).new(**request.form, **logins.lc_kwargs())
        except widgets.ValidationError as e:
            for msg in e.args:
               msgs.append(('error', msg))
        except core.BuchSchlossBaseError as e:
            msgs = [('error', e.message)]
        else:
            if what == 'book':
                flask.flash(utils.get_name('Book::new_id_{}', r), 'success')
            return flask.redirect('/')
    # We want form entries to override defaults
    values = werkzeug.datastructures.MultiDict(config.gui2.entry_defaults.get(what.title()).mapping | request.form.to_dict(flat=False))
    return render_tmpl(forms.render(what, aforms.FormTag.NEW, values), messages=msgs)
