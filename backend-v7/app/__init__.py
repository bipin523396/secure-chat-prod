from flask import Flask, jsonify
from flask_cors import CORS
from app.models.db import init_db, db
from app.routes.auth import auth_bp
from app.routes.friends import friends_bp
from app.routes.media import media_bp
from app.routes.status import status_bp
from app.routes.messages import messages_bp
from app.routes.calls import calls_bp

import os

def create_app():
    # Files moved back to api/app for better Vercel support
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    static_dir = base_dir
    app = Flask(__name__, static_folder=static_dir, static_url_path='')
    
    # Configure CORS to allow all for API routes
    CORS(app, resources={r"/api-v7/*": {"origins": "*"}})
    
    # Initialize DB indexes
    init_db()
    
    # Register Blueprints
    app.register_blueprint(auth_bp, url_prefix='/api-v7')
    app.register_blueprint(friends_bp, url_prefix='/api-v7/friends')
    app.register_blueprint(media_bp, url_prefix='/api-v7/media')
    app.register_blueprint(status_bp, url_prefix='/api-v7/status')
    app.register_blueprint(messages_bp, url_prefix='/api-v7/messages')
    app.register_blueprint(calls_bp, url_prefix='/api-v7/calls')
    
    @app.route('/api-v7/health')
    def health():
        db_status = "connected" if db else "disconnected"
        return jsonify({
            "status": "ok", 
            "service": "SecureChat Backend", 
            "version": "2.0.2",
            "database": db_status
        }), 200
    
    @app.route('/api/v2/test')
    def test_v2():
        return jsonify({"message": "Vercel Backend is Live", "timestamp": os.getenv('VERCEL_DEPLOYMENT_ID', 'local')}), 200
    
    @app.route('/')
    def index():
        try:
            return app.send_static_file('index.html')
        except:
            return "SecureChat Backend is running. Frontend might not be bundled correctly in this environment.", 200
        
    @app.route('/<path:path>')
    def static_files(path):
        try:
            return app.send_static_file(path)
        except:
            return "File not found", 404

    @app.errorhandler(Exception)
    def handle_exception(e):
        # Pass through HTTP errors
        if hasattr(e, 'code'):
            return jsonify({"error": str(e)}), e.code
        # Handle non-HTTP errors
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

    return app
