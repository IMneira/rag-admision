from flask import Blueprint, request, jsonify
from flask_login import current_user
from app.models import User, UserRole, Conversation
from app.auth.decorators import admin_required
from app.auth.utils import validate_password, validate_username, validate_email, sanitize_user_input
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


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


@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_all_users():
    """Get all users (admin only)"""
    try:
        users = User.get_all_users()
        users_list = [user.to_dict(include_sensitive=True) for user in users]
        
        return format_response(
            success=True,
            data={
                'users': users_list,
                'total_count': len(users_list)
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to get users: {str(e)}',
            status_code=500
        )


@admin_bp.route('/users/<user_id>', methods=['GET'])
@admin_required
def get_user_details(user_id):
    """Get detailed user information (admin only)"""
    try:
        user = User.get_by_id(user_id)
        if not user:
            return format_response(
                success=False,
                error='User not found',
                status_code=404
            )
        
        # Get user's conversations count
        user_conversations = Conversation.get_by_user(user_id)
        
        user_data = user.to_dict(include_sensitive=True)
        user_data['conversations'] = [conv.to_dict() for conv in user_conversations]
        
        return format_response(
            success=True,
            data={'user': user_data}
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to get user details: {str(e)}',
            status_code=500
        )


@admin_bp.route('/users/<user_id>/promote', methods=['POST'])
@admin_required
def promote_user(user_id):
    """Promote user to admin role"""
    try:
        user = User.get_by_id(user_id)
        if not user:
            return format_response(
                success=False,
                error='User not found',
                status_code=404
            )
        
        if user.is_admin():
            return format_response(
                success=False,
                error='User is already an admin',
                status_code=400
            )
        
        user.promote_to_admin()
        
        return format_response(
            success=True,
            data={
                'user': user.to_dict(include_sensitive=True),
                'message': f'User {user.username} promoted to admin'
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to promote user: {str(e)}',
            status_code=500
        )


@admin_bp.route('/users/<user_id>/demote', methods=['POST'])
@admin_required
def demote_user(user_id):
    """Demote admin to user role"""
    try:
        user = User.get_by_id(user_id)
        if not user:
            return format_response(
                success=False,
                error='User not found',
                status_code=404
            )
        
        if not user.is_admin():
            return format_response(
                success=False,
                error='User is not an admin',
                status_code=400
            )
        
        # Prevent self-demotion
        if user.id == current_user.id:
            return format_response(
                success=False,
                error='Cannot demote yourself',
                status_code=400
            )
        
        user.demote_to_user()
        
        return format_response(
            success=True,
            data={
                'user': user.to_dict(include_sensitive=True),
                'message': f'User {user.username} demoted to regular user'
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to demote user: {str(e)}',
            status_code=500
        )


@admin_bp.route('/users/<user_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_user(user_id):
    """Deactivate user account"""
    try:
        user = User.get_by_id(user_id)
        if not user:
            return format_response(
                success=False,
                error='User not found',
                status_code=404
            )
        
        if not user.is_active:
            return format_response(
                success=False,
                error='User is already deactivated',
                status_code=400
            )
        
        # Prevent self-deactivation
        if user.id == current_user.id:
            return format_response(
                success=False,
                error='Cannot deactivate yourself',
                status_code=400
            )
        
        user.deactivate()
        
        return format_response(
            success=True,
            data={
                'user': user.to_dict(include_sensitive=True),
                'message': f'User {user.username} deactivated'
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to deactivate user: {str(e)}',
            status_code=500
        )


@admin_bp.route('/users/<user_id>/activate', methods=['POST'])
@admin_required
def activate_user(user_id):
    """Activate user account"""
    try:
        user = User.get_by_id(user_id)
        if not user:
            return format_response(
                success=False,
                error='User not found',
                status_code=404
            )
        
        if user.is_active:
            return format_response(
                success=False,
                error='User is already active',
                status_code=400
            )
        
        user.activate()
        
        return format_response(
            success=True,
            data={
                'user': user.to_dict(include_sensitive=True),
                'message': f'User {user.username} activated'
            }
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to activate user: {str(e)}',
            status_code=500
        )


@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    """Create a new user (admin only)"""
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
        role = data.get('role', 'user').lower()
        
        # Validate required fields
        if not username or not email or not password:
            return format_response(
                success=False,
                error='Username, email, and password are required',
                status_code=400
            )
        
        # Validate role
        if role not in ['user', 'admin']:
            return format_response(
                success=False,
                error='Role must be either "user" or "admin"',
                status_code=400
            )
        
        # Validate inputs
        username_valid, username_error = validate_username(username)
        if not username_valid:
            return format_response(success=False, error=username_error, status_code=400)
        
        email_valid, email_error = validate_email(email)
        if not email_valid:
            return format_response(success=False, error=email_error, status_code=400)
        
        password_valid, password_error = validate_password(password)
        if not password_valid:
            return format_response(success=False, error=password_error, status_code=400)
        
        # Create user
        user_role = UserRole.ADMIN if role == 'admin' else UserRole.USER
        user = User.create_user(
            username=username,
            email=email,
            password=password,
            role=user_role
        )
        
        return format_response(
            success=True,
            data={
                'user': user.to_dict(include_sensitive=True),
                'message': f'User {username} created successfully'
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
            error=f'Failed to create user: {str(e)}',
            status_code=500
        )


@admin_bp.route('/stats', methods=['GET'])
@admin_required
def get_system_stats():
    """Get system statistics (admin only)"""
    try:
        # User statistics
        all_users = User.get_all_users()
        active_users = [u for u in all_users if u.is_active]
        admin_users = [u for u in all_users if u.is_admin()]
        
        # Conversation statistics
        all_conversations = Conversation.get_all()
        
        # Recent activity (last 7 days)
        from datetime import timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_conversations = [c for c in all_conversations if c.created_at >= week_ago]
        recent_users = [u for u in all_users if u.created_at >= week_ago]
        
        stats = {
            'users': {
                'total': len(all_users),
                'active': len(active_users),
                'inactive': len(all_users) - len(active_users),
                'admins': len(admin_users),
                'regular_users': len(all_users) - len(admin_users),
                'recent_registrations': len(recent_users)
            },
            'conversations': {
                'total': len(all_conversations),
                'recent': len(recent_conversations),
                'average_per_user': round(len(all_conversations) / max(len(active_users), 1), 2)
            },
            'system': {
                'current_admin': current_user.username,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        }
        
        return format_response(
            success=True,
            data={'stats': stats}
        )
        
    except Exception as e:
        return format_response(
            success=False,
            error=f'Failed to get system stats: {str(e)}',
            status_code=500
        )