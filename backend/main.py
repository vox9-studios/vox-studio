from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import test_connection, engine
from sqlalchemy import text

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
