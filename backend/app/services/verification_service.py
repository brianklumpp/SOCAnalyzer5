"""
Control Verification Service

Provides async verification of extracted controls after extraction completes.
Runs only on-demand (not during extraction) to validate control extraction
quality using pattern library scoring and multi-factor confidence analysis.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.models import Control, Scan, Company
from backend.app.utils.pattern_library import ControlPatternLibrary


class ControlVerificationService:
    """
    Async service for verifying extracted controls post-extraction.
    
    Features:
    - Pattern-based confidence scoring
    - Multi-factor verification
    - Status tracking (verified/pending)
    - Detailed metadata logging
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def start_verification(
        self,
        scan_id: int,
        db: AsyncSession,
        organization: str = None
    ) -> Dict[str, Any]:
        """
        Trigger verification for all controls in a scan.
        
        Args:
            scan_id: The scan ID to verify
            db: Async database session
            organization: Organization name (if None, fetched from scan)
            
        Returns:
            Dictionary with verification statistics
        """
        self.logger.info(f"Starting verification for scan {scan_id}")
        start_time = datetime.utcnow()
        
        # Fetch scan details
        scan_result = await db.execute(
            select(Scan).where(Scan.id == scan_id)
        )
        scan = scan_result.scalar_one_or_none()
        
        if not scan:
            raise ValueError(f"Scan {scan_id} not found")
        
        # Get organization if not provided
        if not organization and scan.company_id:
            company_result = await db.execute(
                select(Company).where(Company.id == scan.company_id)
            )
            company = company_result.scalar_one_or_none()
            if company:
                organization = company.name
        
        if not organization:
            self.logger.warning(f"No organization found for scan {scan_id}, using default")
            organization = "Unknown"
        
        # Fetch all controls for this scan
        controls_result = await db.execute(
            select(Control).where(Control.scan_id == scan_id)
        )
        controls = controls_result.scalars().all()
        
        if not controls:
            self.logger.warning(f"No controls found for scan {scan_id}")
            return {
                'scan_id': scan_id,
                'verified': 0,
                'pending': 0,
                'total': 0,
                'organization': organization,
                'timestamp': start_time.isoformat()
            }
        
        # Initialize pattern library
        pattern_lib = ControlPatternLibrary(db_session=db)
        await pattern_lib.load_patterns(organization)
        
        # Verify each control
        verified_count = 0
        pending_count = 0
        
        for control in controls:
            verification = await self._verify_control(
                control,
                organization,
                pattern_lib
            )
            
            # Update control with verification data
            control.verification_status = verification['status']
            control.verification_metadata = verification['metadata']
            
            if verification['status'] == 'verified':
                verified_count += 1
            else:
                pending_count += 1
        
        # Commit all updates
        await db.commit()
        
        end_time = datetime.utcnow()
        elapsed = (end_time - start_time).total_seconds()
        
        stats = {
            'scan_id': scan_id,
            'verified': verified_count,
            'pending': pending_count,
            'total': len(controls),
            'organization': organization,
            'timestamp': end_time.isoformat(),
            'duration_seconds': round(elapsed, 2)
        }
        
        self.logger.info(f"Verification complete for scan {scan_id}: {stats}")
        return stats
    
    async def _verify_control(
        self,
        control: Control,
        organization: str,
        pattern_lib: ControlPatternLibrary
    ) -> Dict[str, Any]:
        """
        Verify a single control using 5-factor metadata.
        Reads existing verification_metadata from extraction instead of recalculating.
        
        Args:
            control: The Control model instance
            organization: Organization name
            pattern_lib: Pattern library instance
            
        Returns:
            Dictionary with status and metadata
        """
        # Check if control already has 5-factor metadata from extraction
        if control.verification_metadata and isinstance(control.verification_metadata, dict):
            metadata = control.verification_metadata.copy()
            
            # Extract factor scores
            factor_scores = metadata.get('factor_scores', {})
            final_conf = metadata.get('final_confidence', control.final_confidence or 0.5)
            
            # Add verification timestamp
            metadata['verified_at'] = datetime.utcnow().isoformat()
            metadata['verified_by'] = 'system'
            
            # Determine status based on confidence threshold
            if final_conf >= 0.5:
                status = 'verified'
            else:
                status = 'pending'
            
            # Build low confidence reasons based on specific factors
            if final_conf < 0.5:
                reasons = []
                
                if factor_scores.get('gpt_confidence', 0) < 0.5:
                    reasons.append(f"Low GPT confidence ({factor_scores.get('gpt_confidence', 0):.2f})")
                
                if factor_scores.get('pattern_confidence', 0) < 0.3:
                    reasons.append(f"Unknown pattern ({factor_scores.get('pattern_confidence', 0):.2f})")
                
                if factor_scores.get('structure_score', 0) < 0.5:
                    reasons.append(f"Low structure score ({factor_scores.get('structure_score', 0):.2f} - missing test/results/desc)")
                
                if factor_scores.get('framework_score', 0) <= 0.5:
                    reasons.append(f"No framework mappings ({factor_scores.get('framework_score', 0):.2f})")
                
                if factor_scores.get('deviation_score', 0) < 0.5:
                    reasons.append(f"Inconsistent deviation flag ({factor_scores.get('deviation_score', 0):.2f})")
                
                metadata['low_confidence_reasons'] = reasons
            
            return {
                'status': status,
                'metadata': metadata
            }
        
        # Fallback: Old 2-factor calculation for controls extracted before 5-factor implementation
        else:
            # Calculate pattern confidence
            pattern_score = pattern_lib.score_control_id(control.control_id, organization)
            
            # Get GPT confidence
            gpt_conf = control.control_confidence or 0.5
            
            # Calculate final confidence: 60% GPT + 40% pattern (legacy formula)
            final_conf = (0.6 * gpt_conf) + (0.4 * pattern_score)
            
            # Update control fields if not already set
            if control.pattern_confidence is None:
                control.pattern_confidence = pattern_score
            if control.final_confidence is None:
                control.final_confidence = final_conf
            
            # Determine status based on confidence thresholds
            if final_conf >= 0.5:
                status = 'verified'
            else:
                status = 'pending'
            
            # Build metadata (legacy format)
            metadata = {
                'gpt_confidence': round(gpt_conf, 3),
                'pattern_confidence': round(pattern_score, 3),
                'final_confidence': round(final_conf, 3),
                'verified_at': datetime.utcnow().isoformat(),
                'verified_by': 'system',
                'method': 'legacy-2-factor',
                'factors': {
                    'has_control_id': bool(control.control_id),
                    'has_tests': bool(control.control_test),
                    'has_results': bool(control.control_test_results),
                    'has_deviation': bool(control.has_deviation),
                    'pattern_known': pattern_score > 0.5
                }
            }
            
            # Add reasoning for low confidence
            if final_conf < 0.5:
                reasons = []
                if not control.control_id:
                    reasons.append("Missing control ID")
                if not control.control_test:
                    reasons.append("Missing test procedures")
                if pattern_score < 0.3:
                    reasons.append(f"Unknown pattern ({pattern_score:.2f})")
                if gpt_conf < 0.5:
                    reasons.append(f"Low GPT confidence ({gpt_conf:.2f})")
                
                metadata['low_confidence_reasons'] = reasons
            
            return {
                'status': status,
                'metadata': metadata
            }
    
    async def get_verification_status(
        self,
        scan_id: int,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get verification status for a scan.
        
        Args:
            scan_id: The scan ID
            db: Async database session
            
        Returns:
            Dictionary with verification statistics
        """
        controls_result = await db.execute(
            select(Control).where(Control.scan_id == scan_id)
        )
        controls = controls_result.scalars().all()
        
        verified = sum(1 for c in controls if c.verification_status == 'verified')
        pending = sum(1 for c in controls if c.verification_status == 'pending' or c.verification_status is None)
        low_confidence = sum(1 for c in controls if (c.final_confidence or 0) < 0.5)
        
        # Calculate confidence distribution
        confidence_buckets = {
            '0.0-0.3': 0,
            '0.3-0.5': 0,
            '0.5-0.7': 0,
            '0.7-0.9': 0,
            '0.9-1.0': 0
        }
        
        for control in controls:
            conf = control.final_confidence or control.control_confidence or 0.5
            if conf < 0.3:
                confidence_buckets['0.0-0.3'] += 1
            elif conf < 0.5:
                confidence_buckets['0.3-0.5'] += 1
            elif conf < 0.7:
                confidence_buckets['0.5-0.7'] += 1
            elif conf < 0.9:
                confidence_buckets['0.7-0.9'] += 1
            else:
                confidence_buckets['0.9-1.0'] += 1
        
        return {
            'scan_id': scan_id,
            'total': len(controls),
            'verified': verified,
            'pending': pending,
            'low_confidence': low_confidence,
            'confidence_distribution': confidence_buckets
        }
    
    async def learn_patterns_from_scan(
        self,
        scan_id: int,
        db: AsyncSession,
        organization: str = None
    ) -> Dict[str, Any]:
        """
        Learn patterns from a completed scan's validated controls.
        Called automatically after extraction completes.
        
        Args:
            scan_id: The scan ID
            db: Async database session
            organization: Organization name
            
        Returns:
            Dictionary with learning statistics
        """
        self.logger.info(f"Learning patterns from scan {scan_id}")
        
        # Get organization if not provided
        if not organization:
            scan_result = await db.execute(
                select(Scan).where(Scan.id == scan_id)
            )
            scan = scan_result.scalar_one_or_none()
            
            if scan and scan.company_id:
                company_result = await db.execute(
                    select(Company).where(Company.id == scan.company_id)
                )
                company = company_result.scalar_one_or_none()
                if company:
                    organization = company.name
        
        if not organization:
            organization = "Unknown"
        
        # Fetch high-confidence controls
        controls_result = await db.execute(
            select(Control).where(
                Control.scan_id == scan_id,
                Control.control_confidence >= 0.9
            )
        )
        controls = controls_result.scalars().all()
        
        # Convert to dict format for pattern library
        controls_data = [
            {
                'control_id': c.control_id,
                'control_confidence': c.control_confidence
            }
            for c in controls
        ]
        
        # Learn patterns
        pattern_lib = ControlPatternLibrary(db_session=db)
        learning_stats = await pattern_lib.learn_from_scan(
            scan_id=scan_id,
            organization=organization,
            controls=controls_data
        )
        
        self.logger.info(f"Pattern learning complete: {learning_stats}")
        return learning_stats
