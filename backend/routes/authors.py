# backend/routes/authors.py
"""
Author management routes
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import os
from s3_client import s3_client, BUCKET_NAME
from database import get_db
from models import AuthorProfile
from auth import get_current_user

router = APIRouter(prefix="/api/authors", tags=["authors"])


class AuthorCreateRequest(BaseModel):
    auth_user_id: str
    username: str
    display_name: str

class AuthorResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
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

@router.patch("/{author_id}")
async def update_author_profile(
    author_id: str,
    request: dict,
    db: Session = Depends(get_db)
):
    """Update author profile (display name, bio, website)"""
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Update fields if provided
    if 'display_name' in request:
        author.display_name = request['display_name']
    
    if 'bio' in request:
        author.bio = request['bio']
    
    if 'website_url' in request:
        author.website_url = request['website_url']
    
    if 'avatar_url' in request:
        author.avatar_url = request['avatar_url']
    
    author.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(author)
    
    return {
        "success": True,
        "message": "Profile updated successfully",
        "author": {
            "display_name": author.display_name,
            "bio": author.bio,
            "website_url": author.website_url,
            "avatar_url": author.avatar_url
        }
    }

@router.post("/upload-avatar/{author_id}")
async def upload_avatar(
    author_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload author avatar image"""
    
    # Validate author
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Validate file type
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are supported")
    
    # Validate file size (max 5MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")
    
    try:
        # Generate unique filename
        file_id = str(uuid.uuid4())
        extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        s3_key = f"vox-platform/avatars/{author_id}/{file_id}.{extension}"
        
        # Upload to S3
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=contents,
            ContentType=file.content_type
        )
        
        # Get public URL
        avatar_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION', 'eu-west-2')}.amazonaws.com/{s3_key}"
        
        # Update author profile with new avatar
        author.avatar_url = avatar_url
        author.updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "avatar_url": avatar_url
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
        
@router.delete("/{author_id}/delete-account")
async def delete_account(
    author_id: str,
    db: Session = Depends(get_db)
):
    """Delete entire account - profile, episodes, playlists, and all S3 files"""
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    try:
        from s3_client import s3_client, BUCKET_NAME
        
        # Delete ALL S3 files for this author
        prefixes = [
            f"vox-platform/avatars/{author_id}/",
            f"vox-platform/covers/{author_id}/",
            f"vox-platform/uploads/{author_id}/",
            f"vox-platform/captions/{author_id}/",
            f"vox-platform/generations/{author_id}/"
        ]
        
        for prefix in prefixes:
            try:
                # List all objects with this prefix
                response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
                
                if 'Contents' in response:
                    # Delete all objects
                    objects = [{'Key': obj['Key']} for obj in response['Contents']]
                    if objects:
                        s3_client.delete_objects(
                            Bucket=BUCKET_NAME,
                            Delete={'Objects': objects}
                        )
                        print(f"Deleted {len(objects)} files from {prefix}")
            except Exception as e:
                print(f"Error deleting S3 prefix {prefix}: {e}")
        
        # Delete all episodes
        db.query(GenerationJob).filter(GenerationJob.author_id == author_id).delete()
        
        # Delete all playlists
        from models import Playlist
        db.query(Playlist).filter(Playlist.author_id == author_id).delete()
        
        # Delete author profile
        db.delete(author)
        db.commit()
        
        return {
            "success": True,
            "message": "Account deleted successfully"
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")

@router.get("/by-id/{user_id}")
async def get_author_by_id(user_id: str, db: Session = Depends(get_db)):
    """Get author profile by user ID"""
    
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == user_id).first()
    
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    return {
        "user_id": str(author.user_id),
        "username": author.username,
        "display_name": author.display_name,
        "bio": author.bio,
        "avatar_url": author.avatar_url,
        "website_url": author.website_url
    }
    
