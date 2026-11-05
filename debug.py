#!/usr/bin/env python
"""Debug script to test imports."""
import os
import sys

# This is a local debugging script, never a production entry point (that's
# app.py, run via gunicorn, which deliberately has no such default) - so it
# gets the same convenience default run_server.py already sets, letting the
# app factory's insecure-secret-key guard know this is a safe dev context.
os.environ.setdefault('FLASK_ENV', 'development')

print("Python version:", sys.version)
print("Attempting to import Flask...")
import flask
print("Flask imported successfully")

print("Attempting to import app...")
from app import create_app
print("App imported successfully")

print("Creating app...")
app = create_app()
print("App created successfully")
print(f"App routes: {len(app.url_map._rules)}")
