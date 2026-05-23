import os
import jwt
import datetime
from functools import wraps
from flask import request, jsonify

JWT_SECRET = os.getenv("JWT_SECRET", "JdXw3ypy3KXjLxfRpNW2LWV4ie3WyxrzCN7YUNAAxvE")
JWT_REFRESH_SECRET = os.getenv("JWT_REFRESH_SECRET", "RefreshSecretTokenKeyHere2024")

def generate_tokens(user_id, username):
    # Access token expires in 15 minutes
    access_token = jwt.encode(
        {'id': str(user_id), 'username': username, 'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=15)},
        JWT_SECRET,
        algorithm='HS256'
    )
    # Refresh token expires in 7 days
    refresh_token = jwt.encode(
        {'id': str(user_id), 'username': username, 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)},
        JWT_REFRESH_SECRET,
        algorithm='HS256'
    )
    return access_token, refresh_token

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
                
        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            current_user_id = data['id']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired', 'code': 'TOKEN_EXPIRED'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
            
        return f(current_user_id, *args, **kwargs)
    return decorated
