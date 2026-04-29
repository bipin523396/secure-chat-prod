import datetime
from flask import Blueprint, request, jsonify
from app.models.db import db, users_collection, friend_requests_collection, friends_collection, blocked_users_collection
from app.utils.jwt_utils import token_required
from google.cloud import firestore

friends_bp = Blueprint('friends', __name__)

@friends_bp.route('/search', methods=['GET'])
@token_required
def search_users(current_user_id):
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify([])
        
    # Firestore doesn't support full regex or $nin easily. 
    # We'll fetch users and filter client-side for simplicity in this migration
    # In a production app, we would use a search index like Algolia
    
    users_ref = db.collection("users")
    # Prefix match as a workaround for search
    docs = users_ref.where("username", ">=", query).where("username", "<=", query + "\uf8ff").limit(20).stream()
    
    results = []
    for doc in docs:
        user = doc.to_dict()
        user_id = doc.id
        
        if user_id == current_user_id:
            continue
            
        # Check friendship status
        status = "none"
        
        # Check if friends
        friend_docs = list(db.collection("friends").where("user_id", "==", current_user_id).where("friend_id", "==", user_id).limit(1).stream())
        if friend_docs:
            status = "friend"
        else:
            # Check requests
            sent_req = list(db.collection("friend_requests").where("sender_id", "==", current_user_id).where("receiver_id", "==", user_id).where("status", "==", "pending").limit(1).stream())
            if sent_req:
                status = "request_sent"
            else:
                recv_req = list(db.collection("friend_requests").where("sender_id", "==", user_id).where("receiver_id", "==", current_user_id).where("status", "==", "pending").limit(1).stream())
                if recv_req:
                    status = "request_received"
                    
        results.append({
            'id': user_id,
            'username': user['username'],
            'profile_pic': user.get('profile_pic'),
            'status_message': user.get('status_message'),
            'status': status
        })
        
    return jsonify(results), 200

@friends_bp.route('/request', methods=['POST'])
@token_required
def send_friend_request(current_user_id):
    target_username = request.json.get('username')
    
    target_docs = list(db.collection("users").where("username", "==", target_username).limit(1).stream())
    if not target_docs:
        return jsonify({'error': 'User not found'}), 404
        
    target_id = target_docs[0].id
    
    if target_id == current_user_id:
        return jsonify({'error': 'Cannot add yourself'}), 400
        
    # Check if already friends
    friend_docs = list(db.collection("friends").where("user_id", "==", current_user_id).where("friend_id", "==", target_id).limit(1).stream())
    if friend_docs:
        return jsonify({'error': 'Already friends'}), 400
        
    # Check if request already exists
    req_docs = list(db.collection("friend_requests").where("sender_id", "==", current_user_id).where("receiver_id", "==", target_id).where("status", "==", "pending").limit(1).stream())
    if req_docs:
        return jsonify({'error': 'Request already sent'}), 400

    db.collection("friend_requests").add({
        'sender_id': current_user_id,
        'receiver_id': target_id,
        'status': 'pending',
        'created_at': datetime.datetime.utcnow()
    })
    
    return jsonify({'msg': 'Friend request sent'}), 201

@friends_bp.route('/requests/received', methods=['GET'])
@token_required
def get_received_requests(current_user_id):
    docs = db.collection("friend_requests").where("receiver_id", "==", current_user_id).where("status", "==", "pending").stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        sender_doc = db.collection("users").document(data['sender_id']).get()
        if sender_doc.exists:
            sender = sender_doc.to_dict()
            results.append({
                'request_id': doc.id,
                'sender_id': data['sender_id'],
                'sender_username': sender['username'],
                'created_at': data['created_at'].isoformat()
            })
    return jsonify(results), 200

@friends_bp.route('/requests/respond', methods=['POST'])
@token_required
def respond_request(current_user_id):
    req_id = request.json.get('request_id')
    action = request.json.get('action') # 'accept' or 'reject'
    
    req_ref = db.collection("friend_requests").document(req_id)
    req_doc = req_ref.get()
    
    if not req_doc.exists or req_doc.to_dict()['receiver_id'] != current_user_id:
        return jsonify({'error': 'Request not found'}), 404
        
    if action == 'accept':
        data = req_doc.to_dict()
        sender_id = data['sender_id']
        
        batch = db.batch()
        # Add to friends
        f1_ref = db.collection("friends").document()
        f2_ref = db.collection("friends").document()
        batch.set(f1_ref, {'user_id': current_user_id, 'friend_id': sender_id, 'is_archived': False, 'created_at': datetime.datetime.utcnow()})
        batch.set(f2_ref, {'user_id': sender_id, 'friend_id': current_user_id, 'is_archived': False, 'created_at': datetime.datetime.utcnow()})
        
        # Update request status
        batch.update(req_ref, {'status': 'accepted'})
        batch.commit()
        return jsonify({'msg': 'Friend added'}), 200
    else:
        req_ref.update({'status': 'rejected'})
        return jsonify({'msg': 'Request rejected'}), 200

@friends_bp.route('/archive', methods=['POST'])
@token_required
def toggle_archive(current_user_id):
    friend_id = request.json.get('friend_id')
    is_archived = request.json.get('archive', True)
    
    docs = db.collection("friends").where("user_id", "==", current_user_id).where("friend_id", "==", friend_id).limit(1).stream()
    for doc in docs:
        doc.reference.update({'is_archived': is_archived})
        return jsonify({'msg': 'Chat archived' if is_archived else 'Chat restored'}), 200
        
    return jsonify({'error': 'Friend not found'}), 404

@friends_bp.route('/list', methods=['GET'])
@token_required
def list_friends(current_user_id):
    try:
        friends_docs = db.collection("friends").where("user_id", "==", current_user_id).stream()
        
        results = []
        for f_doc in friends_docs:
            f_data = f_doc.to_dict()
            friend_id = f_data['friend_id']
            # Optionally filter out archived if requested
            if request.args.get('archived') == 'true':
                if not f_data.get('is_archived', False): continue
            else:
                if f_data.get('is_archived', False): continue

            user_doc = db.collection("users").document(friend_id).get()
            if user_doc.exists:
                user = user_doc.to_dict()
                results.append({
                    'id': user_doc.id,
                    'username': user['username'],
                    'identity_hash': user.get('identity_hash') or user.get('public_key', ''),
                    'profile_pic': user.get('profile_pic'),
                    'status_message': user.get('status_message'),
                    'is_online': user.get('is_online', False),
                    'is_archived': f_data.get('is_archived', False),
                    'last_seen': user.get('last_seen').isoformat() if user.get('last_seen') else None
                })
            
        return jsonify(results), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
