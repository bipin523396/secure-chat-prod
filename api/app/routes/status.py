import datetime
from flask import Blueprint, request, jsonify
from app.models.db import db
from app.utils.jwt_utils import token_required
import os

status_bp = Blueprint('status', __name__)

@status_bp.route('/upload', methods=['POST'])
@token_required
def upload_status(current_user_id):
    content = request.json.get('content') # Can be text or a URL to media
    status_type = request.json.get('type', 'text') # 'text', 'image', 'video'
    
    status_data = {
        'user_id': current_user_id,
        'content': content,
        'type': status_type,
        'created_at': datetime.datetime.utcnow(),
        'expires_at': datetime.datetime.utcnow() + datetime.timedelta(hours=24),
        'seen_by': []
    }
    
    db.collection("status").add(status_data)
    return jsonify({'msg': 'Status uploaded'}), 201

@status_bp.route('/list', methods=['GET'])
@token_required
def get_statuses(current_user_id):
    now = datetime.datetime.utcnow()
    
    # Get friends first to only show their status
    friends_docs = db.collection("friends").where("user_id", "==", current_user_id).stream()
    friend_ids = [f.to_dict()['friend_id'] for f in friends_docs]
    friend_ids.append(current_user_id) # Include own status
    
    # Firestore has limit on 'in' query (max 10), but for this clone we'll keep it simple
    # or just fetch all and filter in memory if needed.
    
    results = []
    # Fetch active statuses
    docs = db.collection("status").where("expires_at", ">", now).stream()
    
    grouped = {}
    for doc in docs:
        data = doc.to_dict()
        uid = data['user_id']
        if uid not in friend_ids: continue
        
        if uid not in grouped:
            user_doc = db.collection("users").document(uid).get()
            username = user_doc.to_dict()['username'] if user_doc.exists else "Unknown"
            grouped[uid] = {
                'user_id': uid,
                'username': username,
                'statuses': []
            }
        
        data['id'] = doc.id
        data['created_at'] = data['created_at'].isoformat()
        data['expires_at'] = data['expires_at'].isoformat()
        grouped[uid]['statuses'].append(data)
        
    return jsonify(list(grouped.values())), 200

@status_bp.route('/seen', methods=['POST'])
@token_required
def mark_seen(current_user_id):
    status_id = request.json.get('status_id')
    status_ref = db.collection("status").document(status_id)
    status_doc = status_ref.get()
    
    if status_doc.exists:
        data = status_doc.to_dict()
        if current_user_id not in data.get('seen_by', []):
            status_ref.update({
                'seen_by': firestore.ArrayUnion([current_user_id])
            })
    return jsonify({'msg': 'Marked as seen'}), 200
