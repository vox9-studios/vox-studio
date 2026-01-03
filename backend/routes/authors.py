# backend/routes/authors.py
"""
Author management routes
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import uuid

from database import get_db
from models import AuthorProfile
from auth import get_current_user

router = APIRouter(prefix="/api/authors", tags=["authors"])


class AuthorCreateRequest(BaseModel):
    auth_user_id: str
    username: str
    display_name: str
    email: str


class AuthorResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
    email: str
    bio: Optional[str]
    avatar_url: Optional[str]
    website_url: Optional[str]
    credits_used: int
    credits_limit: int


@router.post("/create")
async def create_author_profile(
    request: AuthorCreateRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create author profile after Supabase signup"""
    
    # Verify the auth_user_id matches the authenticated user
    if current_user.id != request.auth_user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    # Check if username is already taken
    existing_username = db.query(AuthorProfile).filter(
        AuthorProfile.username == request.username
    ).first()
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Check if profile already exists for this auth user
    existing_profile = db.query(AuthorProfile).filter(
        AuthorProfile.auth_user_id == request.auth_user_id
    ).first()
    if existing_profile:
        raise HTTPException(status_code=400, detail="Profile already exists")
    
    # Create author profile
    author = AuthorProfile(
        user_id=uuid.uuid4(),
        auth_user_id=request.auth_user_id,
        username=request.username,
        display_name=request.display_name,
        email=request.email,
        credits_used=0,
        credits_limit=50000  # 50k free credits per month
    )
    
    db.add(author)
    db.commit()
    db.refresh(author)
    
    return {
        "success": True,
        "user_id": str(author.user_id),
        "username": author.username
    }


@router.get("/me")
async def get_my_profile(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's author profile"""
    author = db.query(AuthorProfile).filter(
        AuthorProfile.auth_user_id == current_user.id
    ).first()
    
    if not author:
        raise HTTPException(status_code=404, detail="Author profile not found")
    
    return AuthorResponse(
        user_id=str(author.user_id),
        username=author.username,
        display_name=author.display_name,
        email=author.email,
        bio=author.bio,
        avatar_url=author.avatar_url,
        website_url=author.website_url,
        credits_used=author.credits_used,
        credits_limit=author.credits_limit
    )


@router.get("/{username}")
async def get_author_by_username(
    username: str,
    db: Session = Depends(get_db)
):
    """Get public author profile by username"""
    author = db.query(AuthorProfile).filter(
        AuthorProfile.username == username
    ).first()
    
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    return AuthorResponse(
        user_id=str(author.user_id),
        username=author.username,
        display_name=author.display_name,
        email=author.email,
        bio=author.bio,
        avatar_url=author.avatar_url,
        website_url=author.website_url,
        credits_used=0,  # Don't expose
        credits_limit=0  # Don't expose
    )


@router.get("/")
async def list_all_authors(db: Session = Depends(get_db)):
    """List all authors (for browse page)"""
    authors = db.query(AuthorProfile).all()
    
    return [
        {
            "user_id": str(author.user_id),
            "username": author.username,
            "display_name": author.display_name,
            "bio": author.bio,
            "avatar_url": author.avatar_url
        }
        for author in authors
    ]
