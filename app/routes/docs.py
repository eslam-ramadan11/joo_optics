from flask import Blueprint, send_file, current_app
import os

bp = Blueprint('docs', __name__)


@bp.route('/openapi.json')
def openapi_json():
    return send_file(os.path.join(current_app.root_path, '..', 'openapi.json'))
