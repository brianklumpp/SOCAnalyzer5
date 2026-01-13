"""
Text analysis utilities for intelligent control merging.

Provides functions for:
- Bullet point extraction and merging
- Substring/superset detection
- Text similarity calculation
- Structure analysis
"""
import re
from typing import List, Tuple
from difflib import SequenceMatcher


def extract_bullets(text: str) -> List[str]:
    """
    Extract bullet points or numbered items from text.
    
    Returns list of individual bullets with markers removed.
    Handles:
    - Numbered items: 1., 2., 3.
    - Lettered items: a), b), (i), (ii)
    - Bullet symbols: •, -, *, ◦, ▪
    
    Args:
        text: Text containing bullet points
        
    Returns:
        List of bullet text without markers, or [text] if no structure detected
    """
    if not text:
        return []
    
    lines = text.split('\n')
    bullets = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Match numbered items: 1., 2., a), (i), etc.
        if re.match(r'^(\d+\.|[a-z]\)|\([ivx]+\)|\([a-z]\))', line):
            bullets.append(re.sub(r'^(\d+\.|[a-z]\)|\([ivx]+\)|\([a-z]\))\s*', '', line))
        # Match bullet symbols: •, -, *, ◦, ▪
        elif re.match(r'^[•\-\*◦▪]\s+', line):
            bullets.append(re.sub(r'^[•\-\*◦▪]\s+', '', line))
        # Standalone lines in bulleted text (continuation or implied bullet)
        elif bullets:
            # Append to previous bullet if it looks like continuation
            if not re.match(r'^[A-Z]', line) and len(bullets) > 0:
                bullets[-1] += ' ' + line
            else:
                bullets.append(line)
    
    return bullets if bullets else [text]


def is_substring_match(text1: str, text2: str) -> Tuple[bool, str]:
    """
    Check if one text is a substring/superset of another.
    
    Uses normalized comparison (whitespace collapsed, case-insensitive, trailing punctuation removed).
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Tuple of (is_match, longer_text)
    """
    if not text1 or not text2:
        return False, text1 or text2
    
    # Normalize: collapse whitespace, lowercase, remove trailing punctuation
    t1_clean = re.sub(r'\s+', ' ', text1.strip().lower())
    t2_clean = re.sub(r'\s+', ' ', text2.strip().lower())
    
    # Remove trailing punctuation for comparison
    t1_compare = re.sub(r'[.,;:!?]+$', '', t1_clean)
    t2_compare = re.sub(r'[.,;:!?]+$', '', t2_clean)
    
    if t1_compare == t2_compare:
        return True, text1 if len(text1) >= len(text2) else text2
    
    if t1_compare in t2_compare:
        return True, text2
    if t2_compare in t1_compare:
        return True, text1
    
    return False, ""


def calculate_text_difference(text1: str, text2: str) -> float:
    """
    Calculate percentage difference between two texts.
    
    Uses character-level sequence matching.
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Float from 0.0 (identical) to 1.0 (completely different)
    """
    if not text1 and not text2:
        return 0.0
    if not text1 or not text2:
        return 1.0
    
    # Use SequenceMatcher for character-level similarity
    ratio = SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    return 1.0 - ratio


def has_bullet_structure(text: str) -> bool:
    """
    Check if text contains bullet points or numbered lists.
    
    Requires at least 2 bullet items to be considered structured.
    
    Args:
        text: Text to analyze
        
    Returns:
        True if text has bullet/numbered structure
    """
    if not text:
        return False
    
    bullet_patterns = [
        r'^\d+\.',  # 1., 2., 3.
        r'^[a-z]\)',  # a), b), c)
        r'^\([ivx]+\)',  # (i), (ii), (iii)
        r'^[•\-\*◦▪]\s+',  # bullet symbols
    ]
    
    lines = text.split('\n')
    bullet_count = sum(1 for line in lines if any(re.match(p, line.strip()) for p in bullet_patterns))
    
    return bullet_count >= 2


def merge_bullet_lists(list1: List[str], list2: List[str]) -> List[str]:
    """
    Intelligently merge two bullet lists, preserving unique items.
    
    Uses fuzzy matching (85% similarity threshold) to avoid near-duplicates.
    When duplicates detected, keeps longer version.
    
    Args:
        list1: First bullet list
        list2: Second bullet list
        
    Returns:
        Merged list with unique bullets
    """
    merged = list(list1)
    
    for item2 in list2:
        # Check if this bullet is already in merged list (fuzzy match)
        is_duplicate = False
        for idx, item1 in enumerate(merged):
            similarity = SequenceMatcher(None, item1.lower(), item2.lower()).ratio()
            if similarity > 0.85:  # 85% similar = duplicate
                # Keep longer version
                if len(item2) > len(item1):
                    merged[idx] = item2
                is_duplicate = True
                break
        
        if not is_duplicate:
            merged.append(item2)
    
    return merged
