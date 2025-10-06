#!/bin/bash

# Setup script for Python virtual environment
echo "Setting up Python virtual environment..."

# Navigate to the generation directory
cd public/data/generation

# Create virtual environment if it doesn't exist
if [ ! -d "myenv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv myenv
fi

# Activate virtual environment
source myenv/bin/activate

# Install Python dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "No requirements.txt found, installing basic dependencies..."
    pip install --upgrade pip
    pip install requests beautifulsoup4 selenium openai pillow
fi

echo "Python environment setup complete!"
