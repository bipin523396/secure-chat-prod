from flask import Flask
from flask_cors import CORS
from app.models.db import init_db
from app.routes.auth import auth_bp
from app.routes.friends import friends_bp
from app.routes.media import media_bp
from app.routes.status import status_bp
from app.routes.messages import messages_bp
from app.routes.calls import calls_bp

def create_app():
    app = Flask(__name__, static_folder='../../client', static_url_path='')
    
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
        return app.send_static_file('index.html')
        
    @app.route('/<path:path>')
    def static_files(path):
        return app.send_static_file(path)

    return app
