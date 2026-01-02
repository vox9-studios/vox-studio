"""
ElevenLabs API integration for text-to-speech generation
"""
import os
from elevenlabs import generate, voices, set_api_key, Voice, VoiceSettings
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


def generate_audio_bytes(
    text: str, 
    voice_id: str,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.0,
    use_speaker_boost: bool = True,
    speaking_rate: float = 1.0
) -> Optional[bytes]:
    """
    Generate audio from text using ElevenLabs with custom voice settings
    
    Args:
        text: Text to convert to speech
        voice_id: ElevenLabs voice ID
        stability: Voice stability (0.0 - 1.0). Lower = more variable/expressive
        similarity_boost: Voice similarity (0.0 - 1.0). Higher = closer to original voice
        style: Style exaggeration (0.0 - 1.0). Higher = more exaggerated delivery
        use_speaker_boost: Enable speaker boost for clarity
        speaking_rate: Speaking speed (0.25 - 4.0). 1.0 = normal, 0.5 = slow, 2.0 = fast
    
    Returns audio bytes if successful, None otherwise
    """
    try:
        # Clamp speaking rate to valid range
        speaking_rate = max(0.25, min(4.0, speaking_rate))
        
        # Create voice settings
        voice_settings = VoiceSettings(
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost
        )
        
        audio = generate(
            text=text,
            voice=voice_id,
            model="eleven_monolingual_v1",
            voice_settings=voice_settings
        )
        
        # Convert generator to bytes
        audio_bytes = b''.join(audio)
        
        # Note: ElevenLabs doesn't have a direct speaking_rate parameter
        # If you need speed adjustment, you'd need to process the audio
        # with ffmpeg or similar tool after generation
        # For now, we'll track it for future processing
        
        return audio_bytes
        
    except Exception as e:
        print(f"Error generating audio: {e}")
        return None


def generate_audio_to_file(
    text: str, 
    voice_id: str, 
    output_path: str,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.0,
    use_speaker_boost: bool = True,
    speaking_rate: float = 1.0
) -> bool:
    """
    Generate audio from text and save to file with custom settings
    Returns True if successful, False otherwise
    """
    try:
        audio_bytes = generate_audio_bytes(
            text=text,
            voice_id=voice_id,
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
            speaking_rate=speaking_rate
        )
        
        if audio_bytes:
            with open(output_path, 'wb') as f:
                f.write(audio_bytes)
            return True
        return False
        
    except Exception as e:
        print(f"Error generating audio to file: {e}")
        return False


def adjust_audio_speed(input_path: str, output_path: str, speed: float = 1.0) -> bool:
    """
    Adjust audio speed using ffmpeg (if available)
    
    Args:
        input_path: Path to input audio file
        output_path: Path to save adjusted audio
        speed: Speed multiplier (0.5 = half speed, 2.0 = double speed)
    
    Returns True if successful, False otherwise
    """
    try:
        import subprocess
        
        # Check if ffmpeg is available
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except:
            print("ffmpeg not available - speed adjustment skipped")
            # Just copy the file
            import shutil
            shutil.copy(input_path, output_path)
            return True
        
        # Use atempo filter for speed adjustment
        # atempo valid range is 0.5 to 2.0
        # For speeds outside this range, chain multiple filters
        
        if speed < 0.5 or speed > 2.0:
            # Need to chain atempo filters
            filters = []
            remaining_speed = speed
            
            while remaining_speed > 2.0:
                filters.append('atempo=2.0')
                remaining_speed /= 2.0
            
            while remaining_speed < 0.5:
                filters.append('atempo=0.5')
                remaining_speed /= 0.5
            
            if remaining_speed != 1.0:
                filters.append(f'atempo={remaining_speed}')
            
            filter_string = ','.join(filters)
        else:
            filter_string = f'atempo={speed}'
        
        # Run ffmpeg
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-filter:a', filter_string,
            '-y',  # Overwrite output
            output_path
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        return True
        
    except Exception as e:
        print(f"Error adjusting audio speed: {e}")
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


def get_audio_duration_estimate(text: str, speaking_rate: float = 1.0) -> float:
    """
    Estimate audio duration based on text length
    
    Args:
        text: Text to estimate duration for
        speaking_rate: Speaking rate multiplier (1.0 = normal, 0.5 = slow, 2.0 = fast)
    
    Average speaking rate: ~150 words per minute at normal speed
    """
    word_count = len(text.split())
    # 150 words per minute = 2.5 words per second at normal rate
    base_duration = word_count / 2.5
    # Adjust for speaking rate
    duration_seconds = base_duration / speaking_rate
    return duration_seconds
