import asyncio
import sys
sys.path.insert(0, 'backend')
from app.database import get_db
from app.models import Scan, Control, Company, CUEC
from sqlalchemy.future import select

async def check_scan_28():
    async for db in get_db():
        # Get scan 28
        result = await db.execute(select(Scan).where(Scan.id == 28))
        scan = result.scalar_one_or_none()
        
        if not scan:
            print("❌ Scan 28 NOT FOUND in database")
            return
        
        print(f"✅ Scan 28 EXISTS")
        print(f"   Product: {scan.product}")
        print(f"   Scan Date: {scan.scan_date}")
        print(f"   Has result_json: {bool(scan.result_json)}")
        print(f"   result_json keys: {list(scan.result_json.keys()) if scan.result_json else 'None'}")
        
        # Check related data
        controls = (await db.execute(select(Control).where(Control.scan_id == 28))).scalars().all()
        print(f"   Controls count: {len(controls)}")
        
        company = (await db.execute(select(Company).where(Company.scan_id == 28))).scalars().first()
        print(f"   Has company: {bool(company)}")
        
        cuecs = (await db.execute(select(CUEC).where(CUEC.scan_id == 28))).scalars().all()
        print(f"   CUECs count: {len(cuecs)}")
        
        # Check if backend can see it
        print(f"\n🔍 Testing backend query pattern...")
        result2 = await db.execute(select(Scan).where(Scan.id == 28))
        scan2 = result2.scalar_one_or_none()
        print(f"   Backend query result: {'FOUND' if scan2 else 'NOT FOUND'}")
        
        return

asyncio.run(check_scan_28())
