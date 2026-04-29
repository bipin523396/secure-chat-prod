from flask import Blueprint, request, jsonify
from app.models.db import db
from app.utils.jwt_utils import token_required
import datetime

messages_bp = Blueprint('messages', __name__)

@messages_bp.route('/star', methods=['POST'])
@token_required
def star_message(current_user_id):
    message_id = request.json.get('message_id')
    is_starred = request.json.get('starred', True)
    
    # Store stars in a separate collection for easy retrieval
    star_ref = db.collection("starred_messages").document(f"{current_user_id}_{message_id}")
    
    if is_starred:
        star_ref.set({
            'user_id': current_user_id,
            'message_id': message_id,
            'starred_at': datetime.datetime.utcnow()
        })
    else:
        star_ref.delete()
        
    return jsonify({'msg': 'Star updated'}), 200

@messages_bp.route('/starred', methods=['GET'])
@token_required
def get_starred_messages(current_user_id):
    docs = db.collection("starred_messages").where("user_id", "==", current_user_id).stream()
    
    # In a real app, we'd need to fetch the actual message content from the messages collection
    # For now, we'll return the IDs. The client would ideally fetch these.
    # To keep it simple for the clone, we'll assume the client handles the mapping or we fetch a few.
    
    results = []
    for doc in docs:
        data = doc.to_dict()
        # Fetch message content (assuming messages are in 'messages' collection)
        msg_doc = db.collection("messages").document(data['message_id']).get()
        if msg_doc.exists:
            msg = msg_doc.to_dict()
            msg['id'] = msg_doc.id
            results.append(msg)
            
    return jsonify(results), 200
