import os
import sys
import traceback
from flask import Flask, jsonify
from flask_cors import CORS

try:
    from backend_app import create_app
    app = create_app()
    CORS(app)
except Exception as e:
    error_trace = traceback.format_exc()
    print(f"CRITICAL: Backend failed to start: {error_trace}")
    
    app = Flask(__name__)
    @app.route('/v8-api/health')
    @app.route('/')
    def health_error():
        return jsonify({
            "status": "error",
            "message": str(e),
            "traceback": error_trace,
            "version": "4.0.7-failure"
        }), 500

# Vercel/Render entry point
handler = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
