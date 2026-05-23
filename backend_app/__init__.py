from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from backend_app.models.db import init_db, db
from backend_app.routes.auth import auth_bp
from backend_app.routes.friends import friends_bp
from backend_app.routes.media import media_bp
from backend_app.routes.status import status_bp
from backend_app.routes.messages import messages_bp
from backend_app.routes.calls import calls_bp

import os

def create_app():
    app = Flask(__name__)

    CORS(
        app,
        resources={r"/api/*": {"origins": "*"}},
        supports_credentials=False,
        allow_headers=["Authorization", "Content-Type"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    @app.before_request
    def handle_preflight():
        if request.method != "OPTIONS":
            return None
        response = make_response("", 204)
        origin = request.headers.get("Origin", "*")
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Max-Age"] = "86400"
        return response

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
        else:
            response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return response
    
    # Initialize DB indexes
    init_db()
    
    # Register Blueprints
    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(friends_bp, url_prefix='/api/friends')
    app.register_blueprint(media_bp, url_prefix='/api/media')
    app.register_blueprint(status_bp, url_prefix='/api/status')
    app.register_blueprint(messages_bp, url_prefix='/api/messages')
    app.register_blueprint(calls_bp, url_prefix='/api/calls')
    
    @app.route('/')
    def home():
        return jsonify({
            "status": "success",
            "message": "SecureChat backend running",
            "version": "4.0.32"
        }), 200

    @app.route('/api/health')
    def health():
        db_status = "connected" if db else "disconnected"
        return jsonify({
            "status": "ok", 
            "service": "SecureChat Backend", 
            "version": "4.0.32",
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
