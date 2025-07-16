#!/bin/bash

# Define the name of the virtual environment directory
VENV_DIR="sof-discord-venv"
REQUIREMENTS_FILE="requirements.txt"

echo "Checking for Python 3..."
if ! command -v python3 &> /dev/null
then
    echo "Python 3 is not installed. Please install Python 3 to continue."
    exit 1
fi

echo "Creating virtual environment in '$VENV_DIR'..."
python3 -m venv "$VENV_DIR"

echo "Activating virtual environment..."
# Check if the activation script exists
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "Error: Could not find virtual environment activation script."
    exit 1
fi

echo "Installing dependencies from '$REQUIREMENTS_FILE'..."
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip install -r "$REQUIREMENTS_FILE"
    echo "Dependencies installed successfully."
else
    echo "Warning: '$REQUIREMENTS_FILE' not found. No dependencies installed."
fi

echo "Virtual environment '$VENV_DIR' is set up and dependencies are installed."
echo "To activate it in the future, run: source $VENV_DIR/bin/activate"
echo "To deactivate, run: deactivate"