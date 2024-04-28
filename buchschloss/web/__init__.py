"""main web entry point"""

import wsgiref.simple_server

from .. import config
from . import app


def start():
    with wsgiref.simple_server.make_server(config.web.host, config.web.port, app.app) as server:
        server.serve_forever()
