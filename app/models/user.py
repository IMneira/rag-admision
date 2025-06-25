from datetime import datetime
from app.db import flask_db as db
from sqlalchemy import String, Enum
from flask_login import UserMixin
from flask_bcrypt import generate_password_hash, check_password_hash
import uuid
import enum


class UserRole(enum.Enum):
    USER = "user"
    ADMIN = "admin"


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(Enum(UserRole), nullable=False, default=UserRole.USER)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Relationship with conversations
    conversations = db.relationship('Conversation', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, username, email, password, role=UserRole.USER):
        self.username = username
        self.email = email
        self.set_password(password)
        self.role = role
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        """Check if user has admin role"""
        return self.role == UserRole.ADMIN
    
    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def to_dict(self, include_sensitive=False):
        """Convert user to dictionary for API responses"""
        user_dict = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role.value,
            'created_at': self.created_at.isoformat() + 'Z',
            'is_active': self.is_active,
            'last_login': self.last_login.isoformat() + 'Z' if self.last_login else None,
            'conversation_count': len(self.conversations)
        }
        
        if include_sensitive:
            # Include additional info for admin or self queries
            user_dict['email'] = self.email
            
        return user_dict
    
    @staticmethod
    def create_user(username, email, password, role=UserRole.USER):
        """Create a new user"""
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            raise ValueError("Username already exists")
        if User.query.filter_by(email=email).first():
            raise ValueError("Email already exists")
        
        user = User(username=username, email=email, password=password, role=role)
        db.session.add(user)
        db.session.commit()
        return user
    
    @staticmethod
    def get_by_id(user_id):
        """Get user by ID"""
        return User.query.filter_by(id=user_id).first()
    
    @staticmethod
    def get_by_username(username):
        """Get user by username"""
        return User.query.filter_by(username=username).first()
    
    @staticmethod
    def get_by_email(email):
        """Get user by email"""
        return User.query.filter_by(email=email).first()
    
    @staticmethod
    def get_all_users():
        """Get all users (admin function)"""
        return User.query.order_by(User.created_at.desc()).all()
    
    @staticmethod
    def authenticate(username_or_email, password):
        """Authenticate user with username/email and password"""
        # Try to find user by username first, then email
        user = User.query.filter_by(username=username_or_email).first()
        if not user:
            user = User.query.filter_by(email=username_or_email).first()
        
        if user and user.is_active and user.check_password(password):
            user.update_last_login()
            return user
        return None
    
    def deactivate(self):
        """Deactivate user account"""
        self.is_active = False
        db.session.commit()
    
    def activate(self):
        """Activate user account"""
        self.is_active = True
        db.session.commit()
    
    def promote_to_admin(self):
        """Promote user to admin role"""
        self.role = UserRole.ADMIN
        db.session.commit()
    
    def demote_to_user(self):
        """Demote admin to user role"""
        self.role = UserRole.USER
        db.session.commit()
    
    def change_password(self, old_password, new_password):
        """Change user password"""
        if not self.check_password(old_password):
            raise ValueError("Current password is incorrect")
        
        self.set_password(new_password)
        db.session.commit()
    
    def __repr__(self):
        return f'<User {self.username} ({self.role.value})>'


def create_admin_user(username, email, password):
    """Helper function to create admin user during setup"""
    try:
        admin = User.create_user(
            username=username,
            email=email,
            password=password,
            role=UserRole.ADMIN
        )
        return admin
    except ValueError as e:
        # User might already exist
        existing_user = User.get_by_username(username)
        if existing_user and not existing_user.is_admin():
            existing_user.promote_to_admin()
            return existing_user
        raise e