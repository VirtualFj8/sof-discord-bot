#!/bin/bash

set -euo pipefail

# Define the name of the virtual environment directory
VENV_DIR="sof-discord-venv"
REQUIREMENTS_FILE="requirements.txt"

# Detect if this script is being sourced
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  SOURCED=1
else
  SOURCED=0
fi

die() {
  echo "$1" >&2
  if [[ $SOURCED -eq 1 ]]; then
    return 1
  else
    exit 1
  fi
}

echo "Checking for Python 3..."
if ! command -v python3 >/dev/null 2>&1; then
  die "Python 3 is not installed. Please install Python 3 to continue."
fi

echo "Creating virtual environment in '$VENV_DIR'..."
python3 -m venv "$VENV_DIR"

ACTIVATE_PATH="$VENV_DIR/bin/activate"
PIP_PATH="$VENV_DIR/bin/pip"

if [[ ! -f "$ACTIVATE_PATH" ]]; then
  die "Error: Could not find virtual environment activation script at $ACTIVATE_PATH."
fi

echo "Installing dependencies from '$REQUIREMENTS_FILE'..."
if [[ -f "$REQUIREMENTS_FILE" ]]; then
  # Install using the venv's pip, regardless of activation
  "$PIP_PATH" install -r "$REQUIREMENTS_FILE"
  echo "Dependencies installed successfully."
else
  echo "Warning: '$REQUIREMENTS_FILE' not found. No dependencies installed."
fi

if [[ $SOURCED -eq 1 ]]; then
  echo "Activating virtual environment in current shell..."
  # shellcheck disable=SC1090
  source "$ACTIVATE_PATH"
  echo "Virtual environment '$VENV_DIR' is now active."
  echo "To deactivate later, run: deactivate"
else
  echo
  echo "Virtual environment '$VENV_DIR' is set up and dependencies are installed."
  echo "To activate it in your current shell, run:"
  echo "  source $ACTIVATE_PATH"
  echo
  echo "Tip: run 'source setup_env.sh' to both set up and activate in the same shell."
fi