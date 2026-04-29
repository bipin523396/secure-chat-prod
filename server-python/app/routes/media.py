import os
import datetime
from flask import Blueprint, request, jsonify, send_file
from app.models.db import db
from app.utils.jwt_utils import token_required
import uuid

media_bp = Blueprint('media', __name__)

# Local upload directory (server-python/uploads/)
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads"
)
os.makedirs(UPLOAD_DIR, exist_ok=True)


@media_bp.route('/upload', methods=['POST'])
@token_required
def upload_file(current_user_id):
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    content_type = file.content_type or 'application/octet-stream'
    file_bytes = file.read()

    file_uuid = str(uuid.uuid4())
    # Keep original filename but prefix with UUID to avoid collisions
    safe_name = f"{file_uuid}_{file.filename}"
    local_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(local_path, 'wb') as f:
        f.write(file_bytes)

    # Store metadata in Firestore
    db.collection("media_files").document(file_uuid).set({
        'file_id': file_uuid,
        'uploader_id': current_user_id,
        'original_name': file.filename,
        'file_type': content_type,
        'size': len(file_bytes),
        'local_path': local_path,
        'created_at': datetime.datetime.utcnow()
    })

    return jsonify({
        'msg': 'File uploaded successfully',
        'file_id': file_uuid,
        'file_url': f"/api/media/download/{file_uuid}",
        'file_name': file.filename,
        'file_type': content_type
    }), 201


@media_bp.route('/download/<file_id>', methods=['GET'])
@token_required
def download_file(current_user_id, file_id):
    try:
        media_doc = db.collection("media_files").document(file_id).get()
        if not media_doc.exists:
            return jsonify({'error': 'File not found'}), 404

        metadata = media_doc.to_dict()
        local_path = metadata.get('local_path')

        if not local_path or not os.path.exists(local_path):
            return jsonify({'error': 'File not found on disk'}), 404

        content_type = metadata.get('file_type', 'application/octet-stream')
        is_image = content_type.startswith('image/')

        return send_file(
            local_path,
            mimetype=content_type,
            as_attachment=not is_image,
            download_name=metadata.get('original_name', 'file')
        )
    except Exception as e:
        print(f"[Media] Download error: {e}")
        return jsonify({'error': str(e)}), 500
