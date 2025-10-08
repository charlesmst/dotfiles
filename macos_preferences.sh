#!/bin/bash

# macOS System Preferences Configuration
# This script configures macOS system preferences to optimize for development
#
# NOTE: Many preferences require logging out or restarting to take effect
# Usage: ./macos_preferences.sh

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

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

echo -e "${BLUE}"
cat << "EOF"
╔══════════════════════════════════════════════════════════════╗
║           macOS System Preferences Configuration             ║
╚══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo ""
echo "This script will configure macOS system preferences for development."
echo "You can customize these settings after running this script."
echo ""
echo -e "${YELLOW}Note: Most changes require logging out or restarting.${NC}"
echo ""
read -p "Continue? (y/N): " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 0
fi

echo ""

# Close System Preferences to prevent conflicts
osascript -e 'tell application "System Preferences" to quit' 2>/dev/null || true

# ============================================================================
# GENERAL UI/UX
# ============================================================================

log_step "Configuring General UI/UX..."

# Disable the sound effects on boot
log "Disabling boot sound effects..."
sudo nvram SystemAudioVolume=" " 2>/dev/null || log_warning "Could not disable boot sound"

# Expand save panel by default
defaults write NSGlobalDomain NSNavPanelExpandedStateForSaveMode -bool true
defaults write NSGlobalDomain NSNavPanelExpandedStateForSaveMode2 -bool true
log_success "Expand save panel by default"

# Expand print panel by default
defaults write NSGlobalDomain PMPrintingExpandedStateForPrint -bool true
defaults write NSGlobalDomain PMPrintingExpandedStateForPrint2 -bool true
log_success "Expand print panel by default"

# Save to disk (not to iCloud) by default
defaults write NSGlobalDomain NSDocumentSaveNewDocumentsToCloud -bool false
log_success "Save to disk by default"

# Disable the "Are you sure you want to open this application?" dialog
defaults write com.apple.LaunchServices LSQuarantine -bool false
log_success "Disable 'Are you sure?' dialog for applications"

# Reveal IP address, hostname, OS version, etc. when clicking the clock in login window
sudo defaults write /Library/Preferences/com.apple.loginwindow AdminHostInfo HostName 2>/dev/null || true
log_success "Show system info in login window"

# ============================================================================
# KEYBOARD & INPUT
# ============================================================================

log_step "Configuring Keyboard & Input..."

# Set keyboard repeat rate (requires logout)
defaults write NSGlobalDomain KeyRepeat -int 2
defaults write NSGlobalDomain InitialKeyRepeat -int 15
log_success "Set fast keyboard repeat rate"

# Disable press-and-hold for keys in favor of key repeat
defaults write NSGlobalDomain ApplePressAndHoldEnabled -bool false
log_success "Enable key repeat instead of press-and-hold"

# Disable auto-correct
defaults write NSGlobalDomain NSAutomaticSpellingCorrectionEnabled -bool false
log_success "Disable auto-correct"

# ============================================================================
# TRACKPAD, MOUSE, BLUETOOTH
# ============================================================================

log_step "Configuring Trackpad & Mouse..."

# Enable tap to click for this user and for the login screen
defaults write com.apple.driver.AppleBluetoothMultitouch.trackpad Clicking -bool true
defaults -currentHost write NSGlobalDomain com.apple.mouse.tapBehavior -int 1
defaults write NSGlobalDomain com.apple.mouse.tapBehavior -int 1
log_success "Enable tap to click"

# Trackpad: enable three finger drag
defaults write com.apple.driver.AppleBluetoothMultitouch.trackpad TrackpadThreeFingerDrag -bool true
defaults write com.apple.AppleMultitouchTrackpad TrackpadThreeFingerDrag -bool true
log_success "Enable three finger drag"

# Increase mouse tracking speed
defaults write NSGlobalDomain com.apple.mouse.scaling -float 2.5
log_success "Increase mouse tracking speed"

# ============================================================================
# FINDER
# ============================================================================

log_step "Configuring Finder..."

# Show hidden files by default
defaults write com.apple.finder AppleShowAllFiles -bool true
log_success "Show hidden files"

# Show all filename extensions
defaults write NSGlobalDomain AppleShowAllExtensions -bool true
log_success "Show all file extensions"

# Show status bar
defaults write com.apple.finder ShowStatusBar -bool true
log_success "Show status bar"

# Show path bar
defaults write com.apple.finder ShowPathbar -bool true
log_success "Show path bar"

# Display full POSIX path as Finder window title
defaults write com.apple.finder _FXShowPosixPathInTitle -bool true
log_success "Show full path in title bar"

# Keep folders on top when sorting by name
defaults write com.apple.finder _FXSortFoldersFirst -bool true
log_success "Keep folders on top"

# When performing a search, search the current folder by default
defaults write com.apple.finder FXDefaultSearchScope -string "SCcf"
log_success "Search current folder by default"

# Disable the warning when changing a file extension
defaults write com.apple.finder FXEnableExtensionChangeWarning -bool false
log_success "Disable extension change warning"

# Avoid creating .DS_Store files on network or USB volumes
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool true
defaults write com.apple.desktopservices DSDontWriteUSBStores -bool true
log_success "Avoid .DS_Store on network/USB volumes"

# Use list view in all Finder windows by default
# Four-letter codes: `icnv` (icon), `clmv` (column), `Flwv` (cover flow), `Nlsv` (list)
defaults write com.apple.finder FXPreferredViewStyle -string "Nlsv"
log_success "Use list view by default"

# Show the ~/Library folder
chflags nohidden ~/Library
log_success "Show ~/Library folder"

# Show the /Volumes folder
sudo chflags nohidden /Volumes 2>/dev/null || true
log_success "Show /Volumes folder"

# ============================================================================
# DOCK & MISSION CONTROL
# ============================================================================

log_step "Configuring Dock & Mission Control..."

# Set the icon size of Dock items
defaults write com.apple.dock tilesize -int 48
log_success "Set Dock icon size to 48px"

# Enable auto-hide
defaults write com.apple.dock autohide -bool true
log_success "Enable Dock auto-hide"

# Make Dock icons of hidden applications translucent
defaults write com.apple.dock showhidden -bool true
log_success "Make hidden apps translucent in Dock"

# Don't show recent applications in Dock
defaults write com.apple.dock show-recents -bool false
log_success "Hide recent applications in Dock"

# Speed up Mission Control animations
defaults write com.apple.dock expose-animation-duration -float 0.1
log_success "Speed up Mission Control animations"

# Don't automatically rearrange Spaces based on most recent use
defaults write com.apple.dock mru-spaces -bool false
log_success "Don't auto-rearrange Spaces"

# ============================================================================
# SCREENSHOTS
# ============================================================================

log_step "Configuring Screenshots..."

# Save screenshots to the desktop
defaults write com.apple.screencapture location -string "${HOME}/Desktop"
log_success "Save screenshots to Desktop"

# Save screenshots in PNG format (other options: BMP, GIF, JPG, PDF, TIFF)
defaults write com.apple.screencapture type -string "png"
log_success "Save screenshots as PNG"

# Disable shadow in screenshots
defaults write com.apple.screencapture disable-shadow -bool true
log_success "Disable shadows in screenshots"

# ============================================================================
# TERMINAL & iTERM2
# ============================================================================

log_step "Configuring Terminal..."

# Only use UTF-8 in Terminal.app
defaults write com.apple.terminal StringEncodings -array 4
log_success "Use UTF-8 in Terminal"

# Enable Secure Keyboard Entry in Terminal.app
defaults write com.apple.terminal SecureKeyboardEntry -bool true
log_success "Enable Secure Keyboard Entry"

# ============================================================================
# ACTIVITY MONITOR
# ============================================================================

log_step "Configuring Activity Monitor..."

# Show the main window when launching Activity Monitor
defaults write com.apple.ActivityMonitor OpenMainWindow -bool true
log_success "Show main window on launch"

# Visualize CPU usage in the Activity Monitor Dock icon
defaults write com.apple.ActivityMonitor IconType -int 5
log_success "Show CPU usage in Dock icon"

# Show all processes in Activity Monitor
defaults write com.apple.ActivityMonitor ShowCategory -int 0
log_success "Show all processes"

# Sort Activity Monitor results by CPU usage
defaults write com.apple.ActivityMonitor SortColumn -string "CPUUsage"
defaults write com.apple.ActivityMonitor SortDirection -int 0
log_success "Sort by CPU usage"

# ============================================================================
# TEXT EDIT
# ============================================================================

log_step "Configuring TextEdit..."

# Use plain text mode for new TextEdit documents
defaults write com.apple.TextEdit RichText -int 0
log_success "Use plain text mode by default"

# Open and save files as UTF-8 in TextEdit
defaults write com.apple.TextEdit PlainTextEncoding -int 4
defaults write com.apple.TextEdit PlainTextEncodingForWrite -int 4
log_success "Use UTF-8 in TextEdit"

# ============================================================================
# TIME MACHINE
# ============================================================================

log_step "Configuring Time Machine..."

# Prevent Time Machine from prompting to use new hard drives as backup volume
defaults write com.apple.TimeMachine DoNotOfferNewDisksForBackup -bool true
log_success "Don't prompt for new disks as backup"

# ============================================================================
# RESTART AFFECTED APPS
# ============================================================================

log_step "Restarting affected applications..."

for app in "Activity Monitor" \
    "cfprefsd" \
    "Dock" \
    "Finder" \
    "SystemUIServer"; do
    killall "$app" &>/dev/null || true
done

log_success "Applications restarted"

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║            CONFIGURATION COMPLETE                           ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

log_success "macOS preferences configured!"
echo ""
echo -e "${YELLOW}Important:${NC}"
echo "  - Many changes require a logout/restart to take effect"
echo "  - Some settings may be managed by your company's MDM"
echo "  - Review System Preferences to verify settings"
echo ""
echo -e "${GREEN}Configured:${NC}"
echo "  ✓ Fast keyboard repeat rate"
echo "  ✓ Finder optimizations (show hidden files, extensions, path bar)"
echo "  ✓ Dock auto-hide and optimization"
echo "  ✓ Screenshot settings (PNG, no shadow, save to Desktop)"
echo "  ✓ Trackpad (tap to click, three finger drag)"
echo "  ✓ Activity Monitor optimizations"
echo "  ✓ Disable auto-correct"
echo ""
echo -e "${YELLOW}Recommended next steps:${NC}"
echo "  1. Log out and log back in for all changes to take effect"
echo "  2. Review System Preferences > Keyboard > Shortcuts"
echo "  3. Configure any additional settings specific to your workflow"
echo ""
