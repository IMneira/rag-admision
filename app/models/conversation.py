from datetime import datetime
from app.db import flask_db as db
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String
import uuid


class Conversation(db.Model):
    __tablename__ = 'conversations'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    title = db.Column(db.String(255), nullable=True)
    user_id = db.Column(String(36), db.ForeignKey('users.id'), nullable=True)  # Nullable for backward compatibility
    
    # Conversational memory fields
    summary = db.Column(db.Text, nullable=True)  # Conversation summary for memory optimization
    total_turns = db.Column(db.Integer, nullable=False, default=0)  # Track total conversation turns
    
    # Relationship with messages
    messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, title=None, user_id=None):
        self.title = title
        self.user_id = user_id
        self.total_turns = 0
    
    def to_dict(self):
        """Convert conversation to dictionary for API responses"""
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() + 'Z',
            'updated_at': self.updated_at.isoformat() + 'Z',
            'title': self.title,
            'user_id': self.user_id,
            'message_count': len(self.messages),
            'total_turns': self.total_turns,
            'has_summary': bool(self.summary),
            'last_message': self.messages[-1].timestamp.isoformat() + 'Z' if self.messages else None
        }
    
    def to_dict_with_messages(self):
        """Convert conversation with all messages to dictionary"""
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() + 'Z',
            'updated_at': self.updated_at.isoformat() + 'Z',
            'title': self.title,
            'user_id': self.user_id,
            'messages': [message.to_dict() for message in self.messages]
        }
    
    @staticmethod
    def create_conversation(title=None, user_id=None):
        """Create a new conversation"""
        conversation = Conversation(title=title, user_id=user_id)
        db.session.add(conversation)
        db.session.commit()
        return conversation
    
    @staticmethod
    def get_by_id(conversation_id):
        """Get conversation by ID"""
        return Conversation.query.filter_by(id=conversation_id).first()
    
    @staticmethod
    def get_all():
        """Get all conversations ordered by updated_at descending"""
        return Conversation.query.order_by(Conversation.updated_at.desc()).all()
    
    @staticmethod
    def get_by_user(user_id):
        """Get all conversations for a specific user"""
        return Conversation.query.filter_by(user_id=user_id).order_by(Conversation.updated_at.desc()).all()
    
    @staticmethod
    def get_by_id_and_user(conversation_id, user_id):
        """Get conversation by ID and user ID (for access control)"""
        return Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
    
    def delete(self):
        """Delete conversation and all its messages"""
        db.session.delete(self)
        db.session.commit()
    
    def update_timestamp(self):
        """Update the updated_at timestamp"""
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def update_summary(self, summary: str):
        """Update conversation summary"""
        self.summary = summary
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def increment_turns(self):
        """Increment total turns counter"""
        self.total_turns += 1
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<Conversation {self.id}: {self.title or "Untitled"}>'