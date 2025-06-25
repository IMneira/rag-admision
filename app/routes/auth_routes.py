from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, current_user
from app.models import User, UserRole
from app.auth.utils import (
    validate_password, validate_username, validate_email, 
    sanitize_user_input, format_user_error
)
from app.auth.decorators import login_required
from datetime import datetime

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def format_response(success=True, data=None, error=None, status_code=200):
    """Standardize API responses"""
    response = {
        'success': success,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    if success and data is not None:
        response['data'] = data
    elif not success and error is not None:
        response['error'] = error
        
    return jsonify(response), status_code


@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user account"""
    try:
        if not request.json:
            return format_response(
                success=False,
                error='Request must be JSON',
                status_code=400
            )
        
        data = request.json
        username = sanitize_user_input(data.get('username', '').strip())
        email = sanitize_user_input(data.get('email', '').strip().lower())
        password = data.get('password', '')
        
        # Validate required fields
        if not username:
            return format_response(
                success=False,
                error='Username is required',
                status_code=400
            )
        
        if not email:
            return format_response(
                success=False,
                error='Email is required',
                status_code=400
            )
        
        if not password:
            return format_response(
                success=False,
                error='Password is required',
                status_code=400
            )
        
        # Validate username
        username_valid, username_error = validate_username(username)
        if not username_valid:
            return format_response(
                success=False,
                error=username_error,
                status_code=400
            )
        
        # Validate email
        email_valid, email_error = validate_email(email)
        if not email_valid:
            return format_response(
                success=False,
                error=email_error,
                status_code=400
            )
        
        # Validate password
        password_valid, password_error = validate_password(password)
        if not password_valid:
            return format_response(
                success=False,
                error=password_error,
                status_code=400
            )
        
        # Create user
        try:
            user = User.create_user(
                username=username,
                email=email,
                password=password,
                role=UserRole.USER  # Default role is USER
            )
            
            return format_response(
                success=True,
                data={
                    'user': user.to_dict(),
                    'message': 'User registered successfully'
                }
            )
            
        except ValueError as e:
            return format_response(
                success=False,
                error=str(e),
                status_code=409
            )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Registration failed: {str(e)}',
            status_code=500
        )


@auth_bp.route('/login', methods=['POST'])
def login():
    """User login endpoint"""
    try:
        if not request.json:
            return format_response(
                success=False,
                error='Request must be JSON',
                status_code=400
            )
        
        data = request.json
        username_or_email = sanitize_user_input(data.get('username', '').strip())
        password = data.get('password', '')
        remember_me = data.get('remember_me', False)
        
        if not username_or_email:
            return format_response(
                success=False,
                error='Username or email is required',
                status_code=400
            )
        
        if not password:
            return format_response(
                success=False,
                error='Password is required',
                status_code=400
            )
        
        # Authenticate user
        user = User.authenticate(username_or_email, password)
        
        if not user:
            return format_response(
                success=False,
                error='Invalid username/email or password',
                status_code=401
            )
        
        # Log in user
        login_user(user, remember=remember_me)
        
        return format_response(
            success=True,
            data={
                'user': user.to_dict(include_sensitive=True),
                'message': 'Login successful'
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Login failed: {str(e)}',
            status_code=500
        )


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """User logout endpoint"""
    try:
        logout_user()
        return format_response(
            success=True,
            data={'message': 'Logout successful'}
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Logout failed: {str(e)}',
            status_code=500
        )


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current user information"""
    try:
        return format_response(
            success=True,
            data={
                'user': current_user.to_dict(include_sensitive=True)
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to get user info: {str(e)}',
            status_code=500
        )


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password"""
    try:
        if not request.json:
            return format_response(
                success=False,
                error='Request must be JSON',
                status_code=400
            )
        
        data = request.json
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        
        if not current_password:
            return format_response(
                success=False,
                error='Current password is required',
                status_code=400
            )
        
        if not new_password:
            return format_response(
                success=False,
                error='New password is required',
                status_code=400
            )
        
        # Validate new password
        password_valid, password_error = validate_password(new_password)
        if not password_valid:
            return format_response(
                success=False,
                error=password_error,
                status_code=400
            )
        
        # Change password
        try:
            current_user.change_password(current_password, new_password)
            
            return format_response(
                success=True,
                data={'message': 'Password changed successfully'}
            )
            
        except ValueError as e:
            return format_response(
                success=False,
                error=str(e),
                status_code=400
            )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Password change failed: {str(e)}',
            status_code=500
        )


@auth_bp.route('/status', methods=['GET'])
def auth_status():
    """Check authentication status"""
    try:
        if current_user.is_authenticated:
            return format_response(
                success=True,
                data={
                    'authenticated': True,
                    'user': current_user.to_dict()
                }
            )
        else:
            return format_response(
                success=True,
                data={
                    'authenticated': False,
                    'user': None
                }
            )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to check auth status: {str(e)}',
            status_code=500
        )