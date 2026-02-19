import psycopg2

# Connect to database
conn = psycopg2.connect(
    host="postgres",
    database="soc2analyzer",
    user="soc2_analyzer",
    password="puntitforthewin"
)
cur = conn.cursor()

# Check current status
cur.execute("SELECT id, progress_status, elapsed_seconds FROM scan WHERE id = 2")
row = cur.fetchone()

if row:
    print(f'Current Status: {row[1]}')
    print(f'Elapsed: {row[2]}s')
    
    # Update to completed
    cur.execute("""
        UPDATE scan 
        SET progress_status = 'Scan Complete - All Phases Finished',
            elapsed_seconds = 1314
        WHERE id = 2
    """)
    
    conn.commit()
    print("✓ Scan status updated in database")
else:
    print("✗ Scan not found")

cur.close()
conn.close()
