import os
import sys
import traceback
from flask import Flask, jsonify, request

# app is now in the root, so this should work directly
try:
    from app import create_app
    app = create_app()
    
    @app.route('/api/health')
    def health_check():
        return jsonify({
            "status": "ok",
            "database": "connected",
            "version": "3.0.4",
            "service": "SecureChat Production v3"
        }), 200

except Exception as e:
    error_trace = traceback.format_exc()
    print(f"CRITICAL: Backend failed to start: {error_trace}")
    
    app = Flask(__name__)
    @app.route('/api/health')
    def health_error():
        return jsonify({
            "status": "error",
            "message": str(e),
            "traceback": error_trace,
            "version": "2.0.6-failure"
        }), 500

# Vercel's required entry point
handler = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
