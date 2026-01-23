#!/bin/sh
set -e

# If node_modules doesn't exist or is empty, run npm ci
if [ ! -d "node_modules" ] || [ -z "$(ls -A node_modules 2>/dev/null)" ]; then
    echo "Installing dependencies..."
    npm ci --legacy-peer-deps
fi

# Execute the main command
exec "$@"
