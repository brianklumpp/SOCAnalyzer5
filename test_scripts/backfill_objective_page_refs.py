#!/usr/bin/env python3
"""Backfill page_refs for existing objectives using the improved find_page_refs function."""

import sys
import os
import re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models import ControlObjective, Scan

# Import the improved find_page_refs function
def find_page_refs(objective_text: str, extracted_text: str):
    """Find page references - matches backend/app/extractors/objective_extractor.py"""
    from typing import List
    page_pattern = r'=== PAGE (\d+) ==='
    pages = []
    
    def normalize_text(text):
        return re.sub(r'\s+', ' ', text).strip().lower()
    
    page_sections = re.split(page_pattern, extracted_text)
    page_numbers = []
    for i in range(1, len(page_sections), 2):
        try:
            page_numbers.append(int(page_sections[i]))
        except (ValueError, IndexError):
            pass
    
    for key_length in [100, 60, 40, 25]:
        if len(objective_text) < key_length:
            continue
        search_key = normalize_text(objective_text[:key_length])
        for idx, section in enumerate(page_sections[::2]):
            if normalize_text(section).find(search_key) != -1:
                page_idx = idx // 2
                if page_idx < len(page_numbers):
                    pages.append(page_numbers[page_idx])
                    return pages
    
    if len(objective_text) >= 20:
        search_key = normalize_text(objective_text[:20])
        for idx, section in enumerate(page_sections[::2]):
            if normalize_text(section).find(search_key) != -1:
                page_idx = idx // 2
                if page_idx < len(page_numbers):
                    pages.append(page_numbers[page_idx])
                    return pages
    
    return pages

DATABASE_URL = "postgresql+asyncpg://soc2_analyzer:puntitforthewin@localhost:5433/soc2analyzer"

async def backfill_page_refs():
    """Backfill page_refs for all objectives in the latest scan."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Get latest scan
        result = await session.execute(
            select(Scan).order_by(Scan.id.desc()).limit(1)
        )
        scan = result.scalar_one_or_none()
        
        if not scan:
            print("No scans found")
            return
        
        print(f"Processing scan ID: {scan.id}")
        print(f"Scan file: {scan.pdf_filename}")
        
        extracted_text = scan.extracted_text
        if not extracted_text:
            print("ERROR: No extracted_text in scan!")
            return
        
        # Get all objectives for this scan
        result = await session.execute(
            select(ControlObjective).where(
                ControlObjective.scan_id == scan.id
            )
        )
        objectives = result.scalars().all()
        
        print(f"\nFound {len(objectives)} objectives")
        
        updated_count = 0
        failed_count = 0
        
        for obj in objectives:
            try:
                # Find page refs using improved function
                page_refs = find_page_refs(obj.objective_text, extracted_text)
                
                if page_refs and page_refs != obj.page_refs:
                    obj.page_refs = page_refs
                    updated_count += 1
                    print(f"✓ {obj.objective_id or obj.id}: page_refs={page_refs}")
                elif not page_refs:
                    failed_count += 1
                    print(f"✗ {obj.objective_id or obj.id}: Could not find page refs")
                else:
                    print(f"- {obj.objective_id or obj.id}: Already has page_refs={obj.page_refs}")
                    
            except Exception as e:
                print(f"ERROR processing objective {obj.id}: {e}")
                failed_count += 1
        
        # Commit changes
        await session.commit()
        
        print(f"\n{'='*60}")
        print(f"SUMMARY:")
        print(f"  Updated: {updated_count}")
        print(f"  Failed: {failed_count}")
        print(f"  Total: {len(objectives)}")
        print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(backfill_page_refs())
