import os
import datetime
import tempfile
from flask import Blueprint, request, jsonify, send_file
from backend_app.models.db import db, bucket
from backend_app.utils.jwt_utils import token_required
import uuid

media_bp = Blueprint('media', __name__)

UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads"
)
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _storage_path(file_uuid, filename):
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
    return f"chat_media/{file_uuid}/{safe_name or 'file'}"


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
    storage_path = _storage_path(file_uuid, file.filename)
    local_path = os.path.join(UPLOAD_DIR, f"{file_uuid}_{file.filename}")

    stored_in_cloud = False
    if bucket:
        try:
            blob = bucket.blob(storage_path)
            blob.upload_from_string(file_bytes, content_type=content_type)
            stored_in_cloud = True
        except Exception as e:
            print(f"[Media] Firebase upload failed, using local disk: {e}")

    if not stored_in_cloud:
        with open(local_path, 'wb') as f:
            f.write(file_bytes)

    db.collection("media_files").document(file_uuid).set({
        'file_id': file_uuid,
        'uploader_id': current_user_id,
        'original_name': file.filename,
        'file_type': content_type,
        'size': len(file_bytes),
        'storage_path': storage_path if stored_in_cloud else None,
        'local_path': local_path if not stored_in_cloud else None,
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
def download_file(file_id):
    try:
        media_doc = db.collection("media_files").document(file_id).get()
        if not media_doc.exists:
            return jsonify({'error': 'File not found'}), 404

        metadata = media_doc.to_dict()
        content_type = metadata.get('file_type', 'application/octet-stream')
        is_image = content_type.startswith('image/')
        download_name = metadata.get('original_name', 'file')

        storage_path = metadata.get('storage_path')
        if storage_path and bucket:
            blob = bucket.blob(storage_path)
            if blob.exists():
                tmp = tempfile.NamedTemporaryFile(delete=False)
                blob.download_to_filename(tmp.name)
                return send_file(
                    tmp.name,
                    mimetype=content_type,
                    as_attachment=not is_image,
                    download_name=download_name
                )

        stored_path = metadata.get('local_path')
        safe_name = f"{file_id}_{metadata.get('original_name')}"
        reconstructed_path = os.path.join(UPLOAD_DIR, safe_name)
        local_path = stored_path if stored_path and os.path.exists(stored_path) else reconstructed_path

        if not os.path.exists(local_path):
            return jsonify({'error': 'File not found on disk'}), 404

        return send_file(
            local_path,
            mimetype=content_type,
            as_attachment=not is_image,
            download_name=download_name
        )
    except Exception as e:
        print(f"[Media] Download error: {e}")
        return jsonify({'error': str(e)}), 500
