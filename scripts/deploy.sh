#!/bin/bash

# Deployment script for GrowHaven

# Exit on error
set -e

echo "Starting deployment process..."

# Pull latest changes
echo "Pulling latest changes from repository..."
git pull

# Create and activate virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

# Install or update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Backup the database before migration
echo "Backing up database..."
./scripts/backup_db.sh

# Run database migrations
echo "Running database migrations..."
flask db upgrade

# Collect static files (if needed)
# echo "Collecting static files..."
# flask static-collect

# Restart the application
echo "Restarting application..."
if [ -f "/etc/systemd/system/growhaven.service" ]; then
    sudo systemctl restart growhaven
else
    echo "No systemd service found. Please restart the application manually."
fi

echo "Deployment completed successfully!"
