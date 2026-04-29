from flask import Flask
from flask_cors import CORS
from app.models.db import init_db
from app.routes.auth import auth_bp
from app.routes.friends import friends_bp
from app.routes.media import media_bp
from app.routes.status import status_bp
from app.routes.messages import messages_bp
from app.routes.calls import calls_bp

import os

def create_app():
    # Files moved to root for better Vercel support
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    static_dir = base_dir
    app = Flask(__name__, static_folder=static_dir, static_url_path='')
    
    # Configure CORS to allow all for API routes
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Initialize DB indexes
    init_db()
    
    # Register Blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(friends_bp, url_prefix='/api/friends')
    app.register_blueprint(media_bp, url_prefix='/api/media')
    app.register_blueprint(status_bp, url_prefix='/api/status')
    app.register_blueprint(messages_bp, url_prefix='/api/messages')
    app.register_blueprint(calls_bp, url_prefix='/api/calls')
    
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
