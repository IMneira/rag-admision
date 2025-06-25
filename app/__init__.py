from flask import Flask
from flask_cors import CORS
from config import Config
from app.db import flask_db

def create_app():
    app = Flask(__name__)

    # Enhanced CORS configuration for React app
    CORS(app, 
         origins=Config.CORS_ORIGINS,
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         supports_credentials=True)
    
    app.config.from_object(Config)
    flask_db.init_app(app)
    
    # Import models to register them with SQLAlchemy
    from app.models import Conversation, Message

    from app.routes import blueprints
    for bp in blueprints:
        app.register_blueprint(bp)

    return app

app = create_app()