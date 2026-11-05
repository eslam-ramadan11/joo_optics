"""Serve simple static UI files from the repository `admin/` folder.

This allows visiting `/admin/admin.html` through the Flask app so the
browser-origin is `http://localhost:5000` and CORS works for API calls.
"""
import os
from flask import Blueprint, send_from_directory, current_app

bp = Blueprint('static_ui', __name__)


@bp.route('/admin/')
def admin_index():
    admin_dir = os.path.abspath(os.path.join(current_app.root_path, '..', 'admin'))
    return send_from_directory(admin_dir, 'admin.html')


@bp.route('/admin/<path:filename>')
def serve_admin_file(filename):
    admin_dir = os.path.abspath(os.path.join(current_app.root_path, '..', 'admin'))
    return send_from_directory(admin_dir, filename)
