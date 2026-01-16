#!/bin/sh
set -e

# Force DNS configuration to use our DNS cache FIRST, then Docker's internal DNS
# Docker's embedded DNS (127.0.0.11) is needed for service discovery (postgres, redis, etc)
# but we want our DNS cache (172.20.0.2) to handle external DNS queries first

echo "Configuring DNS to use local cache at 172.20.0.2..."

# Backup original resolv.conf
cp /etc/resolv.conf /etc/resolv.conf.bak || true

# Create new resolv.conf with our DNS cache FIRST, then Docker's internal DNS
cat > /etc/resolv.conf << EOF
# SOCAnalyzer DNS Configuration
# Our DNS cache first for external DNS (dataiku-dss.corp.nandps.com, etc)
nameserver 172.20.0.2
# Docker's internal DNS for service discovery (postgres, redis, etc)
nameserver 127.0.0.11
# Public DNS as last resort fallback
nameserver 8.8.8.8
nameserver 8.8.4.4
options ndots:0
EOF

echo "DNS configuration updated:"
cat /etc/resolv.conf

# Test DNS resolution for both internal and external services
echo "Testing DNS resolution..."
echo "- Testing external: dataiku-dss.corp.nandps.com"
if nslookup dataiku-dss.corp.nandps.com 172.20.0.2 > /dev/null 2>&1; then
    echo "  ✓ External DNS resolution successful"
else
    echo "  ⚠ External DNS resolution failed, but continuing..."
fi

echo "- Testing internal: postgres"
if nslookup postgres 127.0.0.11 > /dev/null 2>&1; then
    echo "  ✓ Internal DNS resolution successful"
else
    echo "  ⚠ Internal DNS resolution failed, but continuing..."
fi

# Wait for postgres to be ready
if [ ! -z "$DATABASE_URL_SYNC" ]; then
    echo "Waiting for database to be ready..."
    RETRIES=30
    until nc -z postgres 5432 2>/dev/null || [ $RETRIES -eq 0 ]; do
        echo "  Waiting for postgres... ($RETRIES retries left)"
        RETRIES=$((RETRIES - 1))
        sleep 1
    done
    
    if [ $RETRIES -eq 0 ]; then
        echo "  ⚠ Database not ready after 30 seconds, starting anyway..."
    else
        echo "  ✓ Database is ready"
        
        # Run database migrations
        echo "Running database migrations..."
        cd /app
        alembic -c backend/alembic.ini upgrade head
        MIGRATION_EXIT_CODE=$?
        
        if [ $MIGRATION_EXIT_CODE -eq 0 ]; then
            echo "  ✓ Database migrations completed successfully"
            
            # Check if users table is empty and create default admin if needed
            if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
                echo "Checking for existing users..."
                python3 -c "
import asyncio
from sqlalchemy import select, func
from backend.app.database import AsyncSessionLocal
from backend.app.models import User

async def check_users():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(func.count(User.id)))
        count = result.scalar()
        return count

count = asyncio.run(check_users())
exit(0 if count == 0 else 1)
" 2>/dev/null
                
                if [ $? -eq 0 ]; then
                    echo "  No users found, creating default admin user..."
                    python3 -m backend.scripts.create_admin
                    if [ $? -eq 0 ]; then
                        echo "  ✓ Default admin user created"
                    else
                        echo "  ⚠ Failed to create default admin user (will need to create manually)"
                    fi
                else
                    echo "  ✓ Users exist, skipping admin creation"
                fi
            fi
        else
            echo ""
            echo "========================================" 
            echo "  ✗ DATABASE MIGRATION FAILED"
            echo "========================================" 
            echo "Exit code: $MIGRATION_EXIT_CODE"
            echo ""
            echo "Cannot start application with incompatible database schema."
            echo "Check the migration errors above."
            echo ""
            echo "To fix manually:"
            echo "  docker compose exec backend sh -c 'cd /app/backend && alembic upgrade head'"
            echo ""
            exit 1
        fi
    fi
fi

# Execute the main command (passed as arguments to this script)
echo "Starting application..."
exec "$@"
