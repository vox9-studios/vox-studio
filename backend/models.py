from sqlalchemy import Column, String, Text, Boolean, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class AuthorProfile(Base):
    __tablename__ = "author_profiles"
    
    user_id = Column(UUID(as_uuid=True), primary_key=True)
    display_name = Column(String(255), nullable=False)
    bio = Column(Text)
    avatar_url = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Playlist(Base):
    __tablename__ = "playlists"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id = Column(UUID(as_uuid=True), ForeignKey("author_profiles.user_id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    cover_image_url = Column(Text)
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Episode(Base):
    __tablename__ = "episodes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playlist_id = Column(UUID(as_uuid=True), ForeignKey("playlists.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    audio_url = Column(Text, nullable=False)
    vtt_url = Column(Text)
    duration_seconds = Column(Float)
    episode_number = Column(Integer, nullable=False)
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
