import os
import sys
from flask import Flask, jsonify

# Ensure the 'api' directory and 'app' package are in the path
api_dir = os.path.dirname(os.path.abspath(__file__))
if api_dir not in sys.path:
    sys.path.append(api_dir)

try:
    from app import create_app, db
    app = create_app()
    
    # Ensure health check is available at the root level for Vercel
    @app.route('/api/health')
    def health_check():
        db_status = "connected" if db else "disconnected"
        return jsonify({
            "status": "ok",
            "database": db_status,
            "version": "2.0.5",
            "service": "SecureChat Backend"
        }), 200

except Exception as e:
    # Fallback app to report errors if initialization fails
    app = Flask(__name__)
    @app.route('/api/health')
    def health_error():
        return jsonify({
            "status": "error",
            "message": str(e),
            "version": "2.0.5-fallback"
        }), 500

# Vercel searches for 'app' or 'handler'
handler = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
