from flask import Blueprint, request, jsonify
from backend_app.models.db import db
from backend_app.utils.jwt_utils import token_required
import datetime

messages_bp = Blueprint('messages', __name__)

@messages_bp.route('/send', methods=['POST'])
@token_required
def send_message_rest(current_user_id):
    data = request.json
    receiver_username = data.get('receiver')
    ciphertext = data.get('ciphertext')
    iv = data.get('iv')
    
    if not receiver_username or not ciphertext or not iv:
        return jsonify({'error': 'Missing fields'}), 400
        
    # Find receiver ID
    receiver_doc = list(db.collection("users").where("username", "==", receiver_username).limit(1).stream())
    if not receiver_doc:
        return jsonify({'error': 'Receiver not found'}), 404
    receiver_id = receiver_doc[0].id
    
    # Get sender username
    sender_doc = db.collection("users").document(current_user_id).get()
    sender_username = sender_doc.to_dict()['username']
    
    # Save message to Firestore
    message_data = {
        'sender': sender_username,
        'receiver': receiver_username,
        'sender_id': current_user_id,
        'receiver_id': receiver_id,
        'ciphertext': ciphertext,
        'iv': iv,
        'timestamp': datetime.datetime.utcnow(),
        'status': 'sent'
    }
    
    doc_ref = db.collection("messages").add(message_data)
    message_data['_id'] = doc_ref[1].id
    message_data['timestamp'] = message_data['timestamp'].isoformat()
    
    return jsonify(message_data), 201

@messages_bp.route('/history', methods=['GET'])
@token_required
def get_chat_history(current_user_id):
    partner_username = request.args.get('withUser')
    if not partner_username:
        return jsonify({'error': 'Missing withUser'}), 400
        
    # Get sender username
    me_doc = db.collection("users").document(current_user_id).get()
    my_username = me_doc.to_dict()['username']
    
    # Fetch messages between these two users
    # Query 1: Me -> Partner
    q1 = db.collection("messages")\
        .where("sender", "==", my_username)\
        .where("receiver", "==", partner_username)\
        .order_by("timestamp")\
        .limit(100).stream()
        
    # Query 2: Partner -> Me
    q2 = db.collection("messages")\
        .where("sender", "==", partner_username)\
        .where("receiver", "==", my_username)\
        .order_by("timestamp")\
        .limit(100).stream()
        
    results = []
    for doc in q1:
        d = doc.to_dict()
        d['_id'] = doc.id
        d['timestamp'] = d['timestamp'].isoformat()
        results.append(d)
        
    for doc in q2:
        d = doc.to_dict()
        d['_id'] = doc.id
        d['timestamp'] = d['timestamp'].isoformat()
        results.append(d)
        
    # Sort by timestamp
    results.sort(key=lambda x: x['timestamp'])
    
    return jsonify(results), 200

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
