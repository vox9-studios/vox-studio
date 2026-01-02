"""
VTT caption generation from alignment data
"""
from typing import List, Dict, Optional
import re


def format_timestamp(seconds: float) -> str:
    """Convert seconds to VTT timestamp format (HH:MM:SS.mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def create_vtt_from_alignment(alignment_data: Dict) -> str:
    """
    Create VTT captions from ElevenLabs alignment data
    
    alignment_data should have structure:
    {
        "alignment": {
            "characters": ["H", "e", "l", "l", "o", ...],
            "character_start_times_seconds": [0.0, 0.1, 0.2, ...],
            "character_end_times_seconds": [0.1, 0.2, 0.3, ...]
        }
    }
    """
    vtt_content = "WEBVTT\n\n"
    
    if not alignment_data or "alignment" not in alignment_data:
        return vtt_content
    
    alignment = alignment_data["alignment"]
    characters = alignment.get("characters", [])
    char_start_times = alignment.get("character_start_times_seconds", [])
    char_end_times = alignment.get("character_end_times_seconds", [])
    
    if not characters or not char_start_times or not char_end_times:
        return vtt_content
    
    # Group characters into words
    words = []
    current_word = ""
    word_start = None
    word_end = None
    
    for i, char in enumerate(characters):
        if word_start is None:
            word_start = char_start_times[i]
        
        current_word += char
        word_end = char_end_times[i]
        
        # End of word (space or punctuation)
        if char in [' ', '.', ',', '!', '?', ';', ':'] or i == len(characters) - 1:
            if current_word.strip():
                words.append({
                    "text": current_word.strip(),
                    "start": word_start,
                    "end": word_end
                })
            current_word = ""
            word_start = None
    
    # Create VTT cues (group 5-10 words per caption)
    words_per_caption = 8
    cue_number = 1
    
    for i in range(0, len(words), words_per_caption):
        caption_words = words[i:i + words_per_caption]
        if not caption_words:
            continue
        
        start_time = caption_words[0]["start"]
        end_time = caption_words[-1]["end"]
        text = " ".join([w["text"] for w in caption_words])
        
        vtt_content += f"{cue_number}\n"
        vtt_content += f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}\n"
        vtt_content += f"{text}\n\n"
        
        cue_number += 1
    
    return vtt_content


def create_simple_vtt(text: str, duration_seconds: float) -> str:
    """
    Create simple VTT captions when alignment data is not available
    Splits text into sentences based on estimated timing
    Preserves all punctuation and proper sentence structure
    """
    vtt_content = "WEBVTT\n\n"
    
    # Split text into sentences (preserve all punctuation)
    # Split on sentence-ending punctuation followed by space or end of string
    sentences = re.split(r'([.!?]+(?:\s+|$))', text)
    
    # Reconstruct sentences with their punctuation
    full_sentences = []
    i = 0
    while i < len(sentences):
        if i + 1 < len(sentences) and sentences[i].strip():
            # Combine sentence with its punctuation
            sentence = sentences[i] + sentences[i + 1]
            full_sentences.append(sentence.strip())
            i += 2
        elif sentences[i].strip():
            full_sentences.append(sentences[i].strip())
            i += 1
        else:
            i += 1
    
    if not full_sentences:
        return vtt_content
    
    # Estimate time per sentence based on character count
    total_chars = sum(len(s) for s in full_sentences)
    
    current_time = 0.0
    for i, sentence in enumerate(full_sentences):
        # Calculate duration based on character proportion
        char_proportion = len(sentence) / max(1, total_chars)
        sentence_duration = duration_seconds * char_proportion
        
        start_time = current_time
        end_time = current_time + sentence_duration
        
        vtt_content += f"{i + 1}\n"
        vtt_content += f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}\n"
        vtt_content += f"{sentence}\n\n"
        
        current_time = end_time
    
    return vtt_content
