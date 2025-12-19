from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, Float, LargeBinary, Boolean, Enum, ForeignKey
import datetime
from datetime import timezone
import enum
from backend.app.base import Base

# Helper function for timezone-aware current time
def get_local_now():
    """Return current local time as timezone-aware datetime"""
    return datetime.datetime.now(timezone.utc).astimezone()


class ReportType(enum.Enum):
    """Enumeration for SOC report types"""
    SOC1 = "SOC1"
    SOC2 = "SOC2"
    COMBINED = "COMBINED"

# --- Scan table for structured scan metadata ---
class Scan(Base):
    __tablename__ = "scan"
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer)
    company = Column(String(256))  # Audited organization name
    product = Column(String(256))
    scan_date = Column(DateTime, default=get_local_now)
    report_date = Column(DateTime)
    coverage_start = Column(DateTime)
    coverage_end = Column(DateTime)
    pdf_file = Column(LargeBinary)
    pdf_filename = Column(String(256))
    embedded_pdf_file = Column(LargeBinary)  # Stores embedded consent agreement PDF if present
    embedded_pdf_filename = Column(String(256))  # Filename of the embedded PDF
    extracted_text = Column(Text)
    result_json = Column(JSON)
    gpt_cost = Column(Float)
    gpt_model = Column(String(128))
    estimated_time_seconds = Column(Float)
    auditor = Column(Text)
    gpt_usage_details = Column(JSON)
    executive_summary = Column(JSON)
    executive_summary_stale = Column(Boolean, default=False)  # Flag when summary needs regeneration
    is_sox_vendor = Column(Boolean, default=False)  # Flag if vendor is subject to SOX compliance
    
    # SOC 1 Type 2 Support
    report_type = Column(Enum(ReportType), default=ReportType.SOC2, nullable=False)  # SOC1, SOC2, or COMBINED
    as_of_date = Column(DateTime)  # Point-in-time date for SOC 1 reports
    progress_status = Column(String(128))  # Current extraction step for real-time progress tracking
    elapsed_seconds = Column(Float)  # Actual processing time for dynamic estimation
    toc_page_offset = Column(Integer)  # Page offset for TOC - converts document page numbers to PDF page numbers
    
    # Multi-framework support (Phase 1)
    detected_standards = Column(JSON)  # Standards detected in report: ["ISAE 3402", "SSAE 18", "CSAE 3416"]
    active_frameworks = Column(JSON)  # Frameworks used for mapping: ["TSC", "COSO", "ISAE3402", "FINANCIAL_ASSERTIONS"]

# --- Entity tables for extracted data ---
class Company(Base):
    __tablename__ = "company"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    parent_company = Column(String(256))
    confidence = Column(Float)
    scan_id = Column(Integer)
    company_domain = Column(String(256), index=True)  # Company website domain for logo fetching
    logo_url = Column(String(512))  # Cached logo URL from Clearbit API

class Control(Base):
    __tablename__ = "control"
    id = Column(Integer, primary_key=True, autoincrement=True)
    control_id = Column(String(128))
    control_desc = Column(Text)
    control_test = Column(Text)
    control_test_results = Column(Text)
    has_deviation = Column(Boolean)
    deviation_desc = Column(Text)
    control_page_refs = Column(JSON)  # [51, 52, 89] - pages where control appears
    control_line_ref = Column(Integer)
    control_seq = Column(Integer)
    
    # ⚠️ LEGACY COLUMNS REMOVED (v2.1.0): control_tsc_id, control_coso_id, control_tsc_similarity, control_soc_domain, etc.
    # ✅ USE INSTEAD: framework_mappings (JSON), primary_framework, primary_criterion_id, primary_confidence
    # See DEPRECATED_FEATURES.md for details
    
    # SOC 1 Type 2 Support - Financial Assertions
    # Schema: [{"id": "EO1", "name": "Existence/Occurrence", "confidence": 0.92, "reasoning": "Control validates transactions occurred"}]
    financial_assertions = Column(JSON)  # Financial assertion mappings for SOC 1 controls
    framework_category = Column(String(32))  # "SOC1", "SOC2", "BOTH", "AMBIGUOUS" - for combined reports
    
    # Phase 1 multi-framework mapping support
    # Universal framework mappings - supports unlimited frameworks beyond TSC/COSO
    # Schema: {"TSC": [{...}], "COSO": [{...}], "FINANCIAL_ASSERTIONS": [{...}], "ISAE3402": [{...}], ...}
    framework_mappings = Column(JSON)  # All framework mappings in one unified structure
    primary_framework = Column(String(64))  # Framework with highest confidence match (e.g., "TSC", "COSO")
    primary_criterion_id = Column(String(128))  # Best matching criterion ID across all frameworks
    primary_confidence = Column(Float)  # Confidence score of best match
    
    control_status = Column(String(64))
    merged_to_control_id = Column(String(128))
    control_gpt_opinion = Column(Text)
    control_gpt_reasoning = Column(Text)
    control_confidence = Column(Float)
    confidence_calc = Column(Text)
    scan_id = Column(Integer)
    annotation = Column(Text)
    analyst_notes = Column(Text)  # Analyst notes for manual annotations
    edit_log = Column(Text)  # Log of manual edits made to this control
    # Verification and pattern scoring fields
    verification_status = Column(String(32))  # 'verified', 'pending', null
    verification_metadata = Column(JSON)  # Detailed scoring breakdown
    pattern_confidence = Column(Float)  # Score from pattern library (0.0-1.0)
    final_confidence = Column(Float)  # Combined multi-factor confidence
    # Deviation summary - AI-generated plain language explanation of what a deviation means
    deviation_summary = Column(Text)  # GPT-generated summary for controls with deviation=true
    # Management response to deviations - extracted from report or manually added
    management_response_text = Column(Text)  # Management's response/remediation plan for the deviation
    management_response_page_refs = Column(JSON)  # [67, 68] - pages where management response appears
    management_response_line_ref = Column(Integer)  # Starting line number of response in extracted text
    management_response_confidence = Column(Float)  # GPT self-evaluation confidence (0-1)
    response_detection_method = Column(String(32))  # 'inline_nearby', 'section_match', 'manual'
    # Merge history - audit trail of all merge events
    merge_history = Column(JSON)  # [{"timestamp": "2025-01-07T12:34:56", "type": "auto|manual", "confidence": 0.85, "merged_from_ids": ["CTL-001", "CTL-002"], "reason": "..."}]
    # Duplicate instance tracking - for controls that appear multiple times for different criteria
    is_duplicate_instance = Column(Boolean, default=False)  # True if this is an intentional duplicate (same control, different TSC/COSO criteria or test procedures)
    duplicate_group_id = Column(String(128))  # UUID linking all instances of the same control
    instance_differentiator = Column(JSON)  # {"criteria": ["CC7.2"], "test_variance": "...", "deviation_variance": "...", "instance_number": 1, "total_instances": 3}
    # Audit fields for tracking manual edits
    updated_at = Column(DateTime)  # Timestamp of last update
    updated_by_user_id = Column(Integer, ForeignKey('users.id'))  # User who last updated this control

class CUEC(Base):
    __tablename__ = "cuec"
    id = Column(Integer, primary_key=True, autoincrement=True)
    cuec_seq = Column(Integer)
    cuec_description = Column(Text)
    cuec_line_ref = Column(Integer)
    cuec_page_refs = Column(JSON)  # Array of page numbers where CUEC appears
    cuec_confidence = Column(Float)
    cuec_gpt_opinion = Column(String(32))
    cuec_distance_from_cuec_keywords = Column(Integer)
    cuec_gpt_reasoning = Column(Text)
    cuec_justification = Column(Text)
    cuec_confidence_justification = Column(Text)
    
    # Phase 1 multi-framework mapping support
    # Universal framework mappings - supports unlimited frameworks beyond TSC/COSO
    framework_mappings = Column(JSON)  # All framework mappings in one unified structure
    primary_framework = Column(String(64))  # Framework with highest confidence match
    primary_criterion_id = Column(String(128))  # Best matching criterion ID across all frameworks
    primary_confidence = Column(Float)  # Confidence score of best match
    
    scan_id = Column(Integer)
    annotation = Column(Text)
    analyst_notes = Column(Text)  # Analyst notes for manual annotations
    edit_log = Column(Text)  # Log of manual edits made to this CUEC
    control_strength = Column(String(32))  # High, Medium, Low
    
    # Audit fields for tracking manual edits
    updated_at = Column(DateTime)  # Timestamp of last update
    updated_by_user_id = Column(Integer, ForeignKey('users.id'))  # User who last updated this CUEC

class SubserviceOrg(Base):
    __tablename__ = "subservice_org"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256))
    confidence = Column(Float)
    scan_id = Column(Integer)
    third_party_description = Column(Text)
    third_party_page_ref = Column(Text)
    third_party_confidence = Column(Float)
    distance_from_so_keywords = Column(Float)
    likely_so = Column(String(64))
    common_so = Column(String(64))
    source_context = Column(Text)
    confidence_justification = Column(Text)
    third_party_controls = Column(JSON)
    annotation = Column(Text)
    analyst_notes = Column(Text)  # Analyst notes for manual annotations
    edit_log = Column(Text)  # Log of manual edits made to this subservice org
    
    # Audit fields for tracking manual edits
    updated_at = Column(DateTime)  # Timestamp of last update
    updated_by_user_id = Column(Integer, ForeignKey('users.id'))  # User who last updated this subservice org

class Product(Base):
    __tablename__ = "product"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256))
    scan_id = Column(Integer)

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)

class ControlPattern(Base):
    """
    Learned control ID patterns per organization.
    Used for pattern-based confidence scoring.
    """
    __tablename__ = "control_pattern"
    id = Column(Integer, primary_key=True, autoincrement=True)
    organization = Column(String(256), nullable=False)
    pattern = Column(String(128), nullable=False)  # e.g., "IAM-XX-XX", "IM.X.X"
    frequency = Column(Integer, default=1)  # Number of times seen
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    scan_ids = Column(JSON)  # List of scan IDs where this pattern appeared

class PatternReviewQueue(Base):
    """
    Queue for manual review of ambiguous pattern merge suggestions.
    """
    __tablename__ = "pattern_review_queue"
    id = Column(Integer, primary_key=True, autoincrement=True)
    organization = Column(String(256), nullable=False)
    pattern1 = Column(String(128), nullable=False)
    pattern2 = Column(String(128), nullable=False)
    merged_pattern = Column(String(128), nullable=False)
    similarity_score = Column(Float, nullable=False)
    status = Column(String(32), default='pending')  # 'pending', 'approved', 'rejected'
    created_at = Column(DateTime, nullable=False)
    reviewed_at = Column(DateTime)
    reviewed_by = Column(String(128))

class ConfidenceWeights(Base):
    """
    Configurable weights for 5-factor confidence scoring.
    Supports global defaults and organization-specific overrides.
    """
    __tablename__ = "confidence_weights"
    id = Column(Integer, primary_key=True, autoincrement=True)
    organization = Column(String(256), nullable=True)  # NULL = global default
    gpt_weight = Column(Float, nullable=False, default=0.25)
    pattern_weight = Column(Float, nullable=False, default=0.20)
    structure_weight = Column(Float, nullable=False, default=0.20)
    framework_weight = Column(Float, nullable=False, default=0.20)
    deviation_weight = Column(Float, nullable=False, default=0.15)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class ConfidenceWeightAudit(Base):
    """
    Audit log for confidence weight changes (compliance tracking).
    """
    __tablename__ = "confidence_weight_audit"
    id = Column(Integer, primary_key=True, autoincrement=True)
    weight_config_id = Column(Integer, nullable=True)  # FK to confidence_weights, NULL if deleted
    organization = Column(String(256), nullable=True)  # Denormalized for deleted configs
    changed_by_user_id = Column(Integer, nullable=True)  # User who made the change
    old_weights = Column(JSON, nullable=True)  # {"gpt": 0.25, "pattern": 0.20, ...}
    new_weights = Column(JSON, nullable=False)  # {"gpt": 0.30, "pattern": 0.15, ...}
    change_reason = Column(Text, nullable=True)  # Admin-provided reason
    change_type = Column(String(32), nullable=False)  # 'create', 'update', 'delete', 'reset'
    changed_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

class ControlReview(Base):
    """
    Admin review records for low-confidence controls.
    Used to collect feedback for weight tuning.
    """
    __tablename__ = "control_review"
    id = Column(Integer, primary_key=True, autoincrement=True)
    control_id = Column(Integer, nullable=False)  # FK to control.id
    scan_id = Column(Integer, nullable=False)  # Denormalized for easier querying
    organization = Column(String(256), nullable=True)  # Denormalized from company
    reviewed_by_user_id = Column(Integer, nullable=True)  # User who reviewed
    review_status = Column(String(32), nullable=False)  # 'correct', 'false_positive', 'uncertain'
    review_notes = Column(Text, nullable=True)  # Admin notes
    low_factor_flags = Column(JSON, nullable=True)  # ["pattern", "structure", "framework", ...]
    final_confidence_at_review = Column(Float, nullable=True)  # Snapshot of confidence when reviewed
    reviewed_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

class ReportTypeDetection(Base):
    """
    Cache for GPT-based report type detection results.
    Stores detection by PDF hash to avoid re-analyzing same files.
    """
    __tablename__ = "report_type_detections"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pdf_hash = Column(String(64), nullable=False, unique=True, index=True)
    detected_type = Column(String(32), nullable=False)  # 'SOC1', 'SOC2', 'COMBINED'
    detected_subtype = Column(String(32), nullable=False)  # 'TYPE1', 'TYPE2'
    confidence = Column(Float, nullable=False)
    evidence = Column(JSON, nullable=True)  # Array of key evidence strings
    analysis_stage = Column(String(16), nullable=False)  # 'quick' or 'deep'
    user_confirmed_type = Column(String(32), nullable=True)  # User override if any
    user_confirmed_subtype = Column(String(32), nullable=True)
    user_confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # For TTL-based cache expiry


class Baseline(Base):
    """
    Baseline snapshots for validation and comparison.
    Stores approved report state for detecting regressions.
    """
    __tablename__ = "baselines"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    scan_id = Column(Integer, nullable=False, index=True)  # FK to scan.id
    description = Column(Text, nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    snapshot_data = Column(JSON, nullable=False)  # Full report snapshot for comparison
    created_by = Column(String(128), nullable=True)  # User who created baseline
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)


class OrganizationPattern(Base):
    """
    Learned patterns for organization naming and detection.
    Helps identify service organizations across reports.
    """
    __tablename__ = "organization_patterns"
    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_name = Column(String(256), nullable=False, unique=True, index=True)
    pattern_variants = Column(JSON, nullable=False)  # Array of name variations
    pattern_type = Column(String(32), nullable=False)  # 'exact', 'fuzzy', 'abbreviation'
    confidence = Column(Float, nullable=False, default=1.0)
    times_seen = Column(Integer, nullable=False, default=1)
    last_seen_scan_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)


# ========== Authentication Models ==========

class User(Base):
    """User model for storing user authentication and profile information."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(128), unique=True, nullable=False, index=True)
    email = Column(String(256), unique=True, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    full_name = Column(String(256), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}', is_admin={self.is_admin})>"


class RefreshToken(Base):
    """Refresh token model for managing long-lived authentication tokens."""
    
    __tablename__ = "refresh_tokens"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(256), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    
    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.revoked})>"
