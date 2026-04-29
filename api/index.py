import os
import sys
import traceback
from flask import Flask, jsonify

# Ensure the 'api' directory is in the path so 'app' can be imported
sys.path.append(os.path.dirname(__file__))

try:
    from app import create_app
    app = create_app()
except Exception as e:
    # If app creation fails (e.g. during imports), create a dummy app to report the error
    error_trace = traceback.format_exc()
    print(f"CRITICAL ERROR DURING APP INITIALIZATION: {error_trace}")
    
    app = Flask(__name__)
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
    def catch_all(path):
        return jsonify({
            "error": "Backend Initialization Failed",
            "message": str(e),
            "traceback": error_trace,
            "cwd": os.getcwd(),
            "files_in_cwd": os.listdir('.') if hasattr(os, 'listdir') else []
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)


