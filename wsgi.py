"""Production WSGI entry point.

Use this with gunicorn:

    gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app

(`app:app` does NOT work: the `app/` package shadows `app.py`, and the
package has no attribute called `app`.)
"""
from app import create_app

app = create_app()
