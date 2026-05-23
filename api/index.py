import os
import sys
import traceback
from flask import Flask, jsonify, request

# Ensure the root directory is in the path so 'app' package can be found
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from app import create_app
    app = create_app()
    
    @app.route('/api/health')
    def health_check():
        return jsonify({
            "status": "ok",
            "database": "connected",
            "version": "3.1.8",
            "service": "SecureChat Production v5"
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
            "version": "3.1.8-failure"
        }), 500

# Vercel's required entry point
handler = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
