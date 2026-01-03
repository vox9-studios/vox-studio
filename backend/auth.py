# backend/auth.py
"""
Supabase authentication middleware
"""
from fastapi import Depends, HTTPException, Header
from supabase import create_client, Client
import os
from typing import Optional

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


async def get_current_user(authorization: str = Header(None)):
    """Get current authenticated user from JWT token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Extract token from "Bearer <token>"
        token = authorization.replace("Bearer ", "")
        
        # Verify token with Supabase
        response = supabase.auth.get_user(token)
        
        if not response or not response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return response.user
        
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


async def get_optional_user(authorization: str = Header(None)) -> Optional[dict]:
    """Get user if authenticated, None otherwise (for public endpoints)"""
    if not authorization:
        return None
    
    try:
        token = authorization.replace("Bearer ", "")
        response = supabase.auth.get_user(token)
        return response.user if response else None
    except:
        return None
