from sqlalchemy import Column, String, Text, Boolean, Integer, Float, DateTime, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, date
import uuid

Base = declarative_base()

class AuthorProfile(Base):
    """Author/creator profile"""
    __tablename__ = "author_profiles"
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auth_user_id = Column(UUID(as_uuid=True))
    username = Column(String(50), unique=True)  # NEW
    display_name = Column(String(100))  # NEW
    bio = Column(Text)  # NEW
    avatar_url = Column(Text)  # NEW
    website_url = Column(Text)  # NEW
    
    # Existing fields:
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    credits_used = Column(Integer, default=0)
    credits_limit = Column(Integer, default=50000)
    subscriber_count = Column(Integer, default=0)
    last_credit_reset = Column(Date)
    
    # Credit tracking columns
    credits_used = Column(Integer, default=0)
    credits_limit = Column(Integer, default=50000)
    last_credit_reset = Column(Date, default=date.today)

class Subscription(Base):
    """Subscription model - tracks fan subscriptions to authors"""
    __tablename__ = "subscriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Who is subscribing (fan)
    subscriber_user_id = Column(UUID(as_uuid=True), ForeignKey('author_profiles.user_id'), nullable=False)
    
    # Who they're subscribing to (author)
    author_user_id = Column(UUID(as_uuid=True), ForeignKey('author_profiles.user_id'), nullable=False)
    
    # Stripe data
    stripe_subscription_id = Column(String, unique=True, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    
    # Subscription status
    status = Column(String, default='active', nullable=False)
    
    # Pricing
    amount_cents = Column(Integer, default=250, nullable=False)
    currency = Column(String, default='usd', nullable=False)
    
    # Billing period
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    
class Playlist(Base):
    __tablename__ = "playlists"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id = Column(UUID(as_uuid=True), ForeignKey("author_profiles.user_id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    cover_image_url = Column(Text)
    is_published = Column(Boolean, default=False)
    episode_count = Column(Integer, default=0)
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

class GenerationJob(Base):
    """Generation jobs for AI narration"""
    __tablename__ = "generation_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id = Column(UUID(as_uuid=True), ForeignKey("author_profiles.user_id"), nullable=False)
    
    # Episode metadata
    episode_title = Column(String(500))
    episode_description = Column(Text)
    cover_square_url = Column(Text)      # 1:1 (1400x1400) for podcasts
    cover_mobile_url = Column(Text)      # 9:16 (1080x1920) for social media  
    cover_widescreen_url = Column(Text)  # 16:9 (1920x1080) for video
    is_published = Column(Boolean, default=False)
    is_free = Column(Boolean, default=False)
    playlist_id = Column(UUID(as_uuid=True), ForeignKey("playlists.id"))
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    # Input
    input_text = Column(Text, nullable=False)
    voice_id = Column(String(255), nullable=False)
    voice_name = Column(String(255))
    model_id = Column(String(255), default="eleven_monolingual_v1")
    
    # Voice settings
    stability = Column(Float, default=0.5)
    similarity_boost = Column(Float, default=0.75)
    speaking_rate = Column(Float, default=1.0)
    
    # Caption settings
    caption_lead_in = Column(Integer, default=50)
    caption_lead_out = Column(Integer, default=120)
    caption_gap = Column(Integer, default=150)
    
    # Status
    status = Column(String(50), default="queued")
    progress = Column(Integer, default=0)
    
    # Output URLs
    audio_url = Column(Text)
    vtt_url = Column(Text)
    
    # Error handling
    error_message = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

class Comment(Base):
    __tablename__ = "comments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    episode_id = Column(UUID(as_uuid=True), ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    author_name = Column(String(255), nullable=False)
    author_avatar_url = Column(Text)
    text = Column(Text, nullable=False)
    parent_comment_id = Column(UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"))
    like_count = Column(Integer, default=0)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CommentLike(Base):
    __tablename__ = "comment_likes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_id = Column(UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class EpisodeLike(Base):
    __tablename__ = "episode_likes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    episode_id = Column(UUID(as_uuid=True), ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class CommentReport(Base):
    __tablename__ = "comment_reports"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_id = Column(UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), nullable=False)
    reporter_id = Column(UUID(as_uuid=True), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime)
    reviewed_by = Column(UUID(as_uuid=True))

