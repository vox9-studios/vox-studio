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
