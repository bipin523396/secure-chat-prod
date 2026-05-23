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
    app = Flask(__name__)
    
    # Configure CORS to allow all for API routes
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Initialize DB indexes
    init_db()
    
    # Register Blueprints
    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(friends_bp, url_prefix='/api/friends')
    app.register_blueprint(media_bp, url_prefix='/api/media')
    app.register_blueprint(status_bp, url_prefix='/api/status')
    app.register_blueprint(messages_bp, url_prefix='/api/messages')
    app.register_blueprint(calls_bp, url_prefix='/api/calls')
    
    @app.route('/api/health')
    def health():
        db_status = "connected" if db else "disconnected"
        return jsonify({
            "status": "ok", 
            "service": "SecureChat Backend", 
            "version": "4.0.1",
            "database": db_status
        }), 200
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        # Pass through HTTP errors
        if hasattr(e, 'code'):
            return jsonify({"error": str(e)}), e.code
        # Handle non-HTTP errors
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

    return app
