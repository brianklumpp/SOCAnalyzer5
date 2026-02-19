import sys
sys.path.insert(0, '/app/backend')

from app.threading.scan_queue import get_scan_queue, ScanQueueStatus
import time

job_id = 'b20d5a5d-2f30-4f37-8ca1-05b497db3149'

queue = get_scan_queue()
scan = queue._load_scan(job_id)

if scan:
    print(f'Current queue status: {scan.status}')
    scan.status = ScanQueueStatus.COMPLETED
    scan.completed_at = time.strftime('%Y-%m-%dT%H:%M:%S')
    queue._save_scan(scan)
    queue.redis.delete(queue.KEY_CURRENT)
    queue.redis.hincrby(queue.KEY_STATS, "total_completed", 1)
    print('✓ Queue status updated to COMPLETED')
else:
    print('✗ Scan not in queue')
