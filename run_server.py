#!/usr/bin/env python
"""Run Flask development server.

SECURITY FIX: debug was hardcoded to True. Now controlled by FLASK_DEBUG
env var (default off) - same fix as app.py. Never run with debug=True
where the server is reachable by anyone other than you.
"""
import os
os.environ['FLASK_APP'] = 'app:create_app'
os.environ.setdefault('FLASK_ENV', 'development')

from app import create_app

if __name__ == '__main__':
    app = create_app()
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', '5000'))
    print(f"Starting server on http://{host}:{port} (debug={debug})")
    app.run(debug=debug, host=host, port=port)
