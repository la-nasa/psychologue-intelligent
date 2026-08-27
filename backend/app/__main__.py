from wsgiref.simple_server import make_server

from .config import Settings
from .http import application

if __name__ == "__main__":
    settings = Settings.from_env()
    with make_server("127.0.0.1", 8000, application(settings)) as server:
        server.serve_forever()

