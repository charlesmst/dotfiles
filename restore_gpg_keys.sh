#!/bin/bash

# GPG Keys Restore Script
# Run this on your NEW machine after copying the backup

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== GPG Keys Restore ===${NC}"
echo ""

# Check if backup file is provided
if [ $# -eq 0 ]; then
    echo -e "${RED}Error: Please provide the path to your GPG backup file${NC}"
    echo "Usage: $0 <path-to-gnupg_backup.tar.gz>"
    echo ""
    echo "Example:"
    echo "  $0 ~/Migration_Backup/latest/critical/gnupg_backup.tar.gz"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}Error: Backup file not found: $BACKUP_FILE${NC}"
    exit 1
fi

# Check if GPG directory already exists
if [ -d "$HOME/.gnupg" ]; then
    echo -e "${YELLOW}Warning: ~/.gnupg directory already exists${NC}"
    echo "Do you want to:"
    echo "  1) Backup current and restore from backup"
    echo "  2) Merge with existing (may cause conflicts)"
    echo "  3) Cancel"
    read -p "Enter choice (1-3): " choice

    case $choice in
        1)
            BACKUP_EXISTING="$HOME/.gnupg.backup.$(date +%Y%m%d_%H%M%S)"
            echo "Backing up existing GPG directory to: $BACKUP_EXISTING"
            mv "$HOME/.gnupg" "$BACKUP_EXISTING"
            ;;
        2)
            echo "Merging with existing GPG directory..."
            ;;
        3)
            echo "Cancelled"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice${NC}"
            exit 1
            ;;
    esac
fi

# Restore GPG keys
echo "Restoring GPG keys from: $BACKUP_FILE"
tar xzf "$BACKUP_FILE" -C "$HOME"

# Fix permissions
echo "Setting correct permissions..."
chmod 700 "$HOME/.gnupg"
chmod 600 "$HOME/.gnupg/"* 2>/dev/null || true
chmod 700 "$HOME/.gnupg/private-keys-v1.d" 2>/dev/null || true

echo ""
echo -e "${GREEN}✓ GPG keys restored successfully${NC}"
echo ""
echo "Verify your keys:"
echo "  gpg --list-secret-keys"
echo ""
echo "Test signing:"
echo "  echo 'test' | gpg --clearsign"
