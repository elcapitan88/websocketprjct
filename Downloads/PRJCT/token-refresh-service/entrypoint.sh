#!/bin/bash
set -e

# Print environment info
echo "Starting Token Refresh Service in $ENVIRONMENT environment"
echo "Python version: $(python --version)"
echo "Current directory: $(pwd)"

# Optional: Run database migrations if needed
# if [ "$RUN_MIGRATIONS" = "true" ]; then
#     echo "Running database migrations..."
#     alembic upgrade head
# fi

# Start the service
echo "Starting service..."
python -m app.main