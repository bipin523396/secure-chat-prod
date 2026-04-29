import datetime
from flask import Blueprint, request, jsonify
from app.models.db import users_collection, friend_requests_collection, friends_collection, blocked_users_collection
from app.utils.jwt_utils import token_required
from bson import ObjectId

friends_bp = Blueprint('friends', __name__)

@friends_bp.route('/search', methods=['GET'])
@token_required
def search_users(current_user_id):
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
        
    # Find users matching query (case-insensitive) but exclude current user and blocked users
    blocked = blocked_users_collection.find({'$or': [{'blocker_id': ObjectId(current_user_id)}, {'blocked_id': ObjectId(current_user_id)}]})
    blocked_ids = [b['blocked_id'] if b['blocker_id'] == ObjectId(current_user_id) else b['blocker_id'] for b in blocked]
    blocked_ids.append(ObjectId(current_user_id))
    
    users = users_collection.find({
        'username': {'$regex': query, '$options': 'i'},
        '_id': {'$nin': blocked_ids}
    }, {'password': 0}).limit(20)
    
    results = []
    for user in users:
        # Check friendship status
        status = "none"
        friend_check = friends_collection.find_one({'$or': [
            {'user_id': ObjectId(current_user_id), 'friend_id': user['_id']},
            {'user_id': user['_id'], 'friend_id': ObjectId(current_user_id)}
        ]})
        
        if friend_check:
            status = "friend"
        else:
            req_check = friend_requests_collection.find_one({
                'sender_id': ObjectId(current_user_id), 'receiver_id': user['_id'], 'status': 'pending'
            })
            if req_check:
                status = "request_sent"
            else:
                req_check = friend_requests_collection.find_one({
                    'sender_id': user['_id'], 'receiver_id': ObjectId(current_user_id), 'status': 'pending'
                })
                if req_check:
                    status = "request_received"
                    
        user_data = {
            'id': str(user['_id']),
            'username': user['username'],
            'profile_pic': user.get('profile_pic'),
            'status_message': user.get('status_message'),
            'status': status
        }
        results.append(user_data)
        
    return jsonify(results), 200

@friends_bp.route('/request', methods=['POST'])
@token_required
def add_friend(current_user_id):
    target_username = request.json.get('username')
    target_user = users_collection.find_one({'username': target_username})
    
    if not target_user:
        return jsonify({'error': 'User not found'}), 404
        
    if str(target_user['_id']) == str(current_user_id):
        return jsonify({'error': 'Cannot add yourself'}), 400
        
    # Check if already friends
    if friends_collection.find_one({'user_id': ObjectId(current_user_id), 'friend_id': target_user['_id']}):
        return jsonify({'error': 'Already friends'}), 400
        
    # Directly create friendship entries (bidirectional)
    friends_collection.insert_one({'user_id': ObjectId(current_user_id), 'friend_id': target_user['_id'], 'created_at': datetime.datetime.utcnow()})
    friends_collection.insert_one({'user_id': target_user['_id'], 'friend_id': ObjectId(current_user_id), 'created_at': datetime.datetime.utcnow()})
    
    return jsonify({'msg': 'Friend added successfully'}), 201

@friends_bp.route('/requests', methods=['GET'])
@token_required
def get_requests(current_user_id):
    # Incoming pending requests
    requests = friend_requests_collection.find({
        'receiver_id': ObjectId(current_user_id),
        'status': 'pending'
    })
    
    results = []
    for req in requests:
        sender = users_collection.find_one({'_id': req['sender_id']})
        results.append({
            'request_id': str(req['_id']),
            'sender': {
                'id': str(sender['_id']),
                'username': sender['username'],
                'profile_pic': sender.get('profile_pic')
            },
            'created_at': req['created_at'].isoformat()
        })
        
    return jsonify(results), 200

@friends_bp.route('/request/<request_id>/accept', methods=['PUT'])
@token_required
def accept_request(current_user_id, request_id):
    req = friend_requests_collection.find_one({'_id': ObjectId(request_id), 'receiver_id': ObjectId(current_user_id)})
    if not req or req['status'] != 'pending':
        return jsonify({'error': 'Request not found or not pending'}), 404
        
    # Update request
    friend_requests_collection.update_one({'_id': ObjectId(request_id)}, {'$set': {'status': 'accepted'}})
    
    # Create friendship entries (bidirectional)
    friends_collection.insert_one({'user_id': ObjectId(current_user_id), 'friend_id': req['sender_id'], 'created_at': datetime.datetime.utcnow()})
    friends_collection.insert_one({'user_id': req['sender_id'], 'friend_id': ObjectId(current_user_id), 'created_at': datetime.datetime.utcnow()})
    
    return jsonify({'msg': 'Friend request accepted'}), 200

@friends_bp.route('/request/<request_id>/reject', methods=['PUT'])
@token_required
def reject_request(current_user_id, request_id):
    req = friend_requests_collection.find_one({'_id': ObjectId(request_id), 'receiver_id': ObjectId(current_user_id)})
    if not req or req['status'] != 'pending':
        return jsonify({'error': 'Request not found or not pending'}), 404
        
    friend_requests_collection.update_one({'_id': ObjectId(request_id)}, {'$set': {'status': 'rejected'}})
    return jsonify({'msg': 'Friend request rejected'}), 200

@friends_bp.route('/list', methods=['GET'])
@token_required
def list_friends(current_user_id):
    try:
        friends = list(friends_collection.find({'user_id': ObjectId(current_user_id)}))
        friend_ids = []
        for f in friends:
            f_id = f['friend_id']
            if isinstance(f_id, str):
                try: friend_ids.append(ObjectId(f_id))
                except: friend_ids.append(f_id)
            else:
                friend_ids.append(f_id)
        
        # Also find by string user_id for legacy records
        legacy_friends = list(friends_collection.find({'user_id': str(current_user_id)}))
        for f in legacy_friends:
            f_id = f['friend_id']
            if isinstance(f_id, str):
                try: friend_ids.append(ObjectId(f_id))
                except: friend_ids.append(f_id)
            else:
                friend_ids.append(f_id)

        friend_users = users_collection.find({'_id': {'$in': friend_ids}})
        results = []
        for user in friend_users:
            results.append({
                'id': str(user['_id']),
                'username': user['username'],
                'identity_hash': user.get('identity_hash') or user.get('public_key', ''),
                'profile_pic': user.get('profile_pic'),
                'status_message': user.get('status_message'),
                'is_online': user.get('is_online', False),
                'last_seen': user.get('last_seen').isoformat() if user.get('last_seen') else None
            })
            
        return jsonify(results), 200
    except Exception as e:
        print(f"Error in list_friends: {str(e)}")
        return jsonify({'error': str(e)}), 500
