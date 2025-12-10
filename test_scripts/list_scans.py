#!/usr/bin/env python3
"""
Quick scrip        latest = scans[0]
        print("="*80)
        print(f"\n✅ Latest Scan ID: {latest.id}")
        print(f"   PDF: {latest.pdf_filename or 'N/A'}")
        print(f"\n🌐 FRONTEND URL: http://localhost:3000/app/report/{latest.id}")
        print(f"🔧 API URL: http://localhost:8000/report/{latest.id}")
        print("\n" + "="*80)
        print("📋 QUICK START:")
        print("   1. Start frontend: cd frontend && npm start")
        print("   2. Open URL: http://localhost:3000/app/report/" + str(latest.id))
        print("="*80 + "\n")ll scans in the database
"""
import sys
import asyncio
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.database import get_db
from app.models import Scan
from sqlalchemy.future import select

async def list_scans():
    """List all scans from database"""
    async for db in get_db():
        result = await db.execute(
            select(Scan).order_by(Scan.id.desc())
        )
        scans = result.scalars().all()
        
        if not scans:
            print("\n❌ No scans found in database")
            return
        
        print("\n" + "="*80)
        print("AVAILABLE SCANS".center(80))
        print("="*80 + "\n")
        
        for scan in scans:
            print(f"📊 Scan ID: {scan.id}")
            print(f"   Product: {scan.product or 'N/A'}")
            print(f"   PDF File: {scan.pdf_filename or 'N/A'}")
            print(f"   Scan Date: {scan.scan_date or 'N/A'}")
            print(f"   Report Date: {scan.report_date or 'N/A'}")
            print(f"   Auditor: {scan.auditor or 'N/A'}")
            print()
        
        latest = scans[0]
        print("="*80)
        print(f"\n✅ Latest Scan ID: {latest.id}")
        print(f"   PDF: {latest.pdf_filename or 'N/A'}")
        print(f"\n🌐 FRONTEND URL: http://localhost:3000/report/{latest.id}")
        print(f"🔧 API URL: http://localhost:8000/report/{latest.id}")
        print("\n" + "="*80)
        print("� QUICK START:")
        print("   1. Start frontend: cd frontend && npm start")
        print("   2. Open URL: http://localhost:3000/report/" + str(latest.id))
        print("="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(list_scans())
