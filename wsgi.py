"""Production WSGI entry point.

Local development still uses ``python app.py``. Linux hosts that need a WSGI
server can point Gunicorn or uWSGI at ``wsgi:app``.
"""

from app import create_app

app = create_app()

# Also expose the conventional name used by some WSGI hosts.
application = app
