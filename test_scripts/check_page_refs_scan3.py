"""Check page_refs values for scan 3 objectives"""
import sys
import asyncio
sys.path.insert(0, 'backend')

from app.database import AsyncSessionLocal
from app.models import ControlObjective
from sqlalchemy import select

async def check_page_refs():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ControlObjective.id, ControlObjective.objective_id, 
                   ControlObjective.line_ref, ControlObjective.page_refs)
            .where(ControlObjective.scan_id == 3)
            .limit(10)
        )
        rows = result.all()
        
        if not rows:
            print("❌ No objectives found for scan 3")
            return
        
        print(f"Found {len(rows)} objectives (showing first 10):\n")
        for row in rows:
            print(f"  ID={row[0]}, objective_id={row[1]}, line_ref={row[2]}, page_refs={row[3]}")
        
        # Count how many have NULL page_refs
        result2 = await session.execute(
            select(ControlObjective.id)
            .where(ControlObjective.scan_id == 3)
            .where(ControlObjective.page_refs.is_(None))
        )
        null_count = len(result2.all())
        
        result3 = await session.execute(
            select(ControlObjective.id)
            .where(ControlObjective.scan_id == 3)
        )
        total = len(result3.all())
        
        print(f"\nStats: {null_count}/{total} objectives have NULL page_refs")

if __name__ == "__main__":
    asyncio.run(check_page_refs())
