from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

# Build connection string from environment variables
SUPABASE_USER = os.getenv("SUPABASE_USER", "postgres")
SUPABASE_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD")
SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT", "5432")
SUPABASE_DB_NAME = os.getenv("SUPABASE_DB_NAME", "postgres")

# Construct the DATABASE_URL
DATABASE_URL = f"postgresql://{SUPABASE_USER}:{SUPABASE_PASSWORD}@{SUPABASE_HOST}:{SUPABASE_PORT}/{SUPABASE_DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False
