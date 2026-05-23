from flask import Flask, jsonify
app = Flask(__name__)
@app.route('/ping')
def ping():
    return jsonify({"ping": "pong", "v": "1.0.0"}), 200
handler = app
