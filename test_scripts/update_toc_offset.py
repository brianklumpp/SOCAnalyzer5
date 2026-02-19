"""Update toc_page_offset to 0 for scan 3"""
import sys
import os
sys.path.insert(0, 'backend')

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import psycopg2

def update_offset():
    # Get DB URL from environment
    db_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://soc2user:Pass@localhost:5432/soc2analyzer')
    # Convert to psycopg2 format (remove +asyncpg)
    db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Check current value
        cur.execute("SELECT id, pdf_filename, toc_page_offset FROM scan WHERE id = 3")
        row = cur.fetchone()
        if row:
            print(f"Before: id={row[0]}, pdf={row[1]}, toc_page_offset={row[2]}")
        
        # Update toc_page_offset
        cur.execute("UPDATE scan SET toc_page_offset = 0 WHERE id = 3")
        conn.commit()
        
        # Verify
        cur.execute("SELECT id, pdf_filename, toc_page_offset FROM scan WHERE id = 3")
        row = cur.fetchone()
        if row:
            print(f"After: id={row[0]}, pdf={row[1]}, toc_page_offset={row[2]}")
            print("✅ Successfully updated toc_page_offset to 0")
        else:
            print("❌ Scan 3 not found")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    update_offset()
