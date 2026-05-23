import datetime
import bcrypt
import jwt
from flask import Blueprint, request, jsonify
from app.models.db import users_collection
from app.utils.jwt_utils import generate_tokens, JWT_REFRESH_SECRET, token_required


auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/public_key', methods=['PUT'])
@token_required
def update_public_key(current_user_id):
    pub_key = request.json.get('public_key')
    if not pub_key:
        return jsonify({'error': 'Missing public key'}), 400
        
    users_collection.update_one(
        {'_id': current_user_id},
        {'$set': {'public_key': pub_key}}
    )
    return jsonify({'msg': 'Public key updated'}), 200

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    identity_hash = data.get('identity_hash', '')  # PBKDF2-derived identity

    if not username or not password:
        return jsonify({'error': 'Missing fields'}), 400

    if users_collection.find_one({'username': username}):
        return jsonify({'error': 'Username taken'}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    new_user = {
        'username': username,
        'password': hashed_password,
        'identity_hash': identity_hash,
        'public_key': identity_hash,  # Kept for backward compat
        'profile_pic': None,
        'status_message': "Hey there! I am using SecureChat.",
        'last_seen': datetime.datetime.utcnow(),
        'is_online': False,
        'created_at': datetime.datetime.utcnow()
    }
    
    users_collection.insert_one(new_user)
    return jsonify({'msg': 'User created successfully'}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    identity_hash = data.get('identity_hash', '')  # PBKDF2 identity, updated on every login

    user = users_collection.find_one({'username': username})
    if not user:
        return jsonify({'error': 'User not found'}), 400

    if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        return jsonify({'error': 'Wrong password'}), 400

    # Always update identity_hash so friends get the latest
    update_fields = {'last_seen': datetime.datetime.utcnow()}
    if identity_hash:
        update_fields['identity_hash'] = identity_hash
        update_fields['public_key'] = identity_hash  # backward compat
    users_collection.update_one({'_id': str(user['_id'])}, {'$set': update_fields})

    access_token, refresh_token = generate_tokens(user['_id'], username)

    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'username': username,
        'id': str(user['_id'])
    }), 200

@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    data = request.json
    refresh_token = data.get('refresh_token')
    
    if not refresh_token:
        return jsonify({'error': 'Refresh token missing'}), 400
        
    try:
        data = jwt.decode(refresh_token, JWT_REFRESH_SECRET, algorithms=['HS256'])
        current_user_id = data['id']
        username = data['username']
        
        # Verify user still exists
        user = users_collection.find_one({'_id': current_user_id})
        if not user:
            return jsonify({'error': 'User no longer exists'}), 401
            
        access_token, new_refresh_token = generate_tokens(current_user_id, username)
        
        return jsonify({
            'access_token': access_token,
            'refresh_token': new_refresh_token
        }), 200
        
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Refresh token expired. Please login again.'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid refresh token'}), 401
