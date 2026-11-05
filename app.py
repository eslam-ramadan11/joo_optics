"""WSGI/dev entry point.

SECURITY FIX: debug mode is no longer hardcoded to True. Flask's debug
mode enables the interactive Werkzeug debugger, which allows arbitrary
Python code execution from the browser if an unhandled exception occurs
and an attacker can reach it - this must never be on in production.

Debug is now controlled by the FLASK_DEBUG environment variable and
defaults to OFF. For actual production deployment, don't use `python
app.py` / app.run() at all - run behind a real WSGI server, e.g.:

    gunicorn -w 4 -b 0.0.0.0:8000 "wsgi:app"
"""
import os

from app import create_app

app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    # Only bind to localhost by default; set FLASK_RUN_HOST explicitly to expose it.
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', '5000'))
    app.run(debug=debug, host=host, port=port)
