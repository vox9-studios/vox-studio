"""
Narration generation routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
import uuid as uuid_pkg
from datetime import datetime, date

from database import get_db
from models import AuthorProfile
from elevenlabs_client import get_available_voices, test_api_key
from sqlalchemy import text

router = APIRouter()


# Pydantic models for API
class VoiceInfo(BaseModel):
    voice_id: str
    name: str
    preview_url: Optional[str] = None
    description: Optional[str] = None
    category: str = "generated"


class GenerateRequest(BaseModel):
    text: str
    voice_id: str
    voice_name: Optional[str] = None
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
    use_speaker_boost: bool = True
    speaking_rate: float = 1.0
    caption_lead_in: int = 50
    caption_lead_out: int = 100
    caption_gap: int = 100


class GenerationJobResponse(BaseModel):
    id: UUID
    author_id: UUID
    character_count: int
    status: str
    progress: int
    audio_url: Optional[str] = None
    vtt_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class CreditStatus(BaseModel):
    credits_used: int
    credits_limit: int
    credits_remaining: int
    last_reset: date


# Routes
@router.get("/voices", response_model=List[VoiceInfo])
async def list_voices():
    """Get list of available ElevenLabs voices"""
    voices = get_available_voices()
    return voices


@router.get("/test-api")
async def test_elevenlabs_api():
    """Test if ElevenLabs API key is working"""
    is_valid = test_api_key()
    return {
        "api_key_valid": is_valid,
        "message": "API key is valid" if is_valid else "API key is invalid or not set"
    }


@router.get("/credits/{author_id}", response_model=CreditStatus)
async def get_credits(author_id: UUID, db: Session = Depends(get_db)):
    """Get credit status for an author"""
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Check if credits need to be reset (monthly)
    today = date.today()
    if author.last_credit_reset.month != today.month or author.last_credit_reset.year != today.year:
        # Reset credits for new month
        author.credits_used = 0
        author.last_credit_reset = today
        db.commit()
        db.refresh(author)
    
    credits_remaining = author.credits_limit - author.credits_used
    
    return CreditStatus(
        credits_used=author.credits_used,
        credits_limit=author.credits_limit,
        credits_remaining=credits_remaining,
        last_reset=author.last_credit_reset
    )


@router.post("/generate/{author_id}", response_model=GenerationJobResponse)
async def create_generation_job(
    author_id: UUID,
    request: GenerateRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new generation job (queued for processing)
    This endpoint creates the job but doesn't process it yet
    """
    # Verify author exists
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Check credits
    character_count = len(request.text)
    
    # Reset credits if needed
    today = date.today()
    if author.last_credit_reset.month != today.month or author.last_credit_reset.year != today.year:
        author.credits_used = 0
        author.last_credit_reset = today
        db.commit()
    
    credits_remaining = author.credits_limit - author.credits_used
    
    if character_count > credits_remaining:
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient credits. Need {character_count}, have {credits_remaining}"
        )
    
    # Create generation job
    job_id = uuid_pkg.uuid4()
    
    insert_query = text("""
        INSERT INTO generation_jobs (
            id, author_id, input_text, character_count, voice_id, voice_name,
            stability, similarity_boost, style, use_speaker_boost, speaking_rate,
            caption_lead_in, caption_lead_out, caption_gap,
            status, progress
        ) VALUES (
            :id, :author_id, :input_text, :character_count, :voice_id, :voice_name,
            :stability, :similarity_boost, :style, :use_speaker_boost, :speaking_rate,
            :caption_lead_in, :caption_lead_out, :caption_gap,
            'queued', 0
        )
    """)
    
    db.execute(insert_query, {
        "id": str(job_id),
        "author_id": str(author_id),
        "input_text": request.text,
        "character_count": character_count,
        "voice_id": request.voice_id,
        "voice_name": request.voice_name,
        "stability": request.stability,
        "similarity_boost": request.similarity_boost,
        "style": request.style,
        "use_speaker_boost": request.use_speaker_boost,
        "speaking_rate": request.speaking_rate,
        "caption_lead_in": request.caption_lead_in,
        "caption_lead_out": request.caption_lead_out,
        "caption_gap": request.caption_gap
    })
    
    db.commit()
    
    # Get the created job
    select_query = text("SELECT * FROM generation_jobs WHERE id = :id")
    result = db.execute(select_query, {"id": str(job_id)}).fetchone()
    
    return GenerationJobResponse(
        id=result.id,
        author_id=result.author_id,
        character_count=result.character_count,
        status=result.status,
        progress=result.progress,
        audio_url=result.audio_url,
        vtt_url=result.vtt_url,
        error_message=result.error_message,
        created_at=result.created_at
    )


@router.get("/job/{job_id}", response_model=GenerationJobResponse)
async def get_job_status(job_id: UUID, db: Session = Depends(get_db)):
    """Get status of a generation job"""
    query = text("SELECT * FROM generation_jobs WHERE id = :id")
    result = db.execute(query, {"id": str(job_id)}).fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return GenerationJobResponse(
        id=result.id,
        author_id=result.author_id,
        character_count=result.character_count,
        status=result.status,
        progress=result.progress,
        audio_url=result.audio_url,
        vtt_url=result.vtt_url,
        error_message=result.error_message,
        created_at=result.created_at
    )


@router.post("/process/{job_id}")
async def process_generation_job(job_id: UUID, db: Session = Depends(get_db)):
    """
    Process a queued generation job
    This is where the actual AI generation happens
    """
    from elevenlabs_client import generate_audio_bytes, get_audio_duration_estimate
    from captions import create_simple_vtt
    from storage import upload_to_s3
    import tempfile
    import os
    
    # Get job
    query = text("SELECT * FROM generation_jobs WHERE id = :id")
    result = db.execute(query, {"id": str(job_id)}).fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if result.status != "queued":
        raise HTTPException(status_code=400, detail=f"Job is {result.status}, cannot process")
    
    try:
        # Update status to processing
        update_query = text("""
            UPDATE generation_jobs 
            SET status = 'processing', started_at = NOW(), progress = 10
            WHERE id = :id
        """)
        db.execute(update_query, {"id": str(job_id)})
        db.commit()
        
        # Generate audio
        audio_bytes = generate_audio_bytes(
            text=result.input_text,
            voice_id=result.voice_id,
            stability=result.stability,
            similarity_boost=result.similarity_boost,
            style=result.style,
            use_speaker_boost=result.use_speaker_boost,
            speaking_rate=result.speaking_rate
        )
        
        if not audio_bytes:
            raise Exception("Failed to generate audio")
        
        # Update progress
        update_query = text("UPDATE generation_jobs SET progress = 50 WHERE id = :id")
        db.execute(update_query, {"id": str(job_id)})
        db.commit()
        
        # Save audio to temp file and upload to S3
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio:
            temp_audio.write(audio_bytes)
            temp_audio_path = temp_audio.name
        
        # Upload audio to S3
        from fastapi import UploadFile
        import aiofiles
        
        # Create S3 key
        audio_s3_key = f"vox-platform/generations/{str(result.author_id)}/{str(job_id)}/audio.mp3"
        
        # Read file as UploadFile for S3 upload
        with open(temp_audio_path, 'rb') as f:
            from io import BytesIO
            audio_file = BytesIO(f.read())
            
            class FakeUploadFile:
                def __init__(self, file, filename, content_type):
                    self.file = file
                    self.filename = filename
                    self.content_type = content_type
                
                async def read(self):
                    return self.file.read()
                
                async def seek(self, position):
                    return self.file.seek(position)
            
            fake_upload = FakeUploadFile(audio_file, "audio.mp3", "audio/mpeg")
            audio_url = await upload_to_s3(fake_upload, audio_s3_key)
        
        # Clean up temp file
        os.unlink(temp_audio_path)
        
        # Update progress
        update_query = text("UPDATE generation_jobs SET progress = 75 WHERE id = :id")
        db.execute(update_query, {"id": str(job_id)})
        db.commit()
        
        # Generate VTT captions
        duration = get_audio_duration_estimate(result.input_text, result.speaking_rate)
        vtt_content = create_simple_vtt(result.input_text, duration)
        
        # Upload VTT to S3
        vtt_s3_key = f"vox-platform/generations/{str(result.author_id)}/{str(job_id)}/captions.vtt"
        
        vtt_bytes = BytesIO(vtt_content.encode('utf-8'))
        fake_vtt = FakeUploadFile(vtt_bytes, "captions.vtt", "text/vtt")
        vtt_url = await upload_to_s3(fake_vtt, vtt_s3_key)
        
        # Update job with results
        update_query = text("""
            UPDATE generation_jobs 
            SET status = 'completed', 
                progress = 100,
                audio_url = :audio_url,
                vtt_url = :vtt_url,
                completed_at = NOW()
            WHERE id = :id
        """)
        db.execute(update_query, {
            "id": str(job_id),
            "audio_url": audio_url,
            "vtt_url": vtt_url
        })
        
        # Update author credits
        update_credits = text("""
            UPDATE author_profiles 
            SET credits_used = credits_used + :chars
            WHERE user_id = :author_id
        """)
        db.execute(update_credits, {
            "chars": result.character_count,
            "author_id": str(result.author_id)
        })
        
        db.commit()
        
        return {
            "status": "completed",
            "audio_url": audio_url,
            "vtt_url": vtt_url
        }
        
    except Exception as e:
        # Update job with error
        update_query = text("""
            UPDATE generation_jobs 
            SET status = 'failed', error_message = :error
            WHERE id = :id
        """)
        db.execute(update_query, {
            "id": str(job_id),
            "error": str(e)
        })
        db.commit()
        
        raise HTTPException(status_code=500, detail=str(e))
