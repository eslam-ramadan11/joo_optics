"""Prescription management routes for uploading and managing prescription images."""
import os
from typing import Tuple
from flask import Blueprint, request, current_app, g, send_file
from marshmallow import ValidationError
from werkzeug.utils import secure_filename

from app.middleware.auth import login_required
from app.models.models import OrderItem
from app.services.prescription_service import PrescriptionService
from app.schemas.prescription_schema import PrescriptionSchema
from app.utils.response import api_response
from app.utils.limiter import limiter

bp = Blueprint('prescriptions', __name__)
prescription_schema = PrescriptionSchema()
prescriptions_schema = PrescriptionSchema(many=True)


@bp.route('', methods=['POST'])
@login_required
@limiter.limit('30 per minute')
def upload_prescription() -> Tuple[dict, int]:
    """Upload a prescription image for the current user.
    
    Form Data:
        - file (FileStorage): Prescription image file
        - sph_r (float): Sphere right eye
        - cyl_r (float): Cylinder right eye
        - axis_r (int): Axis right eye
        - sph_l (float): Sphere left eye
        - cyl_l (float): Cylinder left eye
        - axis_l (int): Axis left eye
    
    Returns:
        tuple: JSON response with prescription details or error message.
    """
    if 'file' not in request.files:
        return api_response(False, {}, 'file is required', 400)
    
    file = request.files['file']
    if file.filename == '':
        return api_response(False, {}, 'no selected file', 400)

    # File size validation
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    max_size = current_app.config.get('MAX_CONTENT_LENGTH', 5 * 1024 * 1024)
    if size > max_size:
        return api_response(False, {}, f'file size exceeds {max_size} bytes', 413)

    # File extension validation
    filename = secure_filename(file.filename)
    if not filename or '.' not in filename:
        return api_response(False, {}, 'invalid file name', 400)
    
    if not PrescriptionService.allowed_file(filename):
        allowed = ', '.join(current_app.config.get('ALLOWED_PRESCRIPTION_EXTENSIONS', set()))
        return api_response(False, {}, f'invalid file type. allowed: {allowed}', 400)

    # Form field validation
    try:
        payload = request.form.to_dict()
        data = prescription_schema.load(payload)
    except ValidationError as e:
        return api_response(False, {}, e.messages, 400)
    except Exception as e:
        current_app.logger.error(f'Unexpected error validating prescription payload: {e}')
        return api_response(False, {}, 'Invalid request data.', 400)

    # File save with security
    try:
        dest = PrescriptionService.save_file(file)
    except ValueError as e:
        return api_response(False, {}, str(e), 400)
    except Exception as e:
        current_app.logger.error(f'Prescription file save failed: {e}')
        return api_response(False, {}, 'File upload failed. Please try again.', 500)

    user = g.current_user
    try:
        p = PrescriptionService.create_prescription(
            user_id=user.id,
            file_path=dest,
            sph_r=float(data['sph_r']),
            cyl_r=float(data['cyl_r']),
            axis_r=int(data['axis_r']),
            sph_l=float(data['sph_l']),
            cyl_l=float(data['cyl_l']),
            axis_l=int(data['axis_l']),
        )
        return api_response(True, prescription_schema.dump(p), status_code=201)
    except Exception as e:
        current_app.logger.error(f'Error creating prescription for user {user.id}: {e}')
        return api_response(False, {}, 'An error occurred while saving the prescription.', 500)


@bp.route('', methods=['GET'])
@login_required
@limiter.limit('30 per minute')
def list_prescriptions() -> Tuple[dict, int]:
    """List all prescriptions for the current user.
    
    Returns:
        tuple: JSON response with prescriptions list.
    """
    user = g.current_user
    try:
        items = PrescriptionService.list_prescriptions(user_id=user.id)
        return api_response(True, prescriptions_schema.dump(items))
    except Exception as e:
        current_app.logger.error(f'Error listing prescriptions for user {user.id}: {e}')
        return api_response(False, {}, 'An error occurred while loading your prescriptions.', 500)


@bp.route('/<int:prescription_id>', methods=['GET'])
@login_required
@limiter.limit('30 per minute')
def get_prescription(prescription_id: int) -> Tuple[dict, int]:
    """Retrieve a specific prescription.
    
    Args:
        prescription_id: The prescription ID.
    
    Returns:
        tuple: JSON response with prescription details or error message.
    """
    p = PrescriptionService.get_prescription(prescription_id)
    if not p:
        return api_response(False, {}, 'Prescription not found', 404)
    
    user = g.current_user
    if p.user_id != user.id and not user.is_admin:
        return api_response(False, {}, 'Forbidden', 403)
    
    return api_response(True, prescription_schema.dump(p))


@bp.route('/<int:prescription_id>', methods=['DELETE'])
@login_required
@limiter.limit('30 per minute')
def delete_prescription(prescription_id: int) -> Tuple[dict, int]:
    """Delete a prescription (own or admin).
    
    Args:
        prescription_id: The prescription ID.
    
    Returns:
        tuple: JSON response with success or error message.
    """
    p = PrescriptionService.get_prescription(prescription_id)
    if not p:
        return api_response(False, {}, 'Prescription not found', 404)
    
    user = g.current_user
    if p.user_id != user.id and not user.is_admin:
        return api_response(False, {}, 'Forbidden', 403)
    
    # Lenses are made from this prescription - deleting it would silently
    # detach it from the order (prescription_id becomes NULL) and the shop
    # would be left with a lens order but no prescription to make it from.
    if OrderItem.query.filter_by(prescription_id=p.id).first():
        return api_response(
            False, {},
            'This prescription is attached to an existing order and cannot be deleted.',
            409,
        )

    try:
        PrescriptionService.delete_prescription(p)
        return api_response(True, {}, 'Prescription deleted')
    except Exception as e:
        current_app.logger.error(f'Error deleting prescription {p.id}: {e}')
        return api_response(False, {}, 'An error occurred while deleting the prescription.', 500)


def _resolve_prescription_path(stored_path):
    """Find a prescription's file on disk and return an absolute path (or None).

    Older rows were saved with a path relative to wherever the server was
    started from, so try that first, then the project folder, then the same
    file name inside the configured upload folder (covers a moved project).
    """
    if not stored_path:
        return None

    candidates = []
    if os.path.isabs(stored_path):
        candidates.append(stored_path)
    else:
        candidates.append(os.path.abspath(stored_path))
        project_root = os.path.dirname(current_app.root_path)
        candidates.append(os.path.abspath(os.path.join(project_root, stored_path)))

    upload_folder = current_app.config.get('PRESCRIPTIONS_UPLOAD_FOLDER')
    if upload_folder:
        candidates.append(os.path.abspath(os.path.join(upload_folder, os.path.basename(stored_path))))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


@bp.route('/<int:prescription_id>/file', methods=['GET'])
@login_required
@limiter.limit('30 per minute')
def download_prescription_file(prescription_id: int):
    """Download a prescription file for the owner or admin."""
    p = PrescriptionService.get_prescription(prescription_id)
    if not p:
        return api_response(False, {}, 'Prescription not found', 404)

    user = g.current_user
    if p.user_id != user.id and not user.is_admin:
        return api_response(False, {}, 'Forbidden', 403)

    file_path = _resolve_prescription_path(p.image_file)
    if not file_path:
        current_app.logger.error(
            f'Prescription {p.id}: file not found on disk (stored path: {p.image_file!r})'
        )
        return api_response(False, {}, 'Prescription file not found', 404)

    # Always hand send_file an ABSOLUTE path: a relative one is resolved
    # against the app/ package folder (not the folder the server was started
    # from), which is why files saved with a relative upload folder could
    # never be opened - not by the customer and not from the admin panel.
    return send_file(file_path)
