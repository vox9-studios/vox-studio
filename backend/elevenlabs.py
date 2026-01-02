"""
ElevenLabs API integration for text-to-speech generation
"""
import os
from elevenlabs import generate, voices, set_api_key, Voice
from typing import Optional, List, Dict
import tempfile

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Set API key for elevenlabs library
if ELEVENLABS_API_KEY:
    set_api_key(ELEVENLABS_API_KEY)


def get_available_voices() -> List[Dict]:
    """Get list of available ElevenLabs voices"""
    try:
        all_voices = voices()
        
        # Return simplified voice list
        voice_list = []
        for voice in all_voices:
            voice_list.append({
                "voice_id": voice.voice_id,
                "name": voice.name,
                "preview_url": voice.preview_url if hasattr(voice, 'preview_url') else None,
                "description": voice.description if hasattr(voice, 'description') else "",
                "category": voice.category if hasattr(voice, 'category') else "generated"
            })
        return voice_list
    except Exception as e:
        print(f"Error fetching voices: {e}")
        return []


def generate_audio_bytes(text: str, voice_id: str) -> Optional[bytes]:
    """
    Generate audio from text using ElevenLabs
    Returns audio bytes if successful, None otherwise
    """
    try:
        audio = generate(
            text=text,
            voice=voice_id,
            model="eleven_monolingual_v1"
        )
        
        # Convert generator to bytes
        audio_bytes = b''.join(audio)
        return audio_bytes
        
    except Exception as e:
        print(f"Error generating audio: {e}")
        return None


def generate_audio_to_file(text: str, voice_id: str, output_path: str) -> bool:
    """
    Generate audio from text and save to file
    Returns True if successful, False otherwise
    """
    try:
        audio_bytes = generate_audio_bytes(text, voice_id)
        
        if audio_bytes:
            with open(output_path, 'wb') as f:
                f.write(audio_bytes)
            return True
        return False
        
    except Exception as e:
        print(f"Error generating audio to file: {e}")
        return False


def test_api_key() -> bool:
    """Test if ElevenLabs API key is valid"""
    try:
        # Try to fetch voices as a test
        all_voices = voices()
        return len(all_voices) > 0
    except Exception as e:
        print(f"API key test failed: {e}")
        return False


def get_audio_duration_estimate(text: str) -> float:
    """
    Estimate audio duration based on text length
    Average speaking rate: ~150 words per minute
    """
    word_count = len(text.split())
    # 150 words per minute = 2.5 words per second
    duration_seconds = word_count / 2.5
    return duration_seconds
