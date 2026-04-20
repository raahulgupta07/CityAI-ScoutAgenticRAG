#!/bin/bash
set -e

echo "=== Document Intelligence Agent ==="

# Wait for database using Python (no pg_isready needed)
if [ "$WAIT_FOR_DB" = "true" ] || [ "$WAIT_FOR_DB" = "True" ]; then
    echo "Waiting for database..."
    python3 -c "
import time, os
db_url = os.environ.get('DATABASE_URL', '')
host = db_url.split('@')[1].split(':')[0] if '@' in db_url else 'db'
port = int(db_url.split(':')[-1].split('/')[0]) if db_url else 5432
import socket
for i in range(30):
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        print(f'Database ready at {host}:{port}')
        break
    except:
        time.sleep(1)
else:
    print('WARNING: Database not ready after 30s, starting anyway')
"
fi

# Start application
echo "Starting API server on port 8000..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
