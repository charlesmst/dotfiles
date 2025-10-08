#!/bin/bash

# Restore Script for Migration Backup
# Run this on your NEW machine after running install_mac.sh
# This restores application settings and other data

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"
}

log_step() {
    echo -e "${BLUE}==>${NC} ${YELLOW}$1${NC}"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

restore_if_exists() {
    local source=$1
    local dest=$2
    local description=$3

    if [ -e "$source" ]; then
        log "Restoring $description..."
        mkdir -p "$(dirname "$dest")"
        cp -R "$source" "$dest"
        log_success "  ✓ Restored: $source -> $dest"
        return 0
    else
        log_warning "  ✗ Not found: $source (skipping)"
        return 1
    fi
}

echo -e "${BLUE}"
cat << "EOF"
╔══════════════════════════════════════════════════════════════╗
║                 Backup Restoration Script                    ║
╚══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if backup directory is provided
if [ $# -eq 0 ]; then
    echo -e "${RED}Error: Please provide the path to your backup directory${NC}"
    echo "Usage: $0 <path-to-backup-directory>"
    echo ""
    echo "Example:"
    echo "  $0 ~/Migration_Backup/latest"
    exit 1
fi

BACKUP_DIR="$1"

if [ ! -d "$BACKUP_DIR" ]; then
    log_error "Backup directory not found: $BACKUP_DIR"
    exit 1
fi

log "Restoring from: $BACKUP_DIR"
echo ""

# ============================================================================
# IMPORTANT NOTICE
# ============================================================================

echo -e "${YELLOW}"
cat << "EOF"
⚠️  IMPORTANT:

This script will restore various configurations and data.
Some items should be restored manually (GPG and SSH keys).

What will be restored:
  - AWS credentials
  - Shell history
  - Git configuration
  - VSCode settings
  - Application preferences
  - Kubernetes configs
  - Docker configs

What should be restored separately:
  - GPG keys: Run ./restore_gpg_keys.sh
  - SSH keys: Run ./restore_ssh_keys.sh

EOF
echo -e "${NC}"

read -p "Continue with restoration? (y/N): " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 0
fi

echo ""

# ============================================================================
# AWS CREDENTIALS
# ============================================================================

log_step "Restoring AWS credentials..."

if restore_if_exists "$BACKUP_DIR/aws" "$HOME/.aws" "AWS credentials"; then
    chmod 600 "$HOME/.aws/credentials" 2>/dev/null || true
    chmod 600 "$HOME/.aws/config" 2>/dev/null || true
fi

# ============================================================================
# SHELL HISTORY
# ============================================================================

log_step "Restoring shell history and configs..."

# Restore history files
restore_if_exists "$BACKUP_DIR/shell/zsh_history" "$HOME/.zsh_history" "Zsh history"
restore_if_exists "$BACKUP_DIR/shell/bash_history" "$HOME/.bash_history" "Bash history"

# Set correct permissions for history
chmod 600 "$HOME/.zsh_history" 2>/dev/null || true
chmod 600 "$HOME/.bash_history" 2>/dev/null || true

# Restore shell config files from home directory
if [ -d "$BACKUP_DIR/shell/home_configs" ]; then
    log "Restoring shell configuration files..."

    echo ""
    echo -e "${YELLOW}Found shell config files from your home directory.${NC}"
    echo "These may conflict with your dotfiles repo configs."
    echo ""
    read -p "Restore shell configs from home directory? (y/N): " restore_shell_configs

    if [[ $restore_shell_configs =~ ^[Yy]$ ]]; then
        for file in "$BACKUP_DIR/shell/home_configs/"*; do
            if [ -f "$file" ]; then
                filename=$(basename "$file")

                # Warn if file already exists
                if [ -f "$HOME/$filename" ]; then
                    log_warning "$filename already exists, backing up to ${filename}.bak"
                    cp "$HOME/$filename" "$HOME/${filename}.bak" 2>/dev/null || true
                fi

                cp "$file" "$HOME/" 2>/dev/null || true
                log_success "Restored: $filename"
            fi
        done
    else
        log "Skipping shell config restoration"
        log "Files available in: $BACKUP_DIR/shell/home_configs/"
    fi
fi

# ============================================================================
# GIT CONFIGURATION
# ============================================================================

log_step "Restoring Git configuration..."

# Only restore if not already configured
if [ ! -f "$HOME/.gitconfig" ]; then
    restore_if_exists "$BACKUP_DIR/git/gitconfig" "$HOME/.gitconfig" "Git config"
else
    log_warning "Git config already exists, skipping (backup available at $BACKUP_DIR/git/gitconfig)"
fi

restore_if_exists "$BACKUP_DIR/git/gitignore_global" "$HOME/.gitignore_global" "Global gitignore"
restore_if_exists "$BACKUP_DIR/git/git-credentials" "$HOME/.git-credentials" "Git credentials"

if [ -f "$HOME/.git-credentials" ]; then
    chmod 600 "$HOME/.git-credentials"
fi

# ============================================================================
# DEVELOPMENT TOOLS
# ============================================================================

log_step "Restoring development tool configurations..."

restore_if_exists "$BACKUP_DIR/dev/tool-versions" "$HOME/.tool-versions" "asdf tool versions"

# npm config
restore_if_exists "$BACKUP_DIR/dev/npmrc" "$HOME/.npmrc" "npm config"

# Show npm global packages for manual installation
if [ -f "$BACKUP_DIR/dev/npm-global-packages.txt" ]; then
    log_success "Found npm global packages list"
    log "To reinstall npm global packages, review: $BACKUP_DIR/dev/npm-global-packages.txt"
fi

# ============================================================================
# VSCODE SETTINGS
# ============================================================================

log_step "Restoring VSCode settings..."

if [ -d "$BACKUP_DIR/vscode" ]; then
    mkdir -p "$HOME/Library/Application Support/Code/User"

    restore_if_exists "$BACKUP_DIR/vscode/settings.json" \
                     "$HOME/Library/Application Support/Code/User/settings.json" \
                     "VSCode settings"

    restore_if_exists "$BACKUP_DIR/vscode/keybindings.json" \
                     "$HOME/Library/Application Support/Code/User/keybindings.json" \
                     "VSCode keybindings"

    if [ -d "$BACKUP_DIR/vscode/snippets" ]; then
        mkdir -p "$HOME/Library/Application Support/Code/User/snippets"
        cp -R "$BACKUP_DIR/vscode/snippets/"* "$HOME/Library/Application Support/Code/User/snippets/" 2>/dev/null || true
        log_success "VSCode snippets restored"
    fi

    # Show VSCode extensions for manual installation
    if [ -f "$BACKUP_DIR/vscode/extensions.txt" ]; then
        log_success "Found VSCode extensions list"
        log "To reinstall extensions, run:"
        echo "  cat $BACKUP_DIR/vscode/extensions.txt | xargs -L 1 code --install-extension"
    fi
fi

# ============================================================================
# CLAUDE CODE
# ============================================================================

log_step "Restoring Claude Code settings..."

if [ -d "$BACKUP_DIR/claude" ]; then
    mkdir -p "$HOME/.claude"

    restore_if_exists "$BACKUP_DIR/claude/settings.json" \
                     "$HOME/.claude/settings.json" \
                     "Claude settings"

    restore_if_exists "$BACKUP_DIR/claude/history.jsonl" \
                     "$HOME/.claude/history.jsonl" \
                     "Claude chat history"

    if [ -d "$BACKUP_DIR/claude/file-history" ]; then
        cp -R "$BACKUP_DIR/claude/file-history" "$HOME/.claude/" 2>/dev/null || true
        log_success "Claude file history restored"
    fi

    if [ -d "$BACKUP_DIR/claude/shell-snapshots" ]; then
        cp -R "$BACKUP_DIR/claude/shell-snapshots" "$HOME/.claude/" 2>/dev/null || true
        log_success "Claude shell snapshots restored"
    fi
else
    log_warning "No Claude Code backup found"
fi

# ============================================================================
# APPLICATION PREFERENCES
# ============================================================================

log_step "Restoring application preferences..."

# Karabiner (should already be linked by dotfiles, but restore if needed)
if [ -d "$BACKUP_DIR/app_preferences/karabiner" ] && [ ! -d "$HOME/.config/karabiner" ]; then
    restore_if_exists "$BACKUP_DIR/app_preferences/karabiner" \
                     "$HOME/.config/karabiner" \
                     "Karabiner config"
fi

# Rectangle
restore_if_exists "$BACKUP_DIR/app_preferences/Rectangle.plist" \
                 "$HOME/Library/Preferences/com.knollsoft.Rectangle.plist" \
                 "Rectangle preferences"

# Magnet
restore_if_exists "$BACKUP_DIR/app_preferences/Magnet.plist" \
                 "$HOME/Library/Preferences/com.crowdcafe.windowmagnet.plist" \
                 "Magnet preferences"

# DBeaver
if [ -d "$BACKUP_DIR/app_preferences/DBeaverData" ]; then
    log "DBeaver data found. Restoring..."
    restore_if_exists "$BACKUP_DIR/app_preferences/DBeaverData" \
                     "$HOME/Library/DBeaverData" \
                     "DBeaver connections and data"
fi

# Alfred
if [ -d "$BACKUP_DIR/app_preferences/Alfred" ]; then
    log "Alfred preferences found. Note: You may need to configure sync manually in Alfred preferences."
    restore_if_exists "$BACKUP_DIR/app_preferences/Alfred" \
                     "$HOME/Library/Application Support/Alfred" \
                     "Alfred preferences"
fi

# Postman
if [ -d "$BACKUP_DIR/app_preferences/Postman" ]; then
    log "Postman data found. Restoring..."
    restore_if_exists "$BACKUP_DIR/app_preferences/Postman" \
                     "$HOME/Library/Application Support/Postman" \
                     "Postman data"
fi

# ============================================================================
# KUBERNETES & DOCKER
# ============================================================================

log_step "Restoring Kubernetes and Docker configs..."

if [ -d "$BACKUP_DIR/kube" ]; then
    log_warning "Kubernetes config found. Review before restoring (may contain old clusters)"
    read -p "Restore Kubernetes config? (y/N): " restore_kube
    if [[ $restore_kube =~ ^[Yy]$ ]]; then
        restore_if_exists "$BACKUP_DIR/kube" "$HOME/.kube" "Kubernetes config"
        chmod 600 "$HOME/.kube/config" 2>/dev/null || true
    fi
fi

restore_if_exists "$BACKUP_DIR/docker" "$HOME/.docker" "Docker config"

# ============================================================================
# MISC CONFIGS
# ============================================================================

log_step "Restoring miscellaneous configs..."

restore_if_exists "$BACKUP_DIR/misc/secrets.sh" "$HOME/.secrets.sh" "Secrets file"

if [ -f "$HOME/.secrets.sh" ]; then
    chmod 600 "$HOME/.secrets.sh"
fi

# ============================================================================
# PROJECTS FOLDER
# ============================================================================

log_step "Checking for projects backup..."

if [ -d "$BACKUP_DIR/projects" ]; then
    PROJECT_BACKUP_SIZE=$(du -sh "$BACKUP_DIR/projects" 2>/dev/null | cut -f1)
    log "Found projects backup (size: $PROJECT_BACKUP_SIZE)"

    echo ""
    echo -e "${YELLOW}Restore ~/projects folder?${NC}"
    echo "This will copy your projects source code (dependencies excluded)."
    echo ""
    read -p "Restore ~/projects? (y/N): " restore_projects

    if [[ $restore_projects =~ ^[Yy]$ ]]; then
        log "Restoring ~/projects..."
        mkdir -p "$HOME/projects"

        rsync -a "$BACKUP_DIR/projects/" "$HOME/projects/" 2>&1 | tee -a "$BACKUP_LOG" || log_warning "Some files may have failed to restore"

        log_success "Projects restored to ~/projects"
        log_warning "Remember to reinstall dependencies:"
        log "  - Node.js: npm install or yarn install"
        log "  - Go: go mod download"
        log "  - Python: pip install -r requirements.txt"
        log "  - Rust: cargo build"
    else
        log "Skipping ~/projects restoration"
    fi
else
    log_warning "No projects backup found"
fi

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                 RESTORATION COMPLETE                         ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

log_success "Restoration completed!"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo ""
echo "1. ${YELLOW}Restore GPG keys:${NC}"
echo "   ./restore_gpg_keys.sh $BACKUP_DIR/critical/gnupg_backup.tar.gz"
echo ""
echo "2. ${YELLOW}Restore SSH keys:${NC}"
echo "   ./restore_ssh_keys.sh $BACKUP_DIR/critical/ssh"
echo ""
echo "3. ${YELLOW}Verify critical configs:${NC}"
echo "   - Check AWS credentials: aws sts get-caller-identity"
echo "   - Check Git config: git config --list"
echo ""
echo "4. ${YELLOW}Install VSCode extensions (if needed):${NC}"
if [ -f "$BACKUP_DIR/vscode/extensions.txt" ]; then
    echo "   cat $BACKUP_DIR/vscode/extensions.txt | xargs -L 1 code --install-extension"
fi
echo ""
echo "5. ${YELLOW}Restart applications${NC} to pick up restored preferences"
echo ""
echo "6. ${YELLOW}Review macOS system preferences:${NC}"
echo "   - System preferences may need manual configuration"
echo "   - Check: $BACKUP_DIR/macos_settings/"
echo ""
