"""
VTT caption generation - Improved version based on Vox9 TTS engine
"""
from typing import List, Dict, Optional, NamedTuple
import re


class SentencePiece(NamedTuple):
    """Represents a sentence with paragraph break info"""
    text: str
    paragraph_break_before: bool


# Abbreviations that don't end sentences
_NON_TERMINAL_ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
    "etc.", "vs.", "e.g.", "i.e.", "a.m.", "p.m."
}

# Common words that start sentences
_COMMON_SENTENCE_STARTERS = {
    "a", "an", "and", "but", "he", "she", "it", "i", "you", "we", "they",
    "the", "there", "these", "those", "this", "that", "what", "when", 
    "where", "why", "how", "who", "which", "so", "then", "now"
}


def format_timestamp(seconds: float) -> str:
    """Convert seconds to VTT timestamp format (HH:MM:SS.mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def _sentence_ends_with_abbreviation(text: str) -> bool:
    """Check if text ends with a protected abbreviation"""
    if not text:
        return False
    last_word = text.rstrip().split()
    if not last_word:
        return False
    # Use simple string concatenation to avoid quote escaping issues
    chars_to_strip = '"' + "'" + ")" + "]" + "}"
    token = last_word[-1].rstrip(chars_to_strip)
    return token.lower() in _NON_TERMINAL_ABBREVIATIONS


def _starts_like_new_sentence(part: str) -> bool:
    """Check if text starts like a new sentence"""
    if not part:
        return False
    tokens = part.split()
    if not tokens:
        return False
    first_word = tokens[0].lstrip("\"'""''([{")
    if not first_word:
        return False
    return first_word.lower() in _COMMON_SENTENCE_STARTERS


def split_into_sentences(text: str) -> List[SentencePiece]:
    """
    Split text into sentences with paragraph break detection.
    Handles abbreviations like "Mr." and "Mrs." correctly.
    """
    # Split by double newlines (paragraphs)
    paragraphs = text.split("\n\n")
    sentences: List[SentencePiece] = []
    seen_paragraph = False
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        
        # Split on sentence-ending punctuation followed by space
        parts = re.split(r"(?<=[\.!?])\s+", paragraph)
        
        first_sentence_in_paragraph = True
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Check if we should merge with previous sentence
            if (
                sentences
                and not first_sentence_in_paragraph
                and _sentence_ends_with_abbreviation(sentences[-1].text)
                and not _starts_like_new_sentence(part)
            ):
                # Merge with previous sentence
                prev_piece = sentences[-1]
                sentences[-1] = SentencePiece(
                    f"{prev_piece.text} {part}",
                    prev_piece.paragraph_break_before,
                )
            else:
                # New sentence
                sentences.append(
                    SentencePiece(
                        part,
                        paragraph_break_before=seen_paragraph and first_sentence_in_paragraph,
                    )
                )
            
            first_sentence_in_paragraph = False
        
        seen_paragraph = True
    
    return sentences


def create_simple_vtt(
    text: str, 
    duration_seconds: float,
    *,
    caption_lead_in_ms: int = 50,
    caption_lead_out_ms: int = 120,
    paragraph_gap_ms: int = 600,
    gap_ms: int = 150
) -> str:
    """
    Create VTT captions with sentence-by-sentence timing.
    Each sentence gets proper lead-in so captions appear BEFORE audio speaks.
    
    Args:
        text: The full text to caption
        duration_seconds: Total audio duration in seconds
        caption_lead_in_ms: How early captions should appear (default 50ms)
        caption_lead_out_ms: How early captions should disappear (default 120ms)
        paragraph_gap_ms: Gap between paragraphs (default 600ms)
        gap_ms: Gap between sentences (default 150ms)
    """
    vtt_content = "WEBVTT\n\n"
    
    # Split into sentences
    sentences = split_into_sentences(text)
    
    if not sentences:
        return vtt_content
    
    # Calculate timing - distribute duration across sentences by character count
    total_chars = sum(len(s.text) for s in sentences)
    if total_chars == 0:
        return vtt_content
    
    # Convert timing parameters to seconds
    caption_lead_in = caption_lead_in_ms / 1000.0
    caption_lead_out = caption_lead_out_ms / 1000.0
    paragraph_gap = paragraph_gap_ms / 1000.0
    sentence_gap = gap_ms / 1000.0
    min_caption_duration = 0.3  # Minimum 300ms for readability
    
    # Track actual audio time (when voice speaks)
    audio_time = 0.0
    cue_number = 1
    last_caption_end = 0.0
    
    for i, sentence in enumerate(sentences):
        # Add gap BEFORE this sentence (in audio time)
        if i > 0:
            if sentence.paragraph_break_before:
                audio_time += paragraph_gap
            else:
                audio_time += sentence_gap
        
        # Calculate how long this sentence's audio will take
        char_proportion = len(sentence.text) / total_chars
        sentence_audio_duration = duration_seconds * char_proportion
        
        # TIMING BREAKDOWN:
        # audio_time = when voice STARTS speaking this sentence
        # audio_end = when voice FINISHES speaking this sentence
        # caption_start = when text appears (BEFORE audio_time)
        # caption_end = when text disappears (BEFORE audio_end)
        
        # CAPTION START: Lead-in means caption appears BEFORE audio
        caption_start = max(0.0, audio_time - caption_lead_in)
        
        # AUDIO ENDS: When the voice finishes speaking this sentence
        audio_end = audio_time + sentence_audio_duration
        
        # CAPTION END: Lead-out means caption disappears BEFORE audio ends
        caption_end = audio_end - caption_lead_out
        
        # Ensure minimum duration for readability
        if caption_end - caption_start < min_caption_duration:
            caption_end = caption_start + min_caption_duration
        
        # Prevent overlapping with previous caption
        if i > 0 and caption_start < last_caption_end:
            caption_start = last_caption_end
            # Re-check minimum duration
            if caption_end - caption_start < min_caption_duration:
                caption_end = caption_start + min_caption_duration
        
        # Write VTT cue
        vtt_content += f"{cue_number}\n"
        vtt_content += f"{format_timestamp(caption_start)} --> {format_timestamp(caption_end)}\n"
        vtt_content += f"{sentence.text}\n\n"
        
        cue_number += 1
        last_caption_end = caption_end
        
        # Advance audio timeline
        audio_time = audio_end
    
    return vtt_content


def create_vtt_from_alignment(alignment_data: Dict) -> str:
    """
    Create VTT captions from ElevenLabs alignment data.
    This is used when ElevenLabs provides word-level timing.
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
    
    # Create VTT cues (group 6-10 words per caption)
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
