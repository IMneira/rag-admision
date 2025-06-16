from flask import Flask
from flask_cors import CORS
from config import Config
from app.db import flask_db

def create_app():
    app = Flask(__name__)

    CORS(app, origins=Config.CORS_ORIGINS)
    app.config.from_object(Config)
    flask_db.init_app(app)

    from app.routes import blueprints
    for bp in blueprints:
        app.register_blueprint(bp)

    return app

app = create_app()