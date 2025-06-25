import re
import secrets
from datetime import datetime


def validate_password(password):
    """
    Validate password strength
    Returns (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if len(password) > 128:
        return False, "Password must be less than 128 characters"
    
    # Check for at least one letter and one number
    if not re.search(r'[A-Za-z]', password):
        return False, "Password must contain at least one letter"
    
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    
    # Check for common weak passwords
    weak_passwords = [
        'password', '12345678', 'qwerty123', 'admin123', 
        'password123', '123456789', 'welcome123'
    ]
    
    if password.lower() in weak_passwords:
        return False, "Password is too common. Please choose a stronger password"
    
    return True, None


def validate_username(username):
    """
    Validate username format
    Returns (is_valid, error_message)
    """
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"
    
    if len(username) > 50:
        return False, "Username must be less than 50 characters"
    
    # Only allow alphanumeric characters and underscores
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    
    # Reserved usernames
    reserved_usernames = [
        'admin', 'root', 'administrator', 'system', 'api', 'test', 
        'guest', 'public', 'anonymous', 'null', 'undefined'
    ]
    
    if username.lower() in reserved_usernames:
        return False, "Username is reserved. Please choose a different username"
    
    return True, None


def validate_email(email):
    """
    Validate email format
    Returns (is_valid, error_message)
    """
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        return False, "Invalid email format"
    
    if len(email) > 120:
        return False, "Email address is too long"
    
    return True, None


def generate_session_token():
    """Generate a secure random session token"""
    return secrets.token_urlsafe(32)


def sanitize_user_input(input_str, max_length=255):
    """Sanitize user input to prevent basic injection attacks"""
    if not input_str:
        return ""
    
    # Remove null bytes and control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', str(input_str))
    
    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized.strip()


def format_user_error(message, field=None):
    """Format user validation error response"""
    error_response = {
        'success': False,
        'error': message,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    if field:
        error_response['field'] = field
    
    return error_response


def is_safe_redirect_url(target_url, allowed_hosts=None):
    """Check if a redirect URL is safe (prevents open redirect attacks)"""
    if not target_url:
        return False
    
    # Only allow relative URLs or URLs to allowed hosts
    if target_url.startswith('/'):
        return True
    
    if allowed_hosts:
        from urllib.parse import urlparse
        parsed = urlparse(target_url)
        return parsed.netloc in allowed_hosts
    
    return False