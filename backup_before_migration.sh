#!/bin/bash

# Backup script for macOS machine migration
# Run this script BEFORE switching to your new machine
# This will create a backup in ~/Migration_Backup that you can upload to Google Drive

set -e

BACKUP_ROOT="$HOME/Migration_Backup"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/backup_${TIMESTAMP}"
BACKUP_LOG="$BACKUP_DIR/backup_log.txt"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$BACKUP_LOG"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$BACKUP_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$BACKUP_LOG"
}

backup_if_exists() {
    local source=$1
    local dest=$2
    local description=$3

    if [ -e "$source" ]; then
        log "Backing up $description..."
        mkdir -p "$(dirname "$dest")"
        cp -R "$source" "$dest"
        log "  ✓ Backed up: $source -> $dest"
    else
        log_warning "  ✗ Not found: $source"
    fi
}

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         macOS Migration Backup Script                     ║${NC}"
echo -e "${BLUE}║  This will backup your configs to ~/Migration_Backup      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"
log "Created backup directory: $BACKUP_DIR"

# Create a 'latest' symlink for easy access
ln -sfn "$BACKUP_DIR" "$BACKUP_ROOT/latest"
log "Created symlink: $BACKUP_ROOT/latest -> $BACKUP_DIR"

# ============================================================================
# CRITICAL FILES - These must be backed up
# ============================================================================

log "=== Backing up CRITICAL files ==="

# GPG Keys
log "Backing up GPG keys..."
if [ -d "$HOME/.gnupg" ]; then
    mkdir -p "$BACKUP_DIR/critical"
    tar czf "$BACKUP_DIR/critical/gnupg_backup.tar.gz" -C "$HOME" .gnupg
    log "  ✓ GPG keys backed up to: critical/gnupg_backup.tar.gz"
else
    log_warning "  ✗ No GPG directory found"
fi

# SSH Keys
log "Backing up SSH keys..."
if [ -d "$HOME/.ssh" ]; then
    mkdir -p "$BACKUP_DIR/critical/ssh"
    cp -R "$HOME/.ssh/"* "$BACKUP_DIR/critical/ssh/"
    chmod 700 "$BACKUP_DIR/critical/ssh"
    chmod 600 "$BACKUP_DIR/critical/ssh/"* 2>/dev/null || true
    log "  ✓ SSH keys backed up"
else
    log_warning "  ✗ No SSH directory found"
fi

# AWS Credentials
backup_if_exists "$HOME/.aws" "$BACKUP_DIR/aws" "AWS credentials and config"

# ============================================================================
# SHELL & TERMINAL CONFIGURATION
# ============================================================================

log "=== Backing up Shell & Terminal configs ==="

# Shell history files
backup_if_exists "$HOME/.zsh_history" "$BACKUP_DIR/shell/zsh_history" "Zsh history"
backup_if_exists "$HOME/.bash_history" "$BACKUP_DIR/shell/bash_history" "Bash history"

# Shell configuration files
log "Backing up all shell configuration files from home directory..."
mkdir -p "$BACKUP_DIR/shell/home_configs"

# Common shell config files
shell_configs=(
    ".zshrc"
    ".zshenv"
    ".zprofile"
    ".zlogin"
    ".zlogout"
    ".bashrc"
    ".bash_profile"
    ".bash_login"
    ".bash_logout"
    ".profile"
    ".shrc"
    ".kshrc"
    ".tcshrc"
    ".cshrc"
)

for config in "${shell_configs[@]}"; do
    if [ -f "$HOME/$config" ]; then
        cp "$HOME/$config" "$BACKUP_DIR/shell/home_configs/" 2>/dev/null || true
        log "  ✓ Backed up: $config"
    fi
done

# Backup any other shell-related files (*.sh, *.bash, *.zsh in home root)
find "$HOME" -maxdepth 1 -type f \( -name "*.sh" -o -name "*.bash" -o -name "*.zsh" \) 2>/dev/null | while read -r file; do
    filename=$(basename "$file")
    cp "$file" "$BACKUP_DIR/shell/home_configs/" 2>/dev/null || true
    log "  ✓ Backed up: $filename"
done

log_success "Shell configuration files backed up"

# iTerm2 settings (if using custom folder)
if [ -d "$HOME/Library/Application Support/iTerm2" ]; then
    backup_if_exists "$HOME/Library/Application Support/iTerm2/DynamicProfiles" \
                     "$BACKUP_DIR/iterm2/DynamicProfiles" "iTerm2 Dynamic Profiles"
fi

# ============================================================================
# GIT CONFIGURATION
# ============================================================================

log "=== Backing up Git configuration ==="

backup_if_exists "$HOME/.gitconfig" "$BACKUP_DIR/git/gitconfig" "Git config"
backup_if_exists "$HOME/.gitignore_global" "$BACKUP_DIR/git/gitignore_global" "Global gitignore"
backup_if_exists "$HOME/.git-credentials" "$BACKUP_DIR/git/git-credentials" "Git credentials"

# ============================================================================
# DEVELOPMENT TOOLS
# ============================================================================

log "=== Backing up Development tools ==="

# asdf tool versions
backup_if_exists "$HOME/.tool-versions" "$BACKUP_DIR/dev/tool-versions" "asdf tool versions"

# npm config
backup_if_exists "$HOME/.npmrc" "$BACKUP_DIR/dev/npmrc" "npm config"

# npm global packages
if command -v npm &> /dev/null; then
    log "Saving npm global packages list..."
    npm list -g --depth=0 > "$BACKUP_DIR/dev/npm-global-packages.txt" 2>/dev/null || true
fi

# pip packages
if command -v pip3 &> /dev/null; then
    log "Saving pip packages list..."
    pip3 list > "$BACKUP_DIR/dev/pip-packages.txt" 2>/dev/null || true
fi

# Homebrew packages - Generate complete Brewfile
if command -v brew &> /dev/null; then
    log "Generating Brewfile from installed packages..."
    mkdir -p "$BACKUP_DIR/homebrew"

    # Generate complete Brewfile
    brew bundle dump --file="$BACKUP_DIR/homebrew/Brewfile" --force
    log "  ✓ Brewfile generated with all installed packages"

    # Also save text lists for reference
    brew list > "$BACKUP_DIR/homebrew/brew-formulas.txt"
    brew list --cask > "$BACKUP_DIR/homebrew/brew-casks.txt"
    brew tap > "$BACKUP_DIR/homebrew/brew-taps.txt"

    log "  ✓ Homebrew package lists saved"
fi

# VSCode settings
if [ -d "$HOME/Library/Application Support/Code/User" ]; then
    log "Backing up VSCode settings..."
    mkdir -p "$BACKUP_DIR/vscode"
    cp "$HOME/Library/Application Support/Code/User/settings.json" "$BACKUP_DIR/vscode/" 2>/dev/null || true
    cp "$HOME/Library/Application Support/Code/User/keybindings.json" "$BACKUP_DIR/vscode/" 2>/dev/null || true
    cp "$HOME/Library/Application Support/Code/User/snippets/"* "$BACKUP_DIR/vscode/snippets/" 2>/dev/null || true

    # VSCode extensions
    if command -v code &> /dev/null; then
        code --list-extensions > "$BACKUP_DIR/vscode/extensions.txt"
        log "  ✓ VSCode extensions list saved"
    fi
fi

# IntelliJ IDEA settings (if using)
backup_if_exists "$HOME/.ideavimrc" "$BACKUP_DIR/intellij/ideavimrc" "IdeaVim config"

# Claude Code settings
if [ -d "$HOME/.claude" ]; then
    log "Backing up Claude Code settings..."
    mkdir -p "$BACKUP_DIR/claude"

    # Settings and chat history
    backup_if_exists "$HOME/.claude/settings.json" "$BACKUP_DIR/claude/settings.json" "Claude settings"
    backup_if_exists "$HOME/.claude/history.jsonl" "$BACKUP_DIR/claude/history.jsonl" "Claude chat history"

    # File history (optional but useful)
    if [ -d "$HOME/.claude/file-history" ]; then
        cp -R "$HOME/.claude/file-history" "$BACKUP_DIR/claude/file-history" 2>/dev/null || true
        log "  ✓ Claude file history backed up"
    fi

    # Shell snapshots (optional)
    if [ -d "$HOME/.claude/shell-snapshots" ]; then
        cp -R "$HOME/.claude/shell-snapshots" "$BACKUP_DIR/claude/shell-snapshots" 2>/dev/null || true
        log "  ✓ Claude shell snapshots backed up"
    fi

    log_success "Claude Code settings backed up (excluding projects)"
fi

# ============================================================================
# APPLICATION PREFERENCES
# ============================================================================

log "=== Backing up Application preferences ==="

mkdir -p "$BACKUP_DIR/app_preferences"

# Karabiner-Elements
backup_if_exists "$HOME/.config/karabiner" "$BACKUP_DIR/app_preferences/karabiner" "Karabiner-Elements config"

# Rectangle (window management)
backup_if_exists "$HOME/Library/Preferences/com.knollsoft.Rectangle.plist" \
                 "$BACKUP_DIR/app_preferences/Rectangle.plist" "Rectangle preferences"

# Magnet (window management)
backup_if_exists "$HOME/Library/Preferences/com.crowdcafe.windowmagnet.plist" \
                 "$BACKUP_DIR/app_preferences/Magnet.plist" "Magnet preferences"

# Spectacle (window management)
backup_if_exists "$HOME/Library/Preferences/com.divisiblebyzero.Spectacle.plist" \
                 "$BACKUP_DIR/app_preferences/Spectacle.plist" "Spectacle preferences"

# Alfred
backup_if_exists "$HOME/Library/Application Support/Alfred" \
                 "$BACKUP_DIR/app_preferences/Alfred" "Alfred preferences"

# Postman
backup_if_exists "$HOME/Library/Application Support/Postman" \
                 "$BACKUP_DIR/app_preferences/Postman" "Postman data"

# DBeaver
backup_if_exists "$HOME/Library/DBeaverData" \
                 "$BACKUP_DIR/app_preferences/DBeaverData" "DBeaver connections"

# macOS Shortcuts (if they exist locally, usually synced via iCloud)
if [ -d "$HOME/Library/Shortcuts" ]; then
    log "Backing up macOS Shortcuts..."
    cp -R "$HOME/Library/Shortcuts" "$BACKUP_DIR/app_preferences/Shortcuts" 2>/dev/null || true
    log_success "macOS Shortcuts backed up"
    log_warning "Note: Shortcuts are typically iCloud-synced. Sign into iCloud on new machine to restore."
fi

# ============================================================================
# macOS SYSTEM SETTINGS
# ============================================================================

log "=== Backing up macOS system settings ==="

mkdir -p "$BACKUP_DIR/macos_settings"

# Export system preferences
log "Exporting system preferences..."

# Dock preferences
defaults read com.apple.dock > "$BACKUP_DIR/macos_settings/dock.plist" 2>/dev/null || log_warning "Could not read Dock preferences"

# Finder preferences
defaults read com.apple.finder > "$BACKUP_DIR/macos_settings/finder.plist" 2>/dev/null || log_warning "Could not read Finder preferences"

# Keyboard preferences
defaults read .GlobalPreferences > "$BACKUP_DIR/macos_settings/global.plist" 2>/dev/null || log_warning "Could not read global preferences"

# Trackpad preferences
defaults read com.apple.AppleMultitouchTrackpad > "$BACKUP_DIR/macos_settings/trackpad.plist" 2>/dev/null || log_warning "Could not read Trackpad preferences"

# Screenshots location
defaults read com.apple.screencapture > "$BACKUP_DIR/macos_settings/screencapture.plist" 2>/dev/null || log_warning "Could not read screenshot preferences"

# Save a script with all defaults
log "Creating restore script for macOS settings..."
cat > "$BACKUP_DIR/macos_settings/current_defaults.sh" << 'EOF'
#!/bin/bash
# This file contains a snapshot of your current macOS defaults
# Review and run selectively on your new machine

echo "This script contains your macOS defaults. Review before running!"
echo "You may want to run individual commands rather than the entire script."

# Note: These are snapshots, review before applying
EOF

# Append some common settings that are safe to restore
defaults read com.apple.dock | grep -E "autohide|orientation|tilesize" >> "$BACKUP_DIR/macos_settings/current_defaults.sh" 2>/dev/null || true

# ============================================================================
# KUBERNETES & CLOUD CONFIGS
# ============================================================================

log "=== Backing up Kubernetes & Cloud configs ==="

backup_if_exists "$HOME/.kube" "$BACKUP_DIR/kube" "Kubernetes config"
backup_if_exists "$HOME/.docker" "$BACKUP_DIR/docker" "Docker config"

# ============================================================================
# MISC CONFIGS
# ============================================================================

log "=== Backing up miscellaneous configs ==="

backup_if_exists "$HOME/.vimrc" "$BACKUP_DIR/misc/vimrc" "Vimrc (if not in dotfiles)"
backup_if_exists "$HOME/.vim" "$BACKUP_DIR/misc/vim" "Vim plugins"
backup_if_exists "$HOME/.tmux.conf" "$BACKUP_DIR/misc/tmux.conf" "Tmux config (if not in dotfiles)"
backup_if_exists "$HOME/.secrets.sh" "$BACKUP_DIR/misc/secrets.sh" "Secrets file"

# ============================================================================
# CREATE INVENTORY
# ============================================================================

log "=== Creating backup inventory ==="

cat > "$BACKUP_DIR/INVENTORY.md" << EOF
# Backup Inventory
Generated: $(date)

## Directory Structure
\`\`\`
$(tree -L 2 "$BACKUP_DIR" 2>/dev/null || find "$BACKUP_DIR" -maxdepth 2 -type d)
\`\`\`

## Backup Contents

### Critical Files
- GPG Keys: $([ -f "$BACKUP_DIR/critical/gnupg_backup.tar.gz" ] && echo "✓" || echo "✗")
- SSH Keys: $([ -d "$BACKUP_DIR/critical/ssh" ] && echo "✓" || echo "✗")
- AWS Config: $([ -d "$BACKUP_DIR/aws" ] && echo "✓" || echo "✗")

### Development
- Git Config: $([ -d "$BACKUP_DIR/git" ] && echo "✓" || echo "✗")
- VSCode Settings: $([ -d "$BACKUP_DIR/vscode" ] && echo "✓" || echo "✗")
- Claude Code: $([ -d "$BACKUP_DIR/claude" ] && echo "✓" || echo "✗")
- NPM Global Packages: $([ -f "$BACKUP_DIR/dev/npm-global-packages.txt" ] && echo "✓" || echo "✗")
- Homebrew Brewfile: $([ -f "$BACKUP_DIR/homebrew/Brewfile" ] && echo "✓" || echo "✗")
- Homebrew Packages: $([ -f "$BACKUP_DIR/homebrew/brew-formulas.txt" ] && echo "✓" || echo "✗")

### Application Preferences
- Karabiner: $([ -d "$BACKUP_DIR/app_preferences/karabiner" ] && echo "✓" || echo "✗")
- DBeaver: $([ -d "$BACKUP_DIR/app_preferences/DBeaverData" ] && echo "✓" || echo "✗")

### System Settings
- macOS Preferences: $([ -d "$BACKUP_DIR/macos_settings" ] && echo "✓" || echo "✗")

## Next Steps

1. **Upload to Google Drive**
   \`\`\`bash
   # Open Finder and drag ~/Migration_Backup to Google Drive
   # Or wait for Google Drive to sync
   \`\`\`

2. **Verify backup**
   - Check that all critical files are present
   - Verify GPG backup: tar -tzf critical/gnupg_backup.tar.gz
   - Check SSH keys: ls -la critical/ssh/
   - Review Brewfile: cat homebrew/Brewfile

3. **On new machine**
   - Clone dotfiles repo
   - Run install_mac.sh
   - Run restore_backups.sh with the path to this backup

## Important Reminders for Corporate Machines

⚠️ If your company uses MDM, let it configure the machine first
⚠️ Follow your company's IT policies for machine setup
✓ Use cloud storage (Google Drive, Dropbox, etc.) for file sync
✓ Review your company's backup/restore policies before using Time Machine

EOF

# ============================================================================
# PROJECTS FOLDER (OPTIONAL)
# ============================================================================

log_step "Checking projects folder..."

if [ -d "$HOME/projects" ]; then
    PROJECT_SIZE=$(du -sh "$HOME/projects" 2>/dev/null | cut -f1)
    log "Found ~/projects directory (size: $PROJECT_SIZE)"

    echo ""
    echo -e "${YELLOW}Do you want to backup ~/projects folder?${NC}"
    echo "This may take a while depending on size."
    echo "Note: node_modules and common build artifacts will be excluded."
    echo ""
    read -p "Backup ~/projects? (y/N): " backup_projects

    if [[ $backup_projects =~ ^[Yy]$ ]]; then
        log "Backing up ~/projects (excluding build artifacts)..."
        mkdir -p "$BACKUP_DIR/projects"

        # Use rsync to exclude common build artifacts
        rsync -a \
            --exclude='node_modules' \
            --exclude='target' \
            --exclude='build' \
            --exclude='dist' \
            --exclude='.next' \
            --exclude='.nuxt' \
            --exclude='vendor' \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='.gradle' \
            --exclude='.terraform' \
            --exclude='venv' \
            --exclude='.venv' \
            --exclude='env' \
            "$HOME/projects/" "$BACKUP_DIR/projects/" 2>&1 | tee -a "$BACKUP_LOG" || log_warning "Some files may have failed to copy"

        BACKUP_SIZE=$(du -sh "$BACKUP_DIR/projects" 2>/dev/null | cut -f1)
        log_success "Projects backed up (size: $BACKUP_SIZE)"
        log_warning "Remember: dependencies (node_modules, etc.) were excluded"
        log_warning "Run 'npm install', 'go mod download', etc. on new machine"
    else
        log "Skipping ~/projects backup"
        log_warning "Make sure your projects are pushed to git!"
    fi
else
    log_warning "~/projects directory not found"
fi

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    BACKUP COMPLETE                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
log "Backup completed successfully!"
log "Backup location: $BACKUP_DIR"
log "Quick access: $BACKUP_ROOT/latest"
log "Backup size: $(du -sh "$BACKUP_DIR" | cut -f1)"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo "1. Review the backup: cd $BACKUP_ROOT/latest"
echo "2. Check INVENTORY.md for what was backed up"
echo "3. Upload $BACKUP_ROOT to cloud storage (Google Drive, Dropbox, etc.)"
echo "4. Verify the upload completed successfully"
echo "5. Keep this backup until you've verified your new machine works"
echo ""
echo -e "${YELLOW}Quick access to your backup:${NC}"
echo "  cd $BACKUP_ROOT/latest"
echo ""
echo -e "${YELLOW}Log file saved to: $BACKUP_LOG${NC}"
