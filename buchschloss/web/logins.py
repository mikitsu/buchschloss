"""Manage login sessions"""

import secrets
import flask

from .. import core


# TODO: periodically clean this
sessions = {}


def login(username, password):
    token = secrets.token_hex()
    sessions[token] = core.login(username, password)
    flask.session['lc'] = token


def logout():
    try:
        del sessions[flask.session['lc']]
        del flask.session['lc']
    except KeyError:
        pass


def lc_kwargs():
    return {'login_context': get_lc()}


def get_lc():
    return sessions.get(flask.session.get('lc'), core.guest_lc)
