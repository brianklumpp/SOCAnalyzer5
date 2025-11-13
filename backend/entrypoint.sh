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

# Execute the main command (passed as arguments to this script)
echo "Starting application..."
exec "$@"
