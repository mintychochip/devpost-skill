#!/usr/bin/env bash
set -e

echo "Installing Devpost CLI..."

# Clone repo
REPO="https://github.com/mintychochip/devpost-skill.git"
TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR"
git clone "$REPO" devpost-cli
cd devpost-cli

# Install package
pip install -e .

# Install playwright browser
playwright install chromium

# Create symlink (optional)
if command -v devpost &> /dev/null; then
    echo "✓ Devpost CLI installed successfully!"
    echo "  Run: devpost --help"
else
    echo "✓ Devpost CLI installed!"
    echo "  Add to PATH or run: python -m devpost_cli --help"
fi

# Cleanup
cd - > /dev/null
rm -rf "$TEMP_DIR"
