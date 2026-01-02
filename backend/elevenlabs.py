"""
ElevenLabs API integration for text-to-speech generation
"""
import os
import requests
from typing import Optional, List, Dict
import time

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


def get_available_voices() -> List[Dict]:
    """Get list of available ElevenLabs voices"""
    try:
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY
        }
        
        response = requests.get(
            f"{ELEVENLABS_API_URL}/voices",
            headers=headers
        )
        
        if response.status_code == 200:
            voices_data = response.json()
            # Return simplified voice list
            voices = []
            for voice in voices_data.get("voices", []):
                voices.append({
                    "voice_id": voice["voice_id"],
                    "name": voice["name"],
                    "preview_url": voice.get("preview_url"),
                    "description": voice.get("description", ""),
                    "labels": voice.get("labels", {})
                })
            return voices
        else:
            print(f"Failed to fetch voices: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching voices: {e}")
        return []


def generate_audio(text: str, voice_id: str, output_path: str) -> bool:
    """
    Generate audio from text using ElevenLabs
    Returns True if successful, False otherwise
    """
    try:
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        response = requests.post(
            f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}",
            json=data,
            headers=headers,
            stream=True
        )
        
        if response.status_code == 200:
            # Save audio file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        else:
            print(f"Failed to generate audio: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"Error generating audio: {e}")
        return False


def generate_audio_with_alignment(text: str, voice_id: str) -> Optional[Dict]:
    """
    Generate audio with word-level alignment data for captions
    Returns dict with audio bytes and alignment data
    """
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        # Request with alignment
        response = requests.post(
            f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}/with-timestamps",
            json=data,
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            return result
        else:
            print(f"Failed to generate audio with alignment: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error generating audio with alignment: {e}")
        return None


def test_api_key() -> bool:
    """Test if ElevenLabs API key is valid"""
    try:
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY
        }
        
        response = requests.get(
            f"{ELEVENLABS_API_URL}/voices",
            headers=headers
        )
        
        return response.status_code == 200
    except:
        return False
