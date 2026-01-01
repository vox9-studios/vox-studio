from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid as uuid_pkg

class AuthorProfileCreate(BaseModel):
    user_id: uuid_pkg.UUID
    display_name: str
    bio: Optional[str] = None

class AuthorProfileRead(BaseModel):
    user_id: uuid_pkg.UUID
    display_name: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# Add these new playlist schemas:
class PlaylistCreate(BaseModel):
    title: str
    description: Optional[str] = None
    author_id: uuid_pkg.UUID
    is_published: bool = False

class PlaylistRead(BaseModel):
    id: uuid_pkg.UUID
    author_id: uuid_pkg.UUID
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    is_published: bool
    created_at: datetime
    episode_count: int = 0
    
    class Config:
        from_attributes = True
