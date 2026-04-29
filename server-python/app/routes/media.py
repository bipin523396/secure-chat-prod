import datetime
from flask import Blueprint, request, jsonify, send_file, Response
from app.models.db import fs, media_files_collection
from app.utils.jwt_utils import token_required
from bson import ObjectId
import io

media_bp = Blueprint('media', __name__)

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
    
    # Save to GridFS
    file_id = fs.put(
        file_bytes,
        filename=file.filename,
        content_type=content_type,
        uploader_id=ObjectId(current_user_id)
    )
    
    # Save metadata record
    media_files_collection.insert_one({
        'file_id': file_id,
        'uploader_id': ObjectId(current_user_id),
        'original_name': file.filename,
        'file_type': content_type,
        'size': len(file_bytes),
        'created_at': datetime.datetime.utcnow()
    })
    
    return jsonify({
        'msg': 'File uploaded successfully',
        'file_id': str(file_id),
        'file_url': f"/api/media/download/{file_id}",
        'file_name': file.filename,
        'file_type': content_type
    }), 201

@media_bp.route('/download/<file_id>', methods=['GET'])
@token_required
def download_file(current_user_id, file_id):
    try:
        grid_out = fs.get(ObjectId(file_id))
        content_type = grid_out.content_type if hasattr(grid_out, 'content_type') and grid_out.content_type else 'application/octet-stream'
        data = grid_out.read()
        
        # Serve inline for images so browser can display them directly
        is_image = content_type.startswith('image/')
        
        return Response(
            data,
            mimetype=content_type,
            headers={
                'Content-Disposition': f'{"inline" if is_image else "attachment"}; filename="{grid_out.filename}"',
                'Content-Length': str(len(data)),
                'Cache-Control': 'private, max-age=3600'
            }
        )
    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({'error': 'File not found'}), 404
