from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, Float, LargeBinary, Boolean
import datetime

Base = declarative_base()

# --- Scan table for structured scan metadata ---
class Scan(Base):
    __tablename__ = "scan"
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer)
    product = Column(String(256))
    scan_date = Column(DateTime, default=datetime.datetime.utcnow)
    report_date = Column(DateTime)
    coverage_start = Column(DateTime)
    coverage_end = Column(DateTime)
    pdf_file = Column(LargeBinary)
    pdf_filename = Column(String(256))
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

# --- Entity tables for extracted data ---
class Company(Base):
    __tablename__ = "company"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    parent_company = Column(String(256))
    confidence = Column(Float)
    scan_id = Column(Integer)

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
    control_tsc_id = Column(String(128))  # Legacy: highest confidence TSC match
    control_coso_id = Column(String(128))  # Legacy: highest confidence COSO match
    control_tsc_similarity = Column(Float)
    control_coso_similarity = Column(Float)
    control_tsc_confidence_pct = Column(Integer)
    control_coso_confidence_pct = Column(Integer)
    control_closest_framework = Column(String(128))
    control_tsc_section = Column(String(128))
    control_coso_section = Column(String(128))
    control_soc_domain = Column(String(128))
    
    # Multi-match framework mappings (JSON arrays)
    # Expected schema for both TSC and COSO mappings:
    # [
    #   {
    #     "id": "CC7.2",           # Framework criterion ID (TSC ID or COSO principle number)
    #     "confidence": 0.95,      # Match confidence score (0.0-1.0)
    #     "reasoning": "...",      # Brief explanation of why this criterion matches
    #     "deviation": "..." or null  # Optional deviation text if applicable
    #   },
    #   ...
    # ]
    # IMPORTANT: These fields MUST be JSON arrays (not strings). The database enforces this
    # with CHECK constraints. Backend validation in control_extractor_v4.py and main.py converts
    # any malformed string data to proper arrays before insertion.
    control_tsc_mappings = Column(JSON)  # [{"id": "CC7.2", "confidence": 0.95, "reasoning": "...", "deviation": "..."}]
    control_coso_mappings = Column(JSON)  # [{"id": "10", "confidence": 0.88, "reasoning": "...", "deviation": "..."}]
    control_status = Column(String(64))
    merged_to_control_id = Column(String(128))
    control_gpt_opinion = Column(Text)
    control_gpt_reasoning = Column(Text)
    control_confidence = Column(Float)
    confidence_calc = Column(Text)
    scan_id = Column(Integer)
    annotation = Column(Text)
    # Verification and pattern scoring fields
    verification_status = Column(String(32))  # 'verified', 'pending', null
    verification_metadata = Column(JSON)  # Detailed scoring breakdown
    pattern_confidence = Column(Float)  # Score from pattern library (0.0-1.0)
    final_confidence = Column(Float)  # Combined multi-factor confidence

class CUEC(Base):
    __tablename__ = "cuec"
    id = Column(Integer, primary_key=True, autoincrement=True)
    cuec_seq = Column(Integer)
    cuec_tsc_id = Column(String(128))  # Legacy: highest confidence TSC match
    cuec_description = Column(Text)
    cuec_line_ref = Column(Integer)
    cuec_confidence = Column(Float)
    cuec_gpt_opinion = Column(String(32))
    cuec_distance_from_cuec_keywords = Column(Integer)
    cuec_gpt_reasoning = Column(Text)
    cuec_framework_alignment = Column(String(128))
    cuec_framework_alignment_id = Column(String(128))
    cuec_justification = Column(Text)
    cuec_coso_id = Column(String(128))  # Legacy: highest confidence COSO match
    cuec_tsc_similarity = Column(Float)
    cuec_coso_similarity = Column(Float)
    cuec_tsc_confidence_pct = Column(Integer)
    cuec_coso_confidence_pct = Column(Integer)
    cuec_closest_framework = Column(String(128))
    cuec_confidence_justification = Column(Text)
    
    # Multi-match framework mappings (JSON arrays)
    # Same schema as Control mappings above - see control_tsc_mappings documentation
    # IMPORTANT: Must be JSON arrays, enforced by database CHECK constraints
    # Backend validation in main.py ensures type safety before insertion
    cuec_tsc_mappings = Column(JSON)  # [{"id": "CC7.2", "confidence": 0.95, "reasoning": "...", "deviation": null}]
    cuec_coso_mappings = Column(JSON)  # [{"id": "10", "confidence": 0.88, "reasoning": "...", "deviation": null}]
    scan_id = Column(Integer)
    annotation = Column(Text)
    control_strength = Column(String(32))  # High, Medium, Low

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
