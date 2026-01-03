"""
Narration API routes - Sentence-by-sentence generation with real timing
"""
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import tempfile
import io
import os
import uuid
from pathlib import Path
from io import BytesIO

from database import get_db
from models import AuthorProfile, GenerationJob
from s3_client import upload_to_s3, s3_client, BUCKET_NAME
from elevenlabs_client import generate_audio_bytes, get_available_voices, test_api_key
from captions import split_into_sentences, create_vtt_from_real_durations, SentencePiece

router = APIRouter(prefix="/api/narration", tags=["narration"])


class VoiceInfo(BaseModel):
    voice_id: str
    name: str
    preview_url: Optional[str] = None
    description: Optional[str] = None
    category: str = "generated"


class GenerationRequest(BaseModel):
    text: str
    voice_id: str
    voice_name: str
    # Episode metadata
    episode_title: Optional[str] = None
    episode_description: Optional[str] = None
    cover_square_url: Optional[str] = None
    cover_mobile_url: Optional[str] = None
    cover_widescreen_url: Optional[str] = None
    is_published: bool = False
    playlist_id: Optional[str] = None  # NEW

class JobResponse(BaseModel):
    id: str
    status: str
    created_at: str


class ProcessResult(BaseModel):
    status: str
    audio_url: Optional[str] = None
    vtt_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    sentence_count: Optional[int] = None


def reset_credits_if_needed(author: AuthorProfile, db: Session):
    """Reset credits if we're in a new month"""
    today = date.today()
    if author.last_credit_reset is None:
        author.last_credit_reset = today
        author.credits_used = 0
        db.commit()
        return
    
    if (today.year > author.last_credit_reset.year or 
        (today.year == author.last_credit_reset.year and today.month > author.last_credit_reset.month)):
        author.credits_used = 0
        author.last_credit_reset = today
        db.commit()


@router.get("/test-api")
async def test_api_endpoint():
    """Test if ElevenLabs API key is valid"""
    is_valid = test_api_key()
    return {
        "api_key_valid": is_valid,
        "message": "API key is valid" if is_valid else "API key is invalid or not set"
    }

@router.post("/upload-cover/{author_id}")
async def upload_cover_image(
    author_id: str,
    file: UploadFile = File(...),
    format_type: str = "square",
    db: Session = Depends(get_db)
):
    """Upload cover image to S3 - supports square, mobile, widescreen"""
    # Validate author
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Validate file type
    if file.content_type not in ["image/jpeg", "image/jpg", "image/png"]:
        raise HTTPException(status_code=400, detail="Only JPG and PNG allowed")
    
    # Validate size (max 5MB)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")
    
    await file.seek(0)
    
    # Generate S3 key
    import uuid
    file_ext = "jpg" if file.content_type == "image/jpeg" else "png"
    image_id = str(uuid.uuid4())
    s3_key = f"vox-platform/covers/{author_id}/{format_type}/{image_id}.{file_ext}"
    
    # Upload to S3
    from storage import upload_to_s3 as storage_upload
    url = await storage_upload(file, s3_key)
    
    return {"success": True, "url": url, "format": format_type}
    
@router.get("/voices", response_model=List[VoiceInfo])
async def get_voices():
    """Get list of available ElevenLabs voices"""
    try:
        voices = get_available_voices()
        return voices
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch voices: {str(e)}")


@router.get("/credits/{author_id}")
async def get_credits(author_id: str, db: Session = Depends(get_db)):
    """Get author's credit usage"""
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    reset_credits_if_needed(author, db)
    
    return {
        "credits_used": author.credits_used,
        "credits_limit": author.credits_limit,
        "credits_remaining": author.credits_limit - author.credits_used,
        "last_reset": author.last_credit_reset.isoformat() if author.last_credit_reset else None
    }


@router.post("/generate/{author_id}", response_model=JobResponse)
async def create_generation_job(
    author_id: str,
    request: GenerationRequest,
    db: Session = Depends(get_db)
):
    """Create a new generation job"""
    # Validate author exists
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Reset credits if needed
    reset_credits_if_needed(author, db)
    
    # Check credits
    char_count = len(request.text)
    if author.credits_used + char_count > author.credits_limit:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits. Need {char_count}, have {author.credits_limit - author.credits_used} remaining."
        )
    
    job = GenerationJob(
        author_id=author_id,
        input_text=request.text,
        voice_id=request.voice_id,
        voice_name=request.voice_name,
        episode_title=request.episode_title,
        episode_description=request.episode_description,
        cover_square_url=request.cover_square_url,
        cover_mobile_url=request.cover_mobile_url,
        cover_widescreen_url=request.cover_widescreen_url,
        is_published=request.is_published,
        playlist_id=request.playlist_id,  # NEW
        status="queued"
    )
    
    db.add(job)
    db.commit()
    db.refresh(job)
    
    return JobResponse(
        id=str(job.id),
        status=job.status,
        created_at=job.created_at.isoformat()
    )


@router.get("/job/{job_id}")
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Get status of a generation job"""
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "id": str(job.id),
        "status": job.status,
        "audio_url": job.audio_url,
        "vtt_url": job.vtt_url,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None
    }


@router.post("/process/{job_id}", response_model=ProcessResult)
async def process_generation_job(job_id: str, db: Session = Depends(get_db)):
    """
    Process a generation job - sentence by sentence with real timing!
    This is the correct approach from Vox9.
    """
    # Get job
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != "queued":
        raise HTTPException(status_code=400, detail=f"Job is {job.status}, cannot process")
    
    # Update status
    job.status = "processing"
    db.commit()
    
    try:
        # Get author for credits
        author = db.query(AuthorProfile).filter(AuthorProfile.user_id == job.author_id).first()
        if not author:
            raise HTTPException(status_code=404, detail="Author not found")
        
        # Step 1: Split text into sentences
        sentences = split_into_sentences(job.input_text)
        
        if not sentences:
            raise HTTPException(status_code=400, detail="No sentences found in text")
        
        print(f"Processing {len(sentences)} sentences...")
        
        # Step 2: Generate audio for EACH sentence individually
        audio_chunks = []  # Store MP3 bytes for each sentence
        durations = []     # Store REAL duration for each sentence
        
        for i, sentence in enumerate(sentences, 1):
            print(f"Generating sentence {i}/{len(sentences)}: {sentence.text[:50]}...")
            
            # Generate audio for THIS sentence
            audio_bytes = generate_audio_bytes(
                text=sentence.text,
                voice_id=job.voice_id,
                model_id=job.model_id or "eleven_monolingual_v1",
                stability=job.stability,
                similarity_boost=job.similarity_boost,
                speaking_rate=job.speaking_rate
            )
            
            if not audio_bytes:
                raise Exception(f"Failed to generate audio for sentence {i}")
            
            # Measure REAL duration using mutagen (lightweight MP3 parser)
            try:
                from mutagen.mp3 import MP3
                
                audio_file = MP3(BytesIO(audio_bytes))
                real_duration = audio_file.info.length  # Actual duration in seconds!
                
                print(f"  → Sentence {i} duration: {real_duration:.2f}s")
                
            except Exception as e:
                # Fallback: estimate based on byte size (very rough)
                # MP3 is typically 128kbps = 16KB/s
                estimated_duration = len(audio_bytes) / 16000
                real_duration = max(0.5, estimated_duration)  # At least 0.5s
                print(f"  → Sentence {i} duration (estimated): {real_duration:.2f}s")
            
            audio_chunks.append(audio_bytes)
            durations.append(real_duration)
        
        # Step 3: Combine audio chunks WITH silence gaps using pydub
        print("Combining audio chunks with silence gaps...")
        
        from pydub import AudioSegment
        
        # Create empty audio to build on
        combined = AudioSegment.empty()
        
        # Define silence durations (match VTT gap settings)
        silence_gap = AudioSegment.silent(duration=job.caption_gap or 150)  # milliseconds
        paragraph_silence = AudioSegment.silent(duration=600)  # milliseconds
        
        for i, (audio_bytes, sentence) in enumerate(zip(audio_chunks, sentences)):
            # Load this sentence's audio
            segment = AudioSegment.from_file(BytesIO(audio_bytes), format="mp3")
            
            # Add gap BEFORE this sentence (except first)
            if i > 0:
                if sentence.paragraph_break_before:
                    combined += paragraph_silence
                    print(f"  → Added 600ms paragraph gap before sentence {i+1}")
                else:
                    combined += silence_gap
                    print(f"  → Added {job.caption_gap or 150}ms gap before sentence {i+1}")
            
            # Add the sentence audio
            combined += segment
        
        # Export combined audio to MP3 bytes
        combined_audio = combined.export(format="mp3").read()
        
        total_duration = sum(durations)
        print(f"Total audio duration (speech only): {total_duration:.2f}s")
        print(f"Total audio duration (with gaps): {len(combined) / 1000.0:.2f}s")
        
        # Step 4: Create VTT with REAL durations (matching the audio gaps!)
        print("Creating captions with real timing...")
        
        vtt_content = create_vtt_from_real_durations(
            sentences=sentences,
            durations=durations,
            caption_lead_in_ms=job.caption_lead_in,
            caption_lead_out_ms=job.caption_lead_out,
            paragraph_gap_ms=600,              # Matches paragraph_silence above
            gap_ms=job.caption_gap or 150      # Matches silence_gap above
        )
        
        # Step 5: Upload to S3
        print("Uploading to S3...")
        
        audio_key = f"vox-platform/generations/{job.author_id}/{job_id}/audio.mp3"
        vtt_key = f"vox-platform/generations/{job.author_id}/{job_id}/captions.vtt"
        
        audio_url = upload_to_s3(combined_audio, audio_key, content_type="audio/mpeg")
        vtt_url = upload_to_s3(vtt_content.encode('utf-8'), vtt_key, content_type="text/vtt")
        
        # Step 6: Update job
        job.status = "completed"
        job.audio_url = audio_url
        job.vtt_url = vtt_url
        job.completed_at = datetime.utcnow()
        
        # Step 7: Deduct credits
        author.credits_used += len(job.input_text)
        
        db.commit()
        
        print(f"✓ Job {job_id} completed successfully!")
        
        return ProcessResult(
            status="completed",
            audio_url=audio_url,
            vtt_url=vtt_url,
            duration_seconds=len(combined) / 1000.0,  # Actual duration with gaps
            sentence_count=len(sentences)
        )
        
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
        
        print(f"✗ Job {job_id} failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/episodes/{author_id}")
async def get_author_episodes(
    author_id: str,
    db: Session = Depends(get_db)
):
    """Get all completed episodes for an author"""
    # Validate author exists
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Get all completed jobs
    jobs = db.query(GenerationJob).filter(
        GenerationJob.author_id == author_id,
        GenerationJob.status == "completed"
    ).order_by(GenerationJob.created_at.desc()).all()
    
    # Format response
    episodes = []
    for job in jobs:
        episodes.append({
            "id": str(job.id),
            "author_id": str(job.author_id),
            "episode_title": job.episode_title,
            "episode_description": job.episode_description,
            "cover_square_url": job.cover_square_url,
            "cover_mobile_url": job.cover_mobile_url,
            "cover_widescreen_url": job.cover_widescreen_url,
            "is_published": job.is_published,
            "playlist_id": str(job.playlist_id) if job.playlist_id else None,
            "audio_url": job.audio_url,
            "vtt_url": job.vtt_url,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None
        })
    
    return episodes

@router.patch("/publish/{job_id}")
async def publish_episode(
    job_id: str,
    db: Session = Depends(get_db)
):
    """Publish an episode (set is_published to true)"""
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Can only publish completed episodes")
    
    # Update is_published
    job.is_published = True
    db.commit()
    
    return {
        "success": True,
        "message": "Episode published successfully",
        "episode_id": str(job.id),
        "is_published": True
    }

# Add to backend/routes/narration.py

@router.post("/upload-audio/{author_id}")
async def upload_audio_file(
    author_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload MP3 audio file directly (no AI generation)"""
    
    # Validate author
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Validate file type
    if not file.filename.endswith('.mp3'):
        raise HTTPException(status_code=400, detail="Only MP3 files are supported")
    
    try:
        # Read file content
        contents = await file.read()
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        s3_key = f"vox-platform/uploads/{author_id}/{file_id}.mp3"
        
        # Upload to S3
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=contents,
            ContentType='audio/mpeg'
        )
        
        # Get public URL
        audio_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION', 'eu-west-2')}.amazonaws.com/{s3_key}"
        
        return {
            "success": True,
            "audio_url": audio_url,
            "file_id": file_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/upload-vtt/{author_id}")
async def upload_vtt_file(
    author_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload VTT caption file"""
    
    # Validate author
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Validate file type
    if not file.filename.endswith('.vtt'):
        raise HTTPException(status_code=400, detail="Only VTT files are supported")
    
    try:
        # Read file content
        contents = await file.read()
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        s3_key = f"vox-platform/captions/{author_id}/{file_id}.vtt"
        
        # Upload to S3
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=contents,
            ContentType='text/vtt'
        )
        
        # Get public URL
        vtt_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION', 'eu-west-2')}.amazonaws.com/{s3_key}"
        
        return {
            "success": True,
            "vtt_url": vtt_url,
            "file_id": file_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/create-uploaded-episode/{author_id}")
async def create_uploaded_episode(
    author_id: str,
    request: dict,
    db: Session = Depends(get_db)
):
    """Create episode from uploaded audio (no AI generation)"""
    
    # Validate author
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    # Create generation job record (marked as uploaded)
    job = GenerationJob(
        id=uuid.uuid4(),
        author_id=author_id,
        episode_title=request.get('episode_title'),
        episode_description=request.get('episode_description'),
        cover_square_url=request.get('cover_square_url'),
        cover_mobile_url=request.get('cover_mobile_url'),
        cover_widescreen_url=request.get('cover_widescreen_url'),
        playlist_id=request.get('playlist_id'),
        is_published=request.get('is_published', False),
        
        # Uploaded file URLs
        audio_url=request.get('audio_url'),
        vtt_url=request.get('vtt_url'),
        
        # Mark as uploaded (not AI generated)
        input_text="[Uploaded Audio]",
        voice_id="uploaded",
        voice_name="Uploaded",
        
        # Status
        status="completed",  # Already completed (no generation needed)
        progress=100,
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow()
    )
    
    db.add(job)
    db.commit()
    db.refresh(job)
    
    return {
        "success": True,
        "job_id": str(job.id),
        "message": "Episode created successfully"
    }

@router.patch("/episodes/{episode_id}")
async def update_episode(
    episode_id: str,
    request: dict,
    db: Session = Depends(get_db)
):
    """Update episode metadata"""
    episode = db.query(GenerationJob).filter(GenerationJob.id == episode_id).first()
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    # Update fields if provided
    if 'episode_title' in request:
        episode.episode_title = request['episode_title']
    
    if 'episode_description' in request:
        episode.episode_description = request['episode_description']
    
    if 'playlist_id' in request:
        # Allow null to remove from playlist
        episode.playlist_id = request['playlist_id'] if request['playlist_id'] else None
    
    if 'is_published' in request:
        episode.is_published = request['is_published']
    
    db.commit()
    db.refresh(episode)
    
    return {
        "success": True,
        "message": "Episode updated successfully",
        "episode": {
            "id": str(episode.id),
            "episode_title": episode.episode_title,
            "episode_description": episode.episode_description,
            "playlist_id": str(episode.playlist_id) if episode.playlist_id else None,
            "is_published": episode.is_published
        }
    }


@router.delete("/episodes/{episode_id}")
async def delete_episode(
    episode_id: str,
    db: Session = Depends(get_db)
):
    """Delete episode and its S3 files"""
    episode = db.query(GenerationJob).filter(GenerationJob.id == episode_id).first()
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    try:
        # Delete S3 files
        from s3_client import s3_client, BUCKET_NAME
        
        # Extract S3 keys from URLs
        if episode.audio_url:
            audio_key = episode.audio_url.split('.amazonaws.com/')[-1]
            try:
                s3_client.delete_object(Bucket=BUCKET_NAME, Key=audio_key)
            except Exception as e:
                print(f"Failed to delete audio: {e}")
        
        if episode.vtt_url:
            vtt_key = episode.vtt_url.split('.amazonaws.com/')[-1]
            try:
                s3_client.delete_object(Bucket=BUCKET_NAME, Key=vtt_key)
            except Exception as e:
                print(f"Failed to delete VTT: {e}")
        
        if episode.cover_square_url:
            cover_key = episode.cover_square_url.split('.amazonaws.com/')[-1]
            try:
                s3_client.delete_object(Bucket=BUCKET_NAME, Key=cover_key)
            except Exception as e:
                print(f"Failed to delete cover: {e}")
        
        # Delete from database
        db.delete(episode)
        db.commit()
        
        return {
            "success": True,
            "message": "Episode deleted successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete episode: {str(e)}")
        
