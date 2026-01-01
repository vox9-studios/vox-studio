from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import test_connection, engine, get_db
from models import AuthorProfile
from schemas import AuthorProfileCreate, AuthorProfileRead
from typing import List
import uuid

app = FastAPI(title="Vox Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Vox Platform API", "status": "healthy"}

@app.get("/health")
async def health():
    db_connected = test_connection()
    
    # Check if tables exist
    tables_exist = False
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
    
    return {
        "status": "ok",
        "database": "connected" if db_connected else "disconnected",
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
