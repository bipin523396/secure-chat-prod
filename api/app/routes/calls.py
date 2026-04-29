from flask import Blueprint, request, jsonify
from app.models.db import db
from app.utils.jwt_utils import token_required
import datetime

calls_bp = Blueprint('calls', __name__)

@calls_bp.route('/history', methods=['GET'])
@token_required
def get_call_history(current_user_id):
    # Fetch calls where user is either caller or receiver
    q1 = db.collection("calls").where("caller_id", "==", current_user_id).stream()
    q2 = db.collection("calls").where("receiver_id", "==", current_user_id).stream()
    
    results = []
    for doc in q1:
        data = doc.to_dict()
        data['id'] = doc.id
        # Get receiver username
        u_doc = db.collection("users").document(data['receiver_id']).get()
        data['with_username'] = u_doc.to_dict()['username'] if u_doc.exists else "Unknown"
        data['direction'] = 'outgoing'
        results.append(data)
        
    for doc in q2:
        data = doc.to_dict()
        data['id'] = doc.id
        # Get caller username
        u_doc = db.collection("users").document(data['caller_id']).get()
        data['with_username'] = u_doc.to_dict()['username'] if u_doc.exists else "Unknown"
        data['direction'] = 'incoming'
        results.append(data)
        
    # Sort by timestamp descending
    results.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return jsonify(results), 200
