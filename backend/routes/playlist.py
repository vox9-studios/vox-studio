"""
Playlist API routes
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

from database import get_db
from models import AuthorProfile, Playlist
from s3_client import upload_to_s3

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


class PlaylistCreate(BaseModel):
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    is_published: bool = False


class PlaylistUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    is_published: Optional[bool] = None


class PlaylistResponse(BaseModel):
    id: str
    author_id: str
    title: str
    description: Optional[str]
    cover_image_url: Optional[str]
    is_published: bool
    created_at: str
    updated_at: str
    episode_count: int = 0

    class Config:
        from_attributes = True


@router.post("/{author_id}", response_model=PlaylistResponse)
async def create_playlist(
    author_id: str,
    playlist: PlaylistCreate,
    db: Session = Depends(get_db)
):
    """Create a new playlist"""
    # Validate author exists
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Generate default cover if none provided
    cover_url = playlist.cover_image_url
    if not cover_url:
        # Generate a default cover URL based on title
        # This will be a placeholder that the frontend can render as a colored tile
        cover_url = f"default://playlist/{uuid.uuid4()}"
    
    # Create playlist
    new_playlist = Playlist(
        id=uuid.uuid4(),
        author_id=author_id,
        title=playlist.title,
        description=playlist.description,
        cover_image_url=cover_url,
        is_published=playlist.is_published
    )
    
    db.add(new_playlist)
    db.commit()
    db.refresh(new_playlist)
    
    return PlaylistResponse(
        id=str(new_playlist.id),
        author_id=str(new_playlist.author_id),
        title=new_playlist.title,
        description=new_playlist.description,
        cover_image_url=new_playlist.cover_image_url,
        is_published=new_playlist.is_published,
        created_at=new_playlist.created_at.isoformat(),
        updated_at=new_playlist.updated_at.isoformat(),
        episode_count=0
    )


@router.get("/{author_id}", response_model=List[PlaylistResponse])
async def get_author_playlists(
    author_id: str,
    db: Session = Depends(get_db)
):
    """Get all playlists for an author"""
    # Validate author exists
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Get playlists
    from models import GenerationJob  # CHANGED: Use GenerationJob instead of Episode
    playlists = db.query(Playlist).filter(Playlist.author_id == author_id).all()
    
    # Use episode_count from database column (updated by trigger)
    result = []
    for playlist in playlists:
        result.append(PlaylistResponse(
            id=str(playlist.id),
            author_id=str(playlist.author_id),
            title=playlist.title,
            description=playlist.description,
            cover_image_url=playlist.cover_image_url,
            is_published=playlist.is_published,
            created_at=playlist.created_at.isoformat(),
            updated_at=playlist.updated_at.isoformat(),
            episode_count=playlist.episode_count or 0  # CHANGED: Use database column
        ))
    
    return result


@router.get("/detail/{playlist_id}", response_model=PlaylistResponse)
async def get_playlist(
    playlist_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific playlist"""
    
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    episode_count = playlist.episode_count or 0  # ✅ CORRECT
    
    return PlaylistResponse(
        id=str(playlist.id),
        author_id=str(playlist.author_id),
        title=playlist.title,
        description=playlist.description,
        cover_image_url=playlist.cover_image_url,
        is_published=playlist.is_published,
        created_at=playlist.created_at.isoformat(),
        updated_at=playlist.updated_at.isoformat(),
        episode_count=episode_count
    )


@router.patch("/{playlist_id}", response_model=PlaylistResponse)
async def update_playlist(
    playlist_id: str,
    updates: PlaylistUpdate,
    db: Session = Depends(get_db)
):
    """Update a playlist"""
    
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Update fields
    if updates.title is not None:
        playlist.title = updates.title
    if updates.description is not None:
        playlist.description = updates.description
    if updates.cover_image_url is not None:
        playlist.cover_image_url = updates.cover_image_url
    if updates.is_published is not None:
        playlist.is_published = updates.is_published
    
    playlist.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(playlist)
    
    episode_count = db.query(Episode).filter(Episode.playlist_id == playlist.id).count()
    
    return PlaylistResponse(
        id=str(playlist.id),
        author_id=str(playlist.author_id),
        title=playlist.title,
        description=playlist.description,
        cover_image_url=playlist.cover_image_url,
        is_published=playlist.is_published,
        created_at=playlist.created_at.isoformat(),
        updated_at=playlist.updated_at.isoformat(),
        episode_count=episode_count
    )


@router.delete("/{playlist_id}")
async def delete_playlist(
    playlist_id: str,
    db: Session = Depends(get_db)
):
    """Delete a playlist (only if it has no episodes)"""
    
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Check if playlist has episodes
    episode_count = db.query(Episode).filter(Episode.playlist_id == playlist.id).count()
    if episode_count > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete playlist with {episode_count} episodes. Delete episodes first."
        )
    
    db.delete(playlist)
    db.commit()
    
    return {"success": True, "message": "Playlist deleted"}


@router.post("/upload-cover/{playlist_id}")
async def upload_playlist_cover(
    playlist_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload cover image for playlist"""
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Validate file type
    if file.content_type not in ["image/jpeg", "image/jpg", "image/png"]:
        raise HTTPException(status_code=400, detail="Only JPG and PNG allowed")
    
    # Validate size (max 5MB)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")
    
    await file.seek(0)
    
    # Generate S3 key
    file_ext = "jpg" if file.content_type == "image/jpeg" else "png"
    image_id = str(uuid.uuid4())
    s3_key = f"vox-platform/playlists/{playlist.author_id}/{playlist_id}/{image_id}.{file_ext}"
    
    # Upload to S3
    from storage import upload_to_s3 as storage_upload
    url = await storage_upload(file, s3_key)
    
    # Update playlist
    playlist.cover_image_url = url
    playlist.updated_at = datetime.utcnow()
    db.commit()
    
    return {"success": True, "url": url}
