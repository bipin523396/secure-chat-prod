import os
import sys
import traceback
from flask import Flask, jsonify

# Ensure the 'api' directory is in the path so 'app' package can be found
api_dir = os.path.dirname(os.path.abspath(__file__))
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

try:
    from app import create_app
    app = create_app()
    
    # Redefine health at top level to be absolutely sure it's accessible
    @app.route('/api/health')
    def health_check():
        return jsonify({
            "status": "ok",
            "database": "connected",
            "version": "2.0.5",
            "service": "SecureChat Backend (Full)"
        }), 200

except Exception as e:
    # Detailed error reporting fallback
    error_trace = traceback.format_exc()
    print(f"CRITICAL: Backend failed to start: {error_trace}")
    
    app = Flask(__name__)
    @app.route('/api/health')
    def health_error():
        return jsonify({
            "status": "error",
            "message": str(e),
            "traceback": error_trace,
            "version": "2.0.5-failure"
        }), 500
    
    @app.route('/api/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
    def catch_all_error(path):
        return jsonify({
            "error": "Backend Initialization Failed",
            "details": str(e)
        }), 500

# Vercel's required entry point
handler = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
