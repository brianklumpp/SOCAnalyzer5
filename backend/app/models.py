from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, JSON, Text
import datetime

Base = declarative_base()


class ScanHistory(Base):
    __tablename__ = "scan_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    filename = Column(String(256), nullable=False)
    results = Column(JSON, nullable=False)

# --- Entity tables for extracted data ---
class Company(Base):
    __tablename__ = "company"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    parent_company = Column(String(256))
    confidence = Column(Integer)
    scan_id = Column(Integer)

class Control(Base):
    __tablename__ = "control"
    id = Column(Integer, primary_key=True, autoincrement=True)
    control_id = Column(String(128))
    description = Column(Text)
    scan_id = Column(Integer)

class CUEC(Base):
    __tablename__ = "cuec"
    id = Column(Integer, primary_key=True, autoincrement=True)
    cuec_id = Column(String(128))
    description = Column(Text)
    scan_id = Column(Integer)

class SubserviceOrg(Base):
    __tablename__ = "subservice_org"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256))
    scan_id = Column(Integer)

class Product(Base):
    __tablename__ = "product"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256))
    scan_id = Column(Integer)

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
