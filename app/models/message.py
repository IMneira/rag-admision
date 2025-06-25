from datetime import datetime
from app.db import flask_db as db
from sqlalchemy import String, Text, JSON
import uuid
import json


class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = db.Column(String(36), db.ForeignKey('conversations.id'), nullable=False)
    question = db.Column(Text, nullable=False)
    response = db.Column(Text, nullable=False)
    sources = db.Column(Text, nullable=True)  # JSON string of source URLs
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def __init__(self, conversation_id, question, response, sources=None):
        self.conversation_id = conversation_id
        self.question = question
        self.response = response
        self.sources = json.dumps(sources) if sources else None
    
    def get_sources(self):
        """Get sources as a list"""
        if self.sources:
            try:
                return json.loads(self.sources)
            except json.JSONDecodeError:
                return []
        return []
    
    def set_sources(self, sources):
        """Set sources from a list"""
        self.sources = json.dumps(sources) if sources else None
    
    def to_dict(self):
        """Convert message to dictionary for API responses"""
        return {
            'id': self.id,
            'question': self.question,
            'response': self.response,
            'sources': self.get_sources(),
            'timestamp': self.timestamp.isoformat() + 'Z'
        }
    
    @staticmethod
    def create_message(conversation_id, question, response, sources=None):
        """Create a new message"""
        message = Message(
            conversation_id=conversation_id,
            question=question,
            response=response,
            sources=sources
        )
        db.session.add(message)
        
        # Update conversation timestamp
        from app.models.conversation import Conversation
        conversation = Conversation.get_by_id(conversation_id)
        if conversation:
            conversation.update_timestamp()
        
        db.session.commit()
        return message
    
    @staticmethod
    def get_by_conversation(conversation_id):
        """Get all messages for a conversation ordered by timestamp"""
        return Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp.asc()).all()
    
    @staticmethod
    def get_by_id(message_id):
        """Get message by ID"""
        return Message.query.filter_by(id=message_id).first()
    
    def delete(self):
        """Delete message"""
        db.session.delete(self)
        db.session.commit()
    
    def __repr__(self):
        return f'<Message {self.id}: {self.question[:50]}...>'