from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from config import Config
from app.db import flask_db

# Initialize extensions
login_manager = LoginManager()
bcrypt = Bcrypt()

def create_app():
    app = Flask(__name__)

    # Enhanced CORS configuration for React app
    CORS(app, 
         origins=Config.CORS_ORIGINS,
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         supports_credentials=True)
    
    app.config.from_object(Config)
    
    # Initialize extensions
    flask_db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    
    # Configure Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.get_by_id(user_id)
    
    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import jsonify
        return jsonify({
            'success': False,
            'error': 'Authentication required',
            'login_url': '/api/auth/login'
        }), 401
    
    # Import models to register them with SQLAlchemy
    from app.models import Conversation, Message, User

    from app.routes import blueprints
    for bp in blueprints:
        app.register_blueprint(bp)

    return app

app = create_app()