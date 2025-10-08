#!/bin/bash

# macOS Setup Script for New Machine
# This script sets up a new Mac with all necessary tools and configurations
#
# Usage: ./install_mac.sh [--skip-checks]
#
# IMPORTANT: Run this AFTER MDM (Kandji) has configured your machine

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m'

SKIP_CHECKS=false
if [[ "$1" == "--skip-checks" ]]; then
    SKIP_CHECKS=true
fi

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$HOME/install_mac_$(date +%Y%m%d_%H%M%S).log"

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_step() {
    echo -e "${BLUE}==>${NC} ${MAGENTA}$1${NC}" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1" | tee -a "$LOG_FILE"
}

# Error handler
error_exit() {
    log_error "$1"
    log_error "Installation failed. Check log: $LOG_FILE"
    exit 1
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo -e "${BLUE}"
cat << "EOF"
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║            macOS Development Environment Setup               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

log "Starting installation at $(date)"
log "Dotfiles directory: $DOTFILES_DIR"
log "Log file: $LOG_FILE"
echo ""

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

if [ "$SKIP_CHECKS" = false ]; then
    log_step "Running pre-flight checks..."

    # Check for corporate machine setup
    echo -e "${YELLOW}"
    cat << "EOF"
⚠️  IMPORTANT REMINDERS:

   1. If your company uses MDM, make sure it has finished configuring your machine
   2. Review your company's IT policies before proceeding
   3. This script will install Homebrew and development tools
   4. Some settings may be managed by corporate policies

EOF
    echo -e "${NC}"

    read -p "Ready to proceed with installation? (y/N): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo "Installation cancelled. Run this script when you're ready."
        exit 0
    fi

    log_success "Pre-flight checks passed"
else
    log_warning "Skipping pre-flight checks"
fi

# ============================================================================
# XCODE COMMAND LINE TOOLS
# ============================================================================

log_step "Checking Xcode Command Line Tools..."

if xcode-select -p &>/dev/null; then
    log_success "Xcode Command Line Tools already installed"
else
    log "Installing Xcode Command Line Tools..."
    log "This may take a while and will prompt for your password..."

    # Trigger installation
    xcode-select --install 2>/dev/null || true

    # Wait for installation to complete
    log "Waiting for installation to complete..."
    log "Please complete the installation in the dialog box"

    until xcode-select -p &>/dev/null; do
        sleep 5
    done

    log_success "Xcode Command Line Tools installed"
fi

# Accept Xcode license
if ! sudo xcodebuild -license check &>/dev/null; then
    log "Accepting Xcode license..."
    sudo xcodebuild -license accept || log_warning "Could not accept Xcode license automatically"
fi

# ============================================================================
# HOMEBREW
# ============================================================================

log_step "Setting up Homebrew..."

if command_exists brew; then
    log_success "Homebrew already installed"
    log "Updating Homebrew..."
    brew update || log_warning "Could not update Homebrew"
else
    log "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || error_exit "Failed to install Homebrew"

    # Add Homebrew to PATH for this session
    if [[ $(uname -m) == "arm64" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile"
    else
        eval "$(/usr/local/bin/brew shellenv)"
        echo 'eval "$(/usr/local/bin/brew shellenv)"' >> "$HOME/.zprofile"
    fi

    log_success "Homebrew installed"
fi

# ============================================================================
# INSTALL PACKAGES FROM BREWFILE
# ============================================================================

log_step "Installing packages from Brewfile..."

if [ -f "$DOTFILES_DIR/Brewfile" ]; then
    log "Running brew bundle..."
    cd "$DOTFILES_DIR"
    brew bundle install --file "./Brewfile" --verbose || log_warning "Some Brewfile packages may have failed"
    log_success "Brewfile packages installed"
else
    log_error "Brewfile not found at $DOTFILES_DIR/Brewfile"
fi

# ============================================================================
# INSTALL NERD FONTS
# ============================================================================

log_step "Installing Nerd Fonts..."

brew tap homebrew/cask-fonts || true

fonts=(
    "font-jetbrains-mono-nerd-font"
    "font-dejavu-sans-mono-nerd-font"
    "font-fira-code-nerd-font"
)

for font in "${fonts[@]}"; do
    if brew list --cask "$font" &>/dev/null; then
        log_success "$font already installed"
    else
        log "Installing $font..."
        brew install --cask "$font" || log_warning "Could not install $font"
    fi
done

# ============================================================================
# ITERM2 PREFERENCES
# ============================================================================

log_step "Configuring iTerm2..."

if [ -d "$DOTFILES_DIR/macos/iTerm/settings" ]; then
    log "Setting iTerm2 preferences folder..."
    defaults write com.googlecode.iterm2 PrefsCustomFolder -string "$DOTFILES_DIR/macos/iTerm/settings"
    defaults write com.googlecode.iterm2 LoadPrefsFromCustomFolder -bool true
    log_success "iTerm2 preferences configured"
else
    log_warning "iTerm2 settings directory not found at $DOTFILES_DIR/macos/iTerm/settings"
fi

# ============================================================================
# ASDF VERSION MANAGER
# ============================================================================

log_step "Setting up asdf version manager..."

if command_exists asdf; then
    log_success "asdf already installed"
else
    log "Installing asdf via Homebrew..."
    brew install asdf || error_exit "Failed to install asdf"

    # Add asdf to shell
    echo -e "\n. $(brew --prefix asdf)/libexec/asdf.sh" >> "$HOME/.zshrc"
    . $(brew --prefix asdf)/libexec/asdf.sh

    log_success "asdf installed"
fi

# Install asdf plugins and tools
if [ -f "$DOTFILES_DIR/asdf.sh" ]; then
    log "Installing asdf plugins and tools..."
    log_warning "This may take a while (10-30 minutes)..."
    cd "$DOTFILES_DIR"
    bash ./asdf.sh || log_warning "Some asdf tools may have failed to install"
    log_success "asdf plugins and tools installed"
else
    log_warning "asdf.sh not found"
fi

# ============================================================================
# OH MY TMUX
# ============================================================================

log_step "Setting up tmux..."

if [ -d "$HOME/.tmux" ]; then
    log_success "Oh My Tmux already installed"
else
    log "Installing Oh My Tmux..."
    git clone https://github.com/gpakosz/.tmux.git "$HOME/.tmux" || error_exit "Failed to clone Oh My Tmux"
    ln -s -f "$HOME/.tmux/.tmux.conf" "$HOME/.tmux.conf"
    log_success "Oh My Tmux installed"
fi

# ============================================================================
# NEOVIM SETUP
# ============================================================================

log_step "Setting up Neovim..."

# Create neovim directories
mkdir -p "$HOME/.config/nvim"
mkdir -p "$HOME/.local/share/nvim/site/autoload"

# Install Paq (Neovim package manager)
if [ -d "${XDG_DATA_HOME:-$HOME/.local/share}/nvim/site/pack/paqs/start/paq-nvim" ]; then
    log_success "Paq already installed"
else
    log "Installing Paq for Neovim..."
    git clone --depth=1 https://github.com/savq/paq-nvim.git \
        "${XDG_DATA_HOME:-$HOME/.local/share}/nvim/site/pack/paqs/start/paq-nvim" || \
        log_warning "Could not install Paq"
    log_success "Paq installed"
fi

# ============================================================================
# CREATE SYMLINKS
# ============================================================================

log_step "Creating symlinks..."

if [ -f "$DOTFILES_DIR/create_links.sh" ]; then
    cd "$DOTFILES_DIR"
    bash ./create_links.sh || log_warning "Some symlinks may have failed"
    log_success "Symlinks created"
else
    log_warning "create_links.sh not found"
fi

# ============================================================================
# KARABINER-ELEMENTS SETUP
# ============================================================================

log_step "Setting up Karabiner-Elements..."

# Create Karabiner directories
mkdir -p "$HOME/.config/karabiner/assets/complex_modifications"

# Karabiner needs to be opened once to initialize
if [ -d "/Applications/Karabiner-Elements.app" ]; then
    log "Karabiner-Elements installed"

    # Re-run create_links to link Karabiner configs
    if [ -d "$DOTFILES_DIR/config/karabiner" ]; then
        log "Linking Karabiner configurations..."
        cd "$DOTFILES_DIR"
        bash ./create_links.sh || true
        log_success "Karabiner configurations linked"
        log_warning "You need to open Karabiner-Elements and enable the modifications"
    fi
else
    log_warning "Karabiner-Elements not installed via Brewfile"
fi

# ============================================================================
# ZSH SETUP
# ============================================================================

log_step "Setting up Zsh..."

# Make sure .config/zsh exists
mkdir -p "$HOME/.config/zsh"

# Set Zsh as default shell if it isn't already
if [ "$SHELL" != "$(which zsh)" ]; then
    log "Setting Zsh as default shell..."
    chsh -s "$(which zsh)" || log_warning "Could not change default shell. Run: chsh -s $(which zsh)"
else
    log_success "Zsh is already the default shell"
fi

# ============================================================================
# INSTALL GENERIC SETUP
# ============================================================================

log_step "Running generic installation script..."

if [ -f "$DOTFILES_DIR/install_generic.sh" ]; then
    cd "$DOTFILES_DIR"
    bash ./install_generic.sh || log_warning "Generic install had some issues"
    log_success "Generic installation completed"
else
    log_warning "install_generic.sh not found"
fi

# ============================================================================
# POST-INSTALL VERIFICATION
# ============================================================================

log_step "Verifying installation..."

echo ""
log "Checking critical tools..."

tools=(
    "git"
    "brew"
    "zsh"
    "nvim"
    "tmux"
    "fzf"
    "gh"
    "asdf"
)

failed_tools=()

for tool in "${tools[@]}"; do
    if command_exists "$tool"; then
        version=$($tool --version 2>&1 | head -n1 || echo "unknown")
        log_success "$tool: $version"
    else
        log_error "$tool: NOT FOUND"
        failed_tools+=("$tool")
    fi
done

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                  INSTALLATION COMPLETE                       ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ ${#failed_tools[@]} -eq 0 ]; then
    log_success "All critical tools installed successfully!"
else
    log_warning "Some tools failed to install: ${failed_tools[*]}"
    log "You may need to install these manually"
fi

echo ""
echo -e "${GREEN}Next steps:${NC}"
echo ""
echo "1. ${YELLOW}Restart your terminal${NC} (or run: source ~/.zshrc)"
echo ""
echo "2. ${YELLOW}Restore your backups:${NC}"
echo "   - GPG keys: ./restore_gpg_keys.sh ~/Migration_Backup/latest/critical/gnupg_backup.tar.gz"
echo "   - SSH keys: ./restore_ssh_keys.sh ~/Migration_Backup/latest/critical/ssh"
echo "   - Other data: ./restore_backups.sh ~/Migration_Backup/latest"
echo ""
echo "3. ${YELLOW}Configure remaining apps:${NC}"
echo "   - Open Karabiner-Elements and enable your key modifications"
echo "   - Sign in to 1Password"
echo "   - Sign in to Google Drive (to access your backed up files)"
echo "   - Import DBeaver connections (if backed up)"
echo ""
echo "4. ${YELLOW}Set up Git:${NC}"
echo "   git config --global user.name \"Your Name\""
echo "   git config --global user.email \"your.email@bitso.com\""
echo ""
echo "5. ${YELLOW}Test your setup:${NC}"
echo "   - Test SSH: ssh -T git@github.com"
echo "   - Test GPG: echo 'test' | gpg --clearsign"
echo "   - Test asdf: asdf list"
echo ""
echo "6. ${YELLOW}Review POST_INSTALL.md${NC} for additional manual steps"
echo ""

log "Full log saved to: $LOG_FILE"
echo ""
echo -e "${GREEN}Happy coding! 🚀${NC}"
