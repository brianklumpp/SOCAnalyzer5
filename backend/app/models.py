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
    control_page_ref = Column(Integer)
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
