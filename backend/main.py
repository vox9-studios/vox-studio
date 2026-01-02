from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from database import test_connection, engine, get_db
from models import AuthorProfile, Playlist, Episode
from storage import upload_to_s3, test_s3_connection
from routes.narration import router as narration_router
from schemas import (
    AuthorProfileCreate, AuthorProfileRead,
    PlaylistCreate, PlaylistRead
)
from typing import List
import uuid
import time

app = FastAPI(title="Vox Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include narration router
app.include_router(narration_router, prefix="/api/narration", tags=["Narration"])  # ← ADD THIS

@app.get("/")
async def root():
    return {"message": "Vox Platform API", "status": "healthy"}

@app.get("/health")
async def health():
    # Quick health check - don't wait for slow connections
    db_connected = False
    s3_connected = False
    tables_exist = False
    
    try:
        # Try database with timeout
        db_connected = test_connection()
        
        # Only check tables if DB connected
        if db_connected:
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT COUNT(*) FROM information_schema.tables 
                        WHERE table_name IN ('author_profiles', 'playlists', 'episodes', 'comments', 'episode_stats')
                    """))
                    count = result.scalar()
                    tables_exist = count == 5
            except:
                tables_exist = False
    except:
        pass
    
    try:
        # Try S3
        s3_connected = test_s3_connection()
    except:
        pass
    
    return {
        "status": "ok",
        "database": "connected" if db_connected else "disconnected",
        "storage": "connected" if s3_connected else "disconnected",
        "tables": "ready" if tables_exist else "not initialized"
    }

# Author Endpoints
@app.post("/api/authors", response_model=AuthorProfileRead)
async def create_author(author: AuthorProfileCreate, db: Session = Depends(get_db)):
    """Create a new author profile"""
    db_author = AuthorProfile(**author.model_dump())
    db.add(db_author)
    db.commit()
    db.refresh(db_author)
    return db_author

@app.get("/api/authors", response_model=List[AuthorProfileRead])
async def list_authors(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """Get list of authors"""
    authors = db.query(AuthorProfile).offset(skip).limit(limit).all()
    return authors

@app.get("/api/authors/{author_id}", response_model=AuthorProfileRead)
async def get_author(author_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get specific author"""
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    return author

# Playlist Endpoints
@app.post("/api/playlists", response_model=PlaylistRead)
async def create_playlist(playlist: PlaylistCreate, db: Session = Depends(get_db)):
    """Create a new playlist"""
    # Verify author exists
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == playlist.author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    db_playlist = Playlist(**playlist.model_dump())
    db.add(db_playlist)
    db.commit()
    db.refresh(db_playlist)
    
    # Return with episode count
    result = PlaylistRead.model_validate(db_playlist)
    result.episode_count = 0
    return result

@app.get("/api/playlists", response_model=List[PlaylistRead])
async def list_playlists(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """Get list of published playlists"""
    playlists = db.query(
        Playlist,
        func.count(Episode.id).label("episode_count")
    ).outerjoin(Episode).filter(
        Playlist.is_published == True
    ).group_by(Playlist.id).offset(skip).limit(limit).all()
    
    results = []
    for playlist, count in playlists:
        p = PlaylistRead.model_validate(playlist)
        p.episode_count = count
        results.append(p)
    return results

@app.get("/api/playlists/{playlist_id}", response_model=PlaylistRead)
async def get_playlist(playlist_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get specific playlist"""
    result = db.query(
        Playlist,
        func.count(Episode.id).label("episode_count")
    ).outerjoin(Episode).filter(
        Playlist.id == playlist_id
    ).group_by(Playlist.id).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    playlist, count = result
    p = PlaylistRead.model_validate(playlist)
    p.episode_count = count
    return p

# File Upload Endpoints
@app.post("/api/upload/test")
async def test_upload(file: UploadFile = File(...)):
    """Test file upload to S3"""
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Generate test S3 key
    s3_key = f"vox-platform/test/{file.filename}"
    
    url = await upload_to_s3(file, s3_key)
    
    return {
        "filename": file.filename,
        "url": url,
        "s3_key": s3_key
    }

@app.post("/api/upload/simple")
async def simple_upload(file: UploadFile = File(...)):
    """Simple file upload to S3 - no database needed"""
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Generate S3 key with timestamp
    timestamp = int(time.time())
    s3_key = f"vox-platform/test/{timestamp}_{file.filename}"
    
    try:
        url = await upload_to_s3(file, s3_key)
        return {
            "success": True,
            "filename": file.filename,
            "url": url,
            "s3_key": s3_key
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
