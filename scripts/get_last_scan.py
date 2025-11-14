import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL_SYNC')
if not DATABASE_URL:
    print('No DATABASE_URL_SYNC set')
    raise SystemExit(1)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT id, scan_date, product FROM scan ORDER BY id DESC LIMIT 1")
row = cur.fetchone()
if row:
    print('LAST_SCAN_ID:', row[0])
    print('SCAN_DATE:', row[1])
    print('PRODUCT:', row[2])
else:
    print('No rows in scan table')
cur.close()
conn.close()
