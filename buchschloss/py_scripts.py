"""Python scripts"""
import os
import base64
import logging
import requests

try:
    from cryptography import fernet
except ImportError:
    fernet = None

from . import config

__all__ = ['local_backup', 'http_backup']


def argument_sink(f):
    """sink the ``callbacks`` and ``login_context`` arguments passed to scripts"""
    def wrapper(callbacks, login_context):  # noqa
        return f()
    return wrapper


@argument_sink
def local_backup():
    """Local backups.

    Move all existing <DB name>.N files one number up,
    deleting the largest if maximum depth is reached
    Then copy the current database to <DB name>.1,
    encrypting if encryption is enabled
    """
    conf = config.scripts.python.local_backup

    number_name = lambda n: '.'.join((config.core.database_name, str(n)))  # noqa
    try:
        os.remove(number_name(conf.depth))
    except FileNotFoundError:
        pass
    for f in range(conf.depth, 1, -1):
        try:
            os.rename(number_name(f - 1), number_name(f))
        except FileNotFoundError:
            pass

    data = get_database_bytes(conf.secret_key)
    with open(number_name(1), 'wb') as f:
        f.write(data)


def get_database_bytes(key):
    """get the contents of the database file, optionally encrypted with the given key"""
    with open(config.core.database_name, 'rb') as f:
        plain = f.read()
    if key is None:
        return plain
    if fernet is None:
        raise RuntimeError('encryption requested, but no cryptography available')
    cipher = fernet.Fernet(base64.urlsafe_b64encode(key)).encrypt(plain)
    return base64.urlsafe_b64decode(cipher)


@argument_sink
def http_backup():
    """remote backups via HTTP"""
    conf = config.scripts.python.http_backup
    data = get_database_bytes(conf.secret_key)
    options: 'dict' = {}
    if conf.Basic_authentication.username:
        options['auth'] = (conf.Basic_authentication.username,
                           conf.Basic_authentication.password)
    options['data'] = conf.POST_authentication.mapping
    try:
        r = requests.post(conf.url, files={conf.file_name: data}, **options)
    except requests.RequestException as e:
        logging.error('exception during HTTP request: ' + str(e))
        return
    if r.status_code != 200:
        logging.error('received unexpected status code {} during HTTP backup'
                      .format(r.status_code))
