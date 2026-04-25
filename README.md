# Dotfiles

Personal development environment configuration for macOS (and Linux).

## Quick Start

### For New Machine Setup

```bash
# 1. Let MDM (Kandji) finish configuring your machine first!

# 2. Clone this repo
git clone https://github.com/yourusername/dotfiles.git ~/personal/dotfiles
cd ~/personal/dotfiles

# 3. Run the installation
./install_mac.sh

# 4. Restore your backups
./restore_gpg_keys.sh ~/Migration_Backup/latest/critical/gnupg_backup.tar.gz
./restore_ssh_keys.sh ~/Migration_Backup/latest/critical/ssh
./restore_backups.sh ~/Migration_Backup/latest

# 5. Configure system preferences (optional)
./macos_preferences.sh

# 6. Follow the post-install checklist
# See POST_INSTALL.md for detailed steps
```

---

## Overview

This repository contains:

- **Shell configuration** (Zsh with custom plugins)
- **Neovim configuration** (Lua-based)
- **Terminal configuration** (Alacritty, iTerm2, tmux)
- **Development tools** (mise, Homebrew packages, apt where applicable)
- **Keyboard customization** (Karabiner-Elements)
- **Automated installation scripts** for macOS and Linux
- **Backup and restore scripts** for machine migration

---

## Table of Contents

- [Before Migration (Old Machine)](#before-migration-old-machine)
- [Installation Scripts](#installation-scripts)
- [What's Included](#whats-included)
- [What Gets Backed Up](#what-gets-backed-up)
- [Directory Structure](#directory-structure)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)

---

## Before Migration (Old Machine)

If you're getting a new machine, **run this on your OLD machine first**:

```bash
cd ~/personal/dotfiles
./backup_before_migration.sh
```

This creates `~/Migration_Backup` with:
- GPG keys
- SSH keys
- AWS credentials
- Application settings
- Development tool configurations
- Shell history
- macOS preferences

**Upload `~/Migration_Backup` to Google Drive** before wiping your old machine.

---

## Installation Scripts

### `install_mac.sh`

Main installation script for macOS. Installs and configures:

- Xcode Command Line Tools
- Homebrew and packages (from Brewfile)
- Nerd Fonts (JetBrains Mono, Fira Code, DejaVu)
- mise (see Brewfile)
- Oh My Tmux
- Neovim with Paq package manager
- Karabiner-Elements configuration
- All dotfile symlinks

**Usage:**
```bash
./install_mac.sh                # Full installation with safety checks
./install_mac.sh --skip-checks  # Skip pre-flight checks
```

**Time:** 30-60 minutes (depending on internet speed)

### `install_ubuntu.sh` / `install_arch.sh`

Similar installation scripts for Linux distributions.

### `backup_before_migration.sh`

Creates comprehensive backup of your current machine configuration.

**Output:** `~/Migration_Backup/backup_YYYYMMDD_HHMMSS/`

**What's backed up:**
- 🔴 GPG & SSH keys
- 💻 Development tools (Homebrew Brewfile, mise / `.tool-versions`, npm/pip packages)
- ⚙️ Application settings (VSCode, DBeaver, Postman, etc.)
- 🐚 Shell history & configs
- ☁️ AWS, Kubernetes, Docker configs
- 🖥️ macOS system preferences

See [BACKUP_SUMMARY.md](BACKUP_SUMMARY.md) for complete details.

### `restore_backups.sh`

Restores application settings and configurations from backup.

```bash
./restore_backups.sh ~/Migration_Backup
```

### `restore_gpg_keys.sh`

Restores GPG keys from backup.

```bash
./restore_gpg_keys.sh ~/Migration_Backup/gnupg_backup_*.tar.gz
```

### `restore_ssh_keys.sh`

Restores SSH keys from backup.

```bash
./restore_ssh_keys.sh ~/Migration_Backup/ssh
```

### `macos_preferences.sh`

Configures macOS system preferences for development (optional).

**Configures:**
- Fast keyboard repeat rate
- Finder optimizations (show hidden files, extensions, etc.)
- Dock auto-hide
- Screenshot settings
- Trackpad settings (tap to click, three-finger drag)
- Disable auto-correct
- Activity Monitor optimizations

**Note:** Requires logout/restart for full effect.

### `create_links.sh`

Creates symlinks from this repo to your home directory.

**Links created:**
- `.zshrc` → `~/.zshrc`
- `config/nvim` → `~/.config/nvim`
- `config/alacritty` → `~/.config/alacritty`
- `config/karabiner` → `~/.config/karabiner`
- `.tmux.conf.local` → `~/.tmux.conf.local`
- And more...

---

## What Gets Backed Up

The backup script creates a comprehensive backup organized in subdirectories:

```
~/Migration_Backup/
├── latest/                    # Symlink to most recent backup
└── backup_YYYYMMDD_HHMMSS/   # Timestamped backup
    ├── critical/              # GPG & SSH keys
    ├── homebrew/              # Complete Brewfile + package lists
    ├── dev/                   # npm, pip, mise tool-version backups
    ├── vscode/                # Settings, extensions, snippets
    ├── app_preferences/       # DBeaver, Postman, Karabiner, etc.
    ├── aws/                   # AWS credentials & config
    ├── git/                   # Git config & credentials
    ├── shell/                 # Zsh/Bash history
    ├── kube/                  # Kubernetes configs
    ├── docker/                # Docker configs
    └── macos_settings/        # System preferences
```

**Key features:**
- ✅ Auto-generates Brewfile from ALL installed packages
- ✅ Organized in logical subdirectories
- ✅ Creates `latest` symlink for easy access
- ✅ Timestamped backups (keep multiple versions)
- ✅ Includes detailed inventory and logs

📄 **See [BACKUP_SUMMARY.md](BACKUP_SUMMARY.md) for complete breakdown of what's backed up**

---

## What's Included

### Shell (Zsh)

**Location:** `config/zsh/`, `.zshrc`

**Features:**
- Custom prompt with git integration
- Vi mode with visual indicators
- Auto-suggestions and syntax highlighting
- FZF integration for fuzzy finding
- Custom aliases and functions
- Fast startup time

**Plugins (auto-installed):**
- zsh-autosuggestions
- zsh-syntax-highlighting
- fzf-zsh-plugin
- zsh-system-clipboard

### Neovim

**Location:** `config/nvim/`

**Package Manager:** Paq

**Features:**
- Lua-based configuration
- LSP support (via CoC or native LSP)
- Treesitter syntax highlighting
- Telescope fuzzy finder
- Git integration
- File explorer

**First time setup:**
```bash
nvim
:PaqInstall
```

### Terminal

**Alacritty:** `config/alacritty/alacritty.toml`
- GPU-accelerated
- Fast and lightweight

**iTerm2:** `macos/iTerm/settings/`
- Custom color scheme
- Key mappings
- Profile settings

**tmux:** `.tmux.conf.local`
- Based on Oh My Tmux
- Custom key bindings
- Status bar configuration

### Development tools (mise, Homebrew, apt)

Use **mise** for per-project runtimes (`.mise.toml` / `.tool-versions`), **Homebrew** on macOS (`Brewfile`), and **apt** on Ubuntu where the install scripts pull packages. Install tools with `mise install`, `brew install`, or your distro package manager.

### Homebrew Packages

**Location:** `Brewfile`

**CLI Tools:**
- awscli
- bat (better cat)
- fd (better find)
- fzf (fuzzy finder)
- gh (GitHub CLI)
- git, git-delta
- htop
- jq, yq
- lazygit
- neovim
- ripgrep (rg)
- tmux
- zsh

**Applications:**
- 1Password CLI
- DBeanver Community
- iTerm2
- Postman
- Spotify
- Tunnelblick (VPN)

### Keyboard Customization (Karabiner-Elements)

**Location:** `config/karabiner/assets/complex_modifications/`

**Modifications:**
- `capslock_charles.json` - Capslock as Hyper/Escape
- `ctrl_enchanced.json` - Enhanced Ctrl key behaviors
- `mouse.json` - Mouse button customizations

---

## Directory Structure

```
dotfiles/
├── README.md                          # This file
├── POST_INSTALL.md                    # Post-installation checklist
├── BACKUP_SUMMARY.md                  # Complete backup breakdown
├── Brewfile                           # Homebrew packages
├── .zshrc                             # Main Zsh configuration
├── .vimrc                             # Vim configuration
├── .ideavimrc                         # IdeaVim configuration
├── .tmux.conf.local                   # Tmux configuration
│
├── install_mac.sh                     # Main macOS installer
├── install_ubuntu.sh                  # Ubuntu installer
├── install_arch.sh                    # Arch Linux installer
├── install_generic.sh                 # Generic setup (tmux, vim)
│
├── backup_before_migration.sh         # Backup script
├── restore_backups.sh                 # Restore application settings
├── restore_gpg_keys.sh                # Restore GPG keys
├── restore_ssh_keys.sh                # Restore SSH keys
├── macos_preferences.sh               # macOS system preferences
│
├── create_links.sh                    # Create symlinks
│
├── config/
│   ├── alacritty/                     # Alacritty terminal config
│   ├── karabiner/                     # Keyboard customization
│   ├── nvim/                          # Neovim configuration
│   │   ├── init.lua                   # Main Neovim config
│   │   ├── lua/                       # Lua modules
│   │   └── coc-settings.json          # CoC settings
│   └── zsh/                           # Zsh configuration
│       ├── zsh_functions.zsh          # Custom functions
│       ├── zsh_alias.zsh              # Aliases
│       ├── zsh_prompt.zsh             # Custom prompt
│       ├── zsh_vi_mode.zsh            # Vi mode config
│       ├── zsh_completions.zsh        # Completions
│       ├── zsh_path_mac.zsh           # macOS PATH
│       └── zsh_path_linux.zsh         # Linux PATH
│
├── macos/
│   └── iTerm/
│       └── settings/                  # iTerm2 preferences
│
├── private/                           # Private configs (not committed)
│   ├── .ssh/                          # SSH keys (gitignored)
│   ├── company/                       # Company-specific configs
│   └── init.sh                        # Private initialization
│
├── tmux/
│   └── tmux-sessionizer.sh            # Tmux session management
│
└── utilities/                         # Utility scripts
    ├── set-audio-output.sh
    ├── display.sh
    └── restart-on-windows.sh
```

---

## Customization

### Adding Your Own Configurations

1. **Fork this repository** (or use it as a template)

2. **Customize configs:**
   - Edit `.zshrc` for shell preferences
   - Modify `config/nvim/init.lua` for Neovim
   - Update `Brewfile` to add/remove packages
   - Use `mise`, `brew`, or `apt` for language runtimes and CLIs

3. **Add private configs:**
   - Create `private/` directory for sensitive files
   - Add to `.gitignore`
   - Use `private/init.sh` for custom initialization

4. **Update scripts:**
   - Modify `install_mac.sh` for additional setup steps
   - Add your own utility scripts to `utilities/`

### Company-Specific Configurations

Store company-specific configs in `private/company/`:

```bash
private/
├── company/
│   ├── vpn-config.ovpn
│   ├── aws-config
│   └── company-tools.sh
└── init.sh
```

Then in `private/init.sh`:
```bash
#!/bin/bash
source ~/personal/dotfiles/private/company/company-tools.sh
```

---

## Troubleshooting

### Common Issues

#### Homebrew not found after installation
```bash
# Apple Silicon
eval "$(/opt/homebrew/bin/brew shellenv)"

# Intel
eval "$(/usr/local/bin/brew shellenv)"
```

#### mise not found
```bash
brew install mise   # macOS
# See https://mise.jdx.dev for Linux install
```

#### Symlinks not working
```bash
# Re-run create_links.sh
./create_links.sh
```

#### GPG signing commits fails
```bash
# Add to ~/.zshrc
export GPG_TTY=$(tty)

# Restart gpg-agent
gpgconf --kill gpg-agent
```

#### SSH keys not working
```bash
# Fix permissions
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_rsa
chmod 644 ~/.ssh/id_rsa.pub

# Add to ssh-agent
ssh-add ~/.ssh/id_rsa
```

#### Neovim plugins not loading
```bash
# Reinstall Paq
rm -rf ~/.local/share/nvim/site/pack/paqs

# Clone Paq again
git clone --depth=1 https://github.com/savq/paq-nvim.git \
    "${XDG_DATA_HOME:-$HOME/.local/share}/nvim/site/pack/paqs/start/paq-nvim"

# Open Neovim and install plugins
nvim
:PaqInstall
```

### Getting Help

1. Check [POST_INSTALL.md](POST_INSTALL.md) for detailed troubleshooting
2. Review script logs (saved in `~/*.log`)
3. Open an issue in this repository

---

## Maintenance

### Keeping Dotfiles Updated

```bash
cd ~/personal/dotfiles
git pull origin main
./create_links.sh  # Refresh symlinks if needed
```

### Updating Homebrew Packages

```bash
brew update
brew upgrade
brew cleanup
```

### Updating mise tools

```bash
mise upgrade
mise ls
```

### Backing Up Your Configurations

Periodically commit and push your changes:

```bash
cd ~/personal/dotfiles
git add .
git commit -m "Update configurations"
git push
```

---

## Migration Workflow Summary

### On Old Machine
1. ✅ Run `./backup_before_migration.sh`
2. ✅ Upload backup to cloud storage (Google Drive, Dropbox, etc.)
3. ✅ Verify backup completed successfully
4. ✅ Push any uncommitted dotfiles changes

### On New Machine
1. ✅ Wait for corporate MDM to finish configuration (if applicable)
2. ✅ Install cloud storage and sync backup
3. ✅ Clone dotfiles: `git clone <repo> ~/personal/dotfiles`
4. ✅ Run `./install_mac.sh`
5. ✅ Run restore scripts (GPG, SSH, backups)
6. ✅ Run `./macos_preferences.sh` (optional)
7. ✅ Follow [POST_INSTALL.md](POST_INSTALL.md) checklist
8. ✅ Test everything works
9. ✅ Clean up old machine

**Estimated total time:** 4-6 hours (including downloads and configuration)

---

## Credits & Inspiration

- [Oh My Tmux](https://github.com/gpakosz/.tmux) - tmux configuration
- [Paq](https://github.com/savq/paq-nvim) - Neovim package manager
- Various dotfiles repos and the community

---

## License

MIT License - Feel free to use and modify for your own needs.

---

## TODO

- [ ] Add Docker configuration
- [ ] Add VS Code extensions backup
- [ ] Create Linux versions of backup/restore scripts
- [ ] Add automatic Brewfile generation from current packages
- [ ] Add pre-commit hooks for dotfiles validation

---

**Last updated:** 2025-10-08
