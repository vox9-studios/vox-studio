"""
ElevenLabs API integration for text-to-speech generation
Adapted from Vox9 TTS engine
"""
import os
import requests
from typing import Optional, List, Dict
from tenacity import retry, stop_after_attempt, wait_exponential

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVEN_TTS_URL_TMPL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVEN_VOICES_URL = "https://api.elevenlabs.io/v1/voices"


def get_available_voices() -> List[Dict]:
    """Get list of available ElevenLabs voices"""
    if not ELEVENLABS_API_KEY:
        return []
    
    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    
    try:
        response = requests.get(ELEVEN_VOICES_URL, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        voices = data.get("voices", [])
        
        # Return simplified voice list
        voice_list = []
        for v in voices:
            voice_id = v.get("voice_id", "").strip()
            if not voice_id:
                continue
                
            voice_list.append({
                "voice_id": voice_id,
                "name": v.get("name", "Unnamed").strip(),
                "preview_url": v.get("preview_url"),
                "description": v.get("description", ""),
                "category": v.get("category", "generated")
            })
        
        return voice_list
        
    except Exception as e:
        print(f"Error fetching voices: {e}")
        return []


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def generate_audio_bytes(
    text: str, 
    voice_id: str,
    model_id: str = "eleven_monolingual_v1",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.0,
    use_speaker_boost: bool = True,
    speaking_rate: float = 1.0
) -> Optional[bytes]:
    """
    Generate audio from text using ElevenLabs
    Returns audio bytes if successful, None otherwise
    """
    if not ELEVENLABS_API_KEY:
        print("ELEVENLABS_API_KEY not set")
        return None
    
    try:
        url = ELEVEN_TTS_URL_TMPL.format(voice_id=voice_id)
        
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": style,
                "use_speaker_boost": use_speaker_boost
            }
        }
        
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=60,
            stream=True
        )
        
        response.raise_for_status()
        
        # Read response as bytes
        audio_bytes = b''.join(response.iter_content(chunk_size=8192))
        
        return audio_bytes
        
    except Exception as e:
        print(f"Error generating audio: {e}")
        raise  # Let tenacity retry


def test_api_key() -> bool:
    """Test if ElevenLabs API key is valid"""
    if not ELEVENLABS_API_KEY:
        return False
    
    try:
        voices = get_available_voices()
        return len(voices) > 0
    except Exception as e:
        print(f"API key test failed: {e}")
        return False


def get_audio_duration_estimate(text: str, speaking_rate: float = 1.0) -> float:
    """
    Estimate audio duration based on text length
    Average speaking rate: ~150 words per minute at normal speed
    """
    word_count = len(text.split())
    # 150 words per minute = 2.5 words per second
    base_duration = word_count / 2.5
    # Adjust for speaking rate
    duration_seconds = base_duration / speaking_rate
    return duration_seconds
