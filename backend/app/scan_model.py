from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, Float
import datetime

Base = declarative_base()

# ...existing code...

class Scan(Base):
    __tablename__ = "scan"
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer)
    product = Column(String(256))
    scan_date = Column(DateTime, default=datetime.datetime.utcnow)
    report_date = Column(DateTime)
    coverage_start = Column(DateTime)
    coverage_end = Column(DateTime)
    pdf_file = Column(String(512))
    pdf_filename = Column(String(256))
    extracted_text = Column(Text)
    result_json = Column(JSON)
    gpt_cost = Column(Float)
    gpt_model = Column(String(128))
    estimated_time_seconds = Column(Float)
