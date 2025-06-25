from .main_routes import main_bp
from .api_routes import api_bp
from .auth_routes import auth_bp
from .admin_routes import admin_bp

blueprints = [
    main_bp,
    api_bp,
    auth_bp,
    admin_bp
]
