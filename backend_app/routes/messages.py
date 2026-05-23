from flask import Blueprint, request, jsonify
from backend_app.models.db import db
from backend_app.utils.jwt_utils import token_required
import datetime
import traceback

messages_bp = Blueprint('messages', __name__)

UTC = datetime.timezone.utc


def _parse_iso_datetime(value):
    """Safely parse ISO-8601 / Firestore timestamps; returns UTC-aware datetime or None."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        dt = value
    elif isinstance(value, (int, float)):
        ts = value / 1000.0 if value > 1e12 else value
        dt = datetime.datetime.fromtimestamp(ts, tz=UTC)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.datetime.fromisoformat(s)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_since(since):
    """Validate ?since= query param (e.g. 2026-05-23T14:31:38.582Z)."""
    if since is None:
        return None
    if isinstance(since, str) and not since.strip():
        return None
    return _parse_iso_datetime(since)


def _chat_id(username_a, username_b):
    return "_".join(sorted([username_a, username_b]))


def _serialize_message(doc):
    d = doc.to_dict()
    d['_id'] = doc.id
    ts = d.get('timestamp')
    parsed = _parse_iso_datetime(ts)
    if parsed is not None:
        d['timestamp'] = parsed.isoformat().replace('+00:00', 'Z')
    elif ts is not None:
        d['timestamp'] = str(ts)
    else:
        d['timestamp'] = ''
    return d


def _fetch_conversation_messages(my_username, partner_username, since=None):
    """Load all messages between two users (chat_id + legacy queries)."""
    chat_id = _chat_id(my_username, partner_username)
    by_id = {}

    for doc in db.collection("messages").where("chat_id", "==", chat_id).limit(200).stream():
        by_id[doc.id] = _serialize_message(doc)

    for field_a, user_a, field_b, user_b in (
        ("sender", my_username, "receiver", partner_username),
        ("sender", partner_username, "receiver", my_username),
    ):
        for doc in db.collection("messages").where(field_a, "==", user_a).where(field_b, "==", user_b).limit(100).stream():
            if doc.id not in by_id:
                by_id[doc.id] = _serialize_message(doc)

    results = list(by_id.values())
    since_dt = _parse_since(since)
    if since_dt is not None:
        filtered = []
        for m in results:
            m_dt = _parse_iso_datetime(m.get('timestamp'))
            if m_dt is None:
                filtered.append(m)
                continue
            if m_dt > since_dt:
                filtered.append(m)
        results = filtered

    results.sort(key=lambda x: x.get('timestamp') or '')
    return results[-100:]


@messages_bp.route('/send', methods=['POST'])
@token_required
def send_message_rest(current_user_id):
    data = request.json or {}
    receiver_username = data.get('receiver')
    ciphertext = data.get('ciphertext')
    iv = data.get('iv')
    file_id = data.get('file_id')
    file_name = data.get('file_name')
    file_type = data.get('file_type')

    if not receiver_username:
        return jsonify({'error': 'Missing receiver'}), 400

    is_file = bool(file_id)
    if not is_file and (ciphertext is None or iv is None):
        return jsonify({'error': 'Missing fields'}), 400

    receiver_doc = list(db.collection("users").where("username", "==", receiver_username).limit(1).stream())
    if not receiver_doc:
        return jsonify({'error': 'Receiver not found'}), 404
    receiver_id = receiver_doc[0].id

    sender_doc = db.collection("users").document(current_user_id).get()
    if not sender_doc.exists:
        return jsonify({'error': 'Sender not found'}), 404
    sender_username = sender_doc.to_dict()['username']
    chat_id = _chat_id(sender_username, receiver_username)

    message_data = {
        'chat_id': chat_id,
        'sender': sender_username,
        'receiver': receiver_username,
        'sender_id': current_user_id,
        'receiver_id': receiver_id,
        'timestamp': datetime.datetime.utcnow(),
        'status': 'sent',
        'deleted': False,
        'edited': False,
    }

    if is_file:
        message_data['file_id'] = file_id
        message_data['file_name'] = file_name or 'file'
        message_data['file_type'] = file_type or 'application/octet-stream'
    else:
        message_data['ciphertext'] = ciphertext
        message_data['iv'] = iv

    doc_ref = db.collection("messages").add(message_data)
    message_data['_id'] = doc_ref[1].id
    message_data['timestamp'] = message_data['timestamp'].isoformat()

    return jsonify(message_data), 201


@messages_bp.route('/history', methods=['GET'])
@token_required
def get_chat_history(current_user_id):
    try:
        partner_username = request.args.get('withUser')
        since = request.args.get('since')
        if not partner_username:
            return jsonify({'error': 'Missing withUser'}), 400

        me_doc = db.collection("users").document(current_user_id).get()
        if not me_doc.exists:
            return jsonify({'error': 'User not found'}), 404
        my_username = me_doc.to_dict()['username']

        messages = _fetch_conversation_messages(
            my_username, partner_username, since=since
        )
        return jsonify(messages), 200
    except Exception as error:
        print('History route error:', error)
        traceback.print_exc()
        return jsonify({'error': str(error)}), 500


@messages_bp.route('/star', methods=['POST'])
@token_required
def star_message(current_user_id):
    message_id = request.json.get('message_id')
    is_starred = request.json.get('starred', True)

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

    results = []
    for doc in docs:
        data = doc.to_dict()
        msg_doc = db.collection("messages").document(data['message_id']).get()
        if msg_doc.exists:
            msg = msg_doc.to_dict()
            msg['id'] = msg_doc.id
            results.append(msg)

    return jsonify(results), 200
