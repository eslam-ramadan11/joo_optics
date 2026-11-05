"""Prescription service for handling prescription uploads and management."""
import os
import uuid
from typing import List, Optional

from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from flask import current_app

from app.extensions import db
from app.models.models import Prescription

_IMAGE_SIGNATURES = {
    b'\xff\xd8\xff': 'jpg',
    b'\x89PNG\r\n\x1a\n': 'png',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
    b'%PDF': 'pdf',
}


class PrescriptionService:
    """Service layer for prescription file management and storage."""

    @staticmethod
    def allowed_file(filename: str) -> bool:
        """Check if file extension is allowed."""
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        return ext in current_app.config.get('ALLOWED_PRESCRIPTION_EXTENSIONS', set())

    @staticmethod
    def _sniff_type(file_storage: FileStorage) -> Optional[str]:
        header = file_storage.stream.read(16)
        file_storage.stream.seek(0)
        for signature, kind in _IMAGE_SIGNATURES.items():
            if header.startswith(signature):
                return kind
        return None

    @staticmethod
    def save_file(file_storage: FileStorage) -> str:
        """Save uploaded prescription file to disk.

        SECURITY:
        - Filename is prefixed with a random uuid so two users uploading a
          file with the same original name can never collide/overwrite each
          other's (sensitive, medical) file.
        - File content is checked against known magic bytes so a renamed
          non-image/non-pdf file can't slip past the extension check.

        Raises:
            ValueError: If file extension/content is not allowed.
        """
        filename = secure_filename(file_storage.filename)
        if not filename or not PrescriptionService.allowed_file(filename):
            raise ValueError('invalid file extension')

        if PrescriptionService._sniff_type(file_storage) is None:
            raise ValueError('file content does not match an allowed type')

        upload_folder = current_app.config['PRESCRIPTIONS_UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)

        unique_name = f"{uuid.uuid4().hex}_{filename}"
        dest = os.path.join(upload_folder, unique_name)
        file_storage.save(dest)
        return dest

    @staticmethod
    def create_prescription(
        user_id: int,
        file_path: str,
        sph_r: float,
        cyl_r: float,
        axis_r: int,
        sph_l: float,
        cyl_l: float,
        axis_l: int
    ) -> Prescription:
        """Create a new prescription record."""
        p = Prescription(
            user_id=user_id,
            image_file=file_path,
            sph_r=sph_r,
            cyl_r=cyl_r,
            axis_r=axis_r,
            sph_l=sph_l,
            cyl_l=cyl_l,
            axis_l=axis_l,
        )
        db.session.add(p)
        db.session.commit()
        return p

    @staticmethod
    def list_prescriptions(user_id: Optional[int] = None) -> List[Prescription]:
        """List prescriptions, optionally filtered by user."""
        q = Prescription.query
        if user_id:
            q = q.filter(Prescription.user_id == user_id)
        return q.order_by(Prescription.uploaded_at.desc()).all()

    @staticmethod
    def get_prescription(prescription_id: int) -> Optional[Prescription]:
        """Retrieve a prescription by ID."""
        return Prescription.query.get(prescription_id)

    @staticmethod
    def delete_prescription(prescription: Prescription) -> None:
        """Delete a prescription and its associated file."""
        try:
            candidates = []
            if prescription.image_file:
                if os.path.isabs(prescription.image_file):
                    candidates.append(prescription.image_file)
                else:
                    candidates.append(os.path.abspath(prescription.image_file))
                    candidates.append(os.path.abspath(os.path.join(
                        current_app.root_path, '..', prescription.image_file
                    )))
                upload_folder = current_app.config.get('PRESCRIPTIONS_UPLOAD_FOLDER')
                if upload_folder:
                    candidates.append(os.path.join(
                        upload_folder, os.path.basename(prescription.image_file)
                    ))
            for candidate in dict.fromkeys(candidates):
                if os.path.isfile(candidate):
                    os.remove(candidate)
                    break
        except OSError:
            current_app.logger.warning('failed to remove prescription file %s', prescription.image_file)
        db.session.delete(prescription)
        db.session.commit()
