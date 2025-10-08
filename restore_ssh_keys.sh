#!/bin/bash

# SSH Keys Restore Script
# Run this on your NEW machine after copying the backup

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== SSH Keys Restore ===${NC}"
echo ""

# Check if backup directory is provided
if [ $# -eq 0 ]; then
    echo -e "${RED}Error: Please provide the path to your SSH backup directory${NC}"
    echo "Usage: $0 <path-to-ssh-backup-directory>"
    echo ""
    echo "Example:"
    echo "  $0 ~/Migration_Backup/latest/critical/ssh"
    exit 1
fi

BACKUP_DIR="$1"

if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}Error: Backup directory not found: $BACKUP_DIR${NC}"
    exit 1
fi

# Create .ssh directory if it doesn't exist
mkdir -p "$HOME/.ssh"

# Check if .ssh already has keys
if [ "$(ls -A $HOME/.ssh)" ]; then
    echo -e "${YELLOW}Warning: ~/.ssh directory is not empty${NC}"
    echo "Existing files:"
    ls -la "$HOME/.ssh"
    echo ""
    read -p "Do you want to continue and potentially overwrite files? (y/N): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo "Cancelled"
        exit 0
    fi
fi

# Copy SSH keys
echo "Restoring SSH keys from: $BACKUP_DIR"
cp -v "$BACKUP_DIR/"* "$HOME/.ssh/"

# Fix permissions
echo "Setting correct permissions..."
chmod 700 "$HOME/.ssh"
chmod 600 "$HOME/.ssh/"* 2>/dev/null || true
chmod 644 "$HOME/.ssh/"*.pub 2>/dev/null || true
chmod 644 "$HOME/.ssh/config" 2>/dev/null || true
chmod 644 "$HOME/.ssh/known_hosts" 2>/dev/null || true

echo ""
echo -e "${GREEN}✓ SSH keys restored successfully${NC}"
echo ""
echo "Your SSH keys:"
ls -la "$HOME/.ssh"
echo ""
echo "Test your SSH keys:"
echo "  ssh -T git@github.com"
echo "  ssh -T git@gitlab.com"
