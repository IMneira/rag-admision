from functools import wraps
from flask import jsonify, request
from flask_login import current_user, login_required as flask_login_required
from app.models import UserRole


def format_auth_error(message, status_code=401):
    """Format authentication error response"""
    return jsonify({
        'success': False,
        'error': message,
        'timestamp': None
    }), status_code


def login_required(f):
    """Decorator to require user authentication"""
    @wraps(f)
    @flask_login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return format_auth_error('Authentication required')
        
        if not current_user.is_active:
            return format_auth_error('Account is deactivated', 403)
        
        return f(*args, **kwargs)
    
    return decorated_function


def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    @flask_login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return format_auth_error('Authentication required')
        
        if not current_user.is_active:
            return format_auth_error('Account is deactivated', 403)
        
        if not current_user.is_admin():
            return format_auth_error('Admin privileges required', 403)
        
        return f(*args, **kwargs)
    
    return decorated_function


def optional_auth(f):
    """Decorator for endpoints that work with or without authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # This decorator allows endpoints to work with optional authentication
        # current_user will be available if logged in, None otherwise
        return f(*args, **kwargs)
    
    return decorated_function


def api_key_or_login_required(f):
    """Decorator that allows either API key or login authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for API key in headers
        api_key = request.headers.get('X-API-Key')
        if api_key:
            # Validate API key (implement according to your needs)
            from config import Config
            if api_key == getattr(Config, 'API_KEY', None):
                return f(*args, **kwargs)
        
        # Fall back to login requirement
        if not current_user.is_authenticated:
            return format_auth_error('Authentication required (login or API key)')
        
        if not current_user.is_active:
            return format_auth_error('Account is deactivated', 403)
        
        return f(*args, **kwargs)
    
    return decorated_function