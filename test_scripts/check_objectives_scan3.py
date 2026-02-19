"""Check if objectives exist for scan 3"""
import sys
import asyncio
sys.path.insert(0, 'backend')

from app.database import AsyncSessionLocal
from app.models import ControlObjective
from sqlalchemy import select, func

async def check_objectives():
    async with AsyncSessionLocal() as session:
        # Count objectives for scan 3
        result = await session.execute(
            select(func.count(ControlObjective.id)).where(ControlObjective.scan_id == 3)
        )
        count = result.scalar()
        
        print(f"Total objectives for scan 3: {count}")
        
        if count > 0:
            # Show sample objectives
            result = await session.execute(
                select(ControlObjective)
                .where(ControlObjective.scan_id == 3)
                .limit(5)
            )
            objectives = result.scalars().all()
            
            print("\nSample objectives:")
            for obj in objectives:
                print(f"  {obj.objective_id}: line_ref={obj.line_ref}, page_refs={obj.page_refs}")
        else:
            print("\n❌ No objectives found for scan 3!")
            print("This means the extraction failed or was never run.")

if __name__ == "__main__":
    asyncio.run(check_objectives())
