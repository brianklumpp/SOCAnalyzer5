"""
Control Pattern Library for learning and validating control ID patterns.

This module provides intelligent pattern recognition for control IDs across different
organizations, with support for:
- Learning patterns from validated controls
- Pruning low-frequency patterns (<5 occurrences)
- Lenient structural merging (e.g., IAM-XX-XX + PAM-XX-XX → XAM-XX-XX)
- Per-organization pattern profiles
- Manual review queue for ambiguous merges
"""

import re
from datetime import datetime
from typing import Dict, List, Optional
from difflib import SequenceMatcher
from sqlalchemy import select, delete, and_
from sqlalchemy.orm import Session

from backend.app.models import ControlPattern, PatternReviewQueue


class ControlPatternLibrary:
    """
    Manages learning and validation of control ID patterns per organization.
    """
    
    def __init__(self, db_session: Session = None):
        """
        Initialize the pattern library.
        
        Args:
            db_session: Database session for persistence (optional for in-memory mode)
        """
        self.db = db_session
        self.patterns_cache: Dict[str, Dict[str, int]] = {}  # org -> {pattern: frequency}
        self.min_frequency = 5
        self.similarity_threshold_exact = 0.7  # 70%+ similarity = auto-merge
        self.similarity_threshold_review = 0.5  # 50-70% = manual review
    
    def extract_pattern(self, control_id: str) -> Optional[str]:
        """
        Extract the structural pattern from a control ID.
        
        Examples:
            "IAM-01-04" -> "IAM-XX-XX"
            "IM.2.0" -> "IM.X.X"
            "ELC-02-01" -> "ELC-XX-XX"
            "CC.1.1" -> "CC.X.X"
        
        Args:
            control_id: The control ID string
            
        Returns:
            Pattern string or None if invalid
        """
        if not control_id or not isinstance(control_id, str):
            return None
        
        # Normalize whitespace
        control_id = control_id.strip()
        
        # Pattern 1: Dash-separated (XXX-XX-XX)
        dash_match = re.match(r'^([A-Z]{2,5})-(\d+)-(\d+)$', control_id)
        if dash_match:
            prefix = dash_match.group(1)
            num_digits_1 = len(dash_match.group(2))
            num_digits_2 = len(dash_match.group(3))
            return f"{prefix}-{'X' * num_digits_1}-{'X' * num_digits_2}"
        
        # Pattern 2: Dot-separated (XX.X.X)
        dot_match = re.match(r'^([A-Z]{2,5})\.(\d+)\.(\d+)$', control_id)
        if dot_match:
            prefix = dot_match.group(1)
            num_digits_1 = len(dot_match.group(2))
            num_digits_2 = len(dot_match.group(3))
            return f"{prefix}.{'X' * num_digits_1}.{'X' * num_digits_2}"
        
        # Pattern 3: Single segment (XX.X)
        single_match = re.match(r'^([A-Z]{2,5})\.(\d+)$', control_id)
        if single_match:
            prefix = single_match.group(1)
            num_digits = len(single_match.group(2))
            return f"{prefix}.{'X' * num_digits}"
        
        return None
    
    def calculate_pattern_similarity(self, pattern1: str, pattern2: str) -> float:
        """
        Calculate structural similarity between two patterns.
        
        Args:
            pattern1: First pattern string
            pattern2: Second pattern string
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        if pattern1 == pattern2:
            return 1.0
        
        # Check if they use same separator
        sep1 = '-' if '-' in pattern1 else '.' if '.' in pattern1 else None
        sep2 = '-' if '-' in pattern2 else '.' if '.' in pattern2 else None
        
        if sep1 != sep2:
            return 0.0  # Different separators = incompatible
        
        # Split into segments
        segments1 = pattern1.split(sep1) if sep1 else [pattern1]
        segments2 = pattern2.split(sep2) if sep2 else [pattern2]
        
        if len(segments1) != len(segments2):
            return 0.0  # Different structure = incompatible
        
        # Compare prefixes
        prefix1 = segments1[0]
        prefix2 = segments2[0]
        
        # Use SequenceMatcher for prefix similarity
        prefix_similarity = SequenceMatcher(None, prefix1, prefix2).ratio()
        
        # Compare segment structures (X counts)
        segment_match = sum(1 for s1, s2 in zip(segments1[1:], segments2[1:]) if s1 == s2)
        segment_similarity = segment_match / len(segments1[1:]) if len(segments1) > 1 else 1.0
        
        # Weighted average: prefix is more important
        return 0.7 * prefix_similarity + 0.3 * segment_similarity
    
    def find_mergeable_patterns(
        self, 
        patterns: Dict[str, int]
    ) -> List[Dict[str, any]]:
        """
        Identify patterns that can be merged based on similarity.
        
        Args:
            patterns: Dictionary of {pattern: frequency}
            
        Returns:
            List of merge suggestions with metadata
        """
        merge_suggestions = []
        pattern_list = list(patterns.keys())
        
        for i, pattern1 in enumerate(pattern_list):
            for pattern2 in pattern_list[i+1:]:
                similarity = self.calculate_pattern_similarity(pattern1, pattern2)
                
                if similarity >= self.similarity_threshold_exact:
                    # Auto-merge: high similarity
                    merged = self._create_merged_pattern(pattern1, pattern2)
                    merge_suggestions.append({
                        'pattern1': pattern1,
                        'pattern2': pattern2,
                        'merged_pattern': merged,
                        'similarity': similarity,
                        'status': 'auto_merge',
                        'combined_frequency': patterns[pattern1] + patterns[pattern2]
                    })
                elif similarity >= self.similarity_threshold_review:
                    # Manual review: moderate similarity
                    merged = self._create_merged_pattern(pattern1, pattern2)
                    merge_suggestions.append({
                        'pattern1': pattern1,
                        'pattern2': pattern2,
                        'merged_pattern': merged,
                        'similarity': similarity,
                        'status': 'needs_review',
                        'combined_frequency': patterns[pattern1] + patterns[pattern2]
                    })
        
        return merge_suggestions
    
    def _create_merged_pattern(self, pattern1: str, pattern2: str) -> str:
        """
        Create a merged pattern from two similar patterns.
        
        Examples:
            "IAM-XX-XX" + "PAM-XX-XX" -> "XAM-XX-XX"
            "IM.X.X" + "AM.X.X" -> "XM.X.X"
        
        Args:
            pattern1: First pattern
            pattern2: Second pattern
            
        Returns:
            Merged pattern string
        """
        sep = '-' if '-' in pattern1 else '.'
        segments1 = pattern1.split(sep)
        segments2 = pattern2.split(sep)
        
        merged_segments = []
        for s1, s2 in zip(segments1, segments2):
            if s1 == s2:
                merged_segments.append(s1)
            else:
                # Find common suffix for prefixes
                # "IAM" + "PAM" -> common suffix "AM"
                common_suffix = ""
                for i in range(1, min(len(s1), len(s2)) + 1):
                    if s1[-i:] == s2[-i:]:
                        common_suffix = s1[-i:]
                    else:
                        break
                
                if common_suffix and len(common_suffix) >= 2:
                    # Keep common suffix, replace prefix with X
                    merged_segments.append('X' + common_suffix)
                else:
                    # No meaningful common part, use X
                    merged_segments.append('X' * max(len(s1), len(s2)))
        
        return sep.join(merged_segments)
    
    async def learn_from_scan(
        self, 
        scan_id: int, 
        organization: str,
        controls: List[Dict]
    ) -> Dict[str, any]:
        """
        Learn patterns from a completed scan's validated controls.
        
        Args:
            scan_id: The scan identifier
            organization: Organization name
            controls: List of control dictionaries with control_id and control_confidence
            
        Returns:
            Dictionary with learning statistics
        """
        if not self.db:
            raise ValueError("Database session required for learning")
        
        learned_patterns = {}
        high_confidence_controls = [
            c for c in controls 
            if c.get('control_confidence', 0) >= 0.9 and c.get('control_id')
        ]
        
        # Extract patterns from high-confidence controls
        for control in high_confidence_controls:
            pattern = self.extract_pattern(control['control_id'])
            if pattern:
                learned_patterns[pattern] = learned_patterns.get(pattern, 0) + 1
        
        # Update or create pattern records
        now = datetime.utcnow()
        patterns_added = 0
        patterns_updated = 0
        
        for pattern, frequency in learned_patterns.items():
            # Check if pattern exists for this organization
            result = await self.db.execute(
                select(ControlPattern).where(
                    and_(
                        ControlPattern.organization == organization,
                        ControlPattern.pattern == pattern
                    )
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing pattern
                existing.frequency += frequency
                existing.last_seen = now
                if existing.scan_ids is None:
                    existing.scan_ids = []
                if scan_id not in existing.scan_ids:
                    existing.scan_ids.append(scan_id)
                patterns_updated += 1
            else:
                # Create new pattern
                new_pattern = ControlPattern(
                    organization=organization,
                    pattern=pattern,
                    frequency=frequency,
                    first_seen=now,
                    last_seen=now,
                    scan_ids=[scan_id]
                )
                self.db.add(new_pattern)
                patterns_added += 1
        
        await self.db.commit()
        
        # Identify merge candidates
        all_patterns_result = await self.db.execute(
            select(ControlPattern).where(ControlPattern.organization == organization)
        )
        all_patterns = {p.pattern: p.frequency for p in all_patterns_result.scalars().all()}
        
        merge_suggestions = self.find_mergeable_patterns(all_patterns)
        
        # Queue manual review items
        review_queued = 0
        for suggestion in merge_suggestions:
            if suggestion['status'] == 'needs_review':
                # Check if already in queue
                result = await self.db.execute(
                    select(PatternReviewQueue).where(
                        and_(
                            PatternReviewQueue.organization == organization,
                            PatternReviewQueue.pattern1 == suggestion['pattern1'],
                            PatternReviewQueue.pattern2 == suggestion['pattern2']
                        )
                    )
                )
                existing_review = result.scalar_one_or_none()
                
                if not existing_review:
                    review_item = PatternReviewQueue(
                        organization=organization,
                        pattern1=suggestion['pattern1'],
                        pattern2=suggestion['pattern2'],
                        merged_pattern=suggestion['merged_pattern'],
                        similarity_score=suggestion['similarity'],
                        status='pending',
                        created_at=now
                    )
                    self.db.add(review_item)
                    review_queued += 1
        
        await self.db.commit()
        
        return {
            'patterns_learned': len(learned_patterns),
            'patterns_added': patterns_added,
            'patterns_updated': patterns_updated,
            'high_confidence_controls': len(high_confidence_controls),
            'merge_suggestions': len(merge_suggestions),
            'auto_merge_candidates': sum(1 for s in merge_suggestions if s['status'] == 'auto_merge'),
            'manual_review_queued': review_queued
        }
    
    def prune_low_frequency(self, organization: str) -> int:
        """
        Remove patterns with frequency below threshold (synchronous version).
        
        Args:
            organization: Organization name
            
        Returns:
            Number of patterns pruned
        """
        if not self.db:
            return 0
        
        result = self.db.execute(
            delete(ControlPattern).where(
                and_(
                    ControlPattern.organization == organization,
                    ControlPattern.frequency < self.min_frequency
                )
            )
        )
        self.db.commit()
        return result.rowcount
    
    async def prune_low_frequency_async(self, organization: str) -> int:
        """
        Remove patterns with frequency below threshold (async version).
        
        Args:
            organization: Organization name
            
        Returns:
            Number of patterns pruned
        """
        if not self.db:
            return 0
        
        result = await self.db.execute(
            delete(ControlPattern).where(
                and_(
                    ControlPattern.organization == organization,
                    ControlPattern.frequency < self.min_frequency
                )
            )
        )
        await self.db.commit()
        return result.rowcount
    
    async def load_patterns(self, organization: str):
        """
        Load patterns for an organization into cache.
        
        Args:
            organization: Organization name
        """
        if not self.db:
            return
        
        result = await self.db.execute(
            select(ControlPattern).where(ControlPattern.organization == organization)
        )
        patterns = result.scalars().all()
        
        self.patterns_cache[organization] = {
            p.pattern: p.frequency for p in patterns
        }
    
    def score_control_id(
        self, 
        control_id: Optional[str], 
        organization: str
    ) -> float:
        """
        Score a control ID against learned patterns for an organization.
        
        Args:
            control_id: The control ID to score
            organization: Organization name
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        if not control_id:
            return 0.0
        
        pattern = self.extract_pattern(control_id)
        if not pattern:
            return 0.3  # Invalid pattern format
        
        # Load patterns if not cached
        if organization not in self.patterns_cache:
            if self.db:
                # Synchronous load for scoring
                result = self.db.execute(
                    select(ControlPattern).where(ControlPattern.organization == organization)
                )
                patterns = result.scalars().all()
                self.patterns_cache[organization] = {
                    p.pattern: p.frequency for p in patterns
                }
            else:
                return 0.5  # No patterns available, neutral score
        
        org_patterns = self.patterns_cache[organization]
        
        # Exact match
        if pattern in org_patterns:
            frequency = org_patterns[pattern]
            # Score based on frequency (higher frequency = higher confidence)
            # Frequency 5 = 0.7, 10 = 0.8, 20+ = 0.95
            if frequency >= 20:
                return 0.95
            elif frequency >= 10:
                return 0.8 + (frequency - 10) * 0.015
            else:
                return 0.7 + (frequency - 5) * 0.02
        
        # Check for similar patterns
        max_similarity = 0.0
        for known_pattern in org_patterns.keys():
            similarity = self.calculate_pattern_similarity(pattern, known_pattern)
            max_similarity = max(max_similarity, similarity)
        
        # Similar pattern scoring
        if max_similarity >= 0.9:
            return 0.75  # Very similar to known pattern
        elif max_similarity >= 0.7:
            return 0.6  # Moderately similar
        elif max_similarity >= 0.5:
            return 0.5  # Somewhat similar
        else:
            return 0.3  # Unknown pattern structure
    
    def get_org_profile(self, organization: str) -> Dict[str, any]:
        """
        Get the pattern profile for an organization.
        
        Args:
            organization: Organization name
            
        Returns:
            Dictionary with pattern statistics
        """
        if organization not in self.patterns_cache:
            if self.db:
                result = self.db.execute(
                    select(ControlPattern).where(ControlPattern.organization == organization)
                )
                patterns = result.scalars().all()
                self.patterns_cache[organization] = {
                    p.pattern: p.frequency for p in patterns
                }
        
        org_patterns = self.patterns_cache.get(organization, {})
        
        if not org_patterns:
            return {
                'organization': organization,
                'total_patterns': 0,
                'total_occurrences': 0,
                'patterns': []
            }
        
        total_occurrences = sum(org_patterns.values())
        pattern_list = [
            {'pattern': p, 'frequency': f, 'percentage': round(f / total_occurrences * 100, 1)}
            for p, f in sorted(org_patterns.items(), key=lambda x: x[1], reverse=True)
        ]
        
        return {
            'organization': organization,
            'total_patterns': len(org_patterns),
            'total_occurrences': total_occurrences,
            'patterns': pattern_list
        }
