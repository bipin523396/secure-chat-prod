from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "message": "Direct file health check works"}), 200

# For Vercel
def handler(request):
    return app(request)
