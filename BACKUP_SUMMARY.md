# Backup Summary

Complete list of everything backed up by `backup_before_migration.sh`.

---

## Backup Structure

```
~/Migration_Backup/
├── latest/                           # Symlink to most recent backup
└── backup_YYYYMMDD_HHMMSS/          # Timestamped backup directory
    ├── backup_log.txt               # Detailed log of backup process
    ├── INVENTORY.md                 # Inventory of what was backed up
    │
    ├── critical/                    # CRITICAL - Must restore first
    │   ├── gnupg_backup.tar.gz     # GPG keys (encrypted keys, trustdb)
    │   └── ssh/                     # SSH keys and config
    │       ├── id_rsa              # Private SSH keys
    │       ├── id_rsa.pub          # Public SSH keys
    │       ├── config              # SSH configuration
    │       └── known_hosts         # Known hosts
    │
    ├── aws/                         # AWS CLI configuration
    │   ├── config                   # AWS profiles and regions
    │   ├── credentials             # AWS access keys (if present)
    │   └── sso/                    # AWS SSO cache
    │
    ├── git/                         # Git configuration
    │   ├── gitconfig               # Global git config
    │   ├── gitignore_global        # Global gitignore
    │   └── git-credentials         # Git credentials (if present)
    │
    ├── shell/                       # Shell configuration & history
    │   ├── zsh_history             # Zsh command history
    │   ├── bash_history            # Bash command history
    │   └── home_configs/           # All shell files from home directory
    │       ├── .zshrc              # Zsh config
    │       ├── .zshenv             # Zsh environment
    │       ├── .zprofile           # Zsh profile
    │       ├── .bashrc             # Bash config
    │       ├── .bash_profile       # Bash profile
    │       ├── .profile            # Generic profile
    │       ├── .secrets.sh         # Secret environment vars
    │       ├── .fzf.zsh            # FZF integration
    │       └── *.sh                # Any shell scripts in home root
    │
    ├── homebrew/                    # Homebrew packages
    │   ├── Brewfile                # Complete Brewfile (all packages)
    │   ├── brew-formulas.txt       # List of installed formulas
    │   ├── brew-casks.txt          # List of installed casks
    │   └── brew-taps.txt           # List of tapped repositories
    │
    ├── dev/                         # Development tools
    │   ├── tool-versions           # asdf tool versions
    │   ├── npmrc                   # npm configuration
    │   ├── npm-global-packages.txt # NPM global packages
    │   └── pip-packages.txt        # Python pip packages
    │
    ├── vscode/                      # Visual Studio Code
    │   ├── settings.json           # VSCode settings
    │   ├── keybindings.json        # Custom keybindings
    │   ├── snippets/               # Code snippets
    │   └── extensions.txt          # List of installed extensions
    │
    ├── claude/                      # Claude Code (AI assistant)
    │   ├── settings.json           # Claude settings
    │   ├── history.jsonl           # Chat history
    │   ├── file-history/           # File edit history
    │   └── shell-snapshots/        # Shell command snapshots
    │
    ├── app_preferences/             # Application preferences
    │   ├── karabiner/              # Karabiner-Elements key mappings
    │   ├── Rectangle.plist         # Rectangle window manager
    │   ├── Magnet.plist            # Magnet window manager
    │   ├── Spectacle.plist         # Spectacle window manager
    │   ├── Alfred/                 # Alfred settings & workflows
    │   ├── Postman/                # Postman collections & environments
    │   └── DBeaverData/            # DBeaver database connections
    │
    ├── kube/                        # Kubernetes configuration
    │   ├── config                  # kubectl config with contexts
    │   └── cache/                  # Kubernetes cache
    │
    ├── docker/                      # Docker configuration
    │   └── config.json             # Docker daemon config
    │
    ├── macos_settings/              # macOS system preferences
    │   ├── dock.plist              # Dock preferences
    │   ├── finder.plist            # Finder preferences
    │   ├── global.plist            # Global system preferences
    │   ├── trackpad.plist          # Trackpad preferences
    │   ├── screencapture.plist     # Screenshot preferences
    │   └── current_defaults.sh     # Script with current defaults
    │
    ├── misc/                        # Miscellaneous configs
    │   ├── vimrc                   # Vim config (if not in dotfiles)
    │   ├── vim/                    # Vim plugins
    │   ├── tmux.conf               # Tmux config (if not in dotfiles)
    │   └── secrets.sh              # Secret environment variables
    │
    └── projects/                    # Source code (OPTIONAL, prompted)
        └── */                      # Your project directories
                                    # (excludes: node_modules, build artifacts)
```

---

## Detailed Breakdown

### 🔴 Critical Files (Must Restore)

| Item | Location | Description | Restore Priority |
|------|----------|-------------|------------------|
| **GPG Keys** | `critical/gnupg_backup.tar.gz` | All GPG keys, trust database, revocation certificates | **CRITICAL** |
| **SSH Keys** | `critical/ssh/` | Private/public keys, SSH config, known hosts | **CRITICAL** |
| **AWS Credentials** | `aws/` | AWS CLI configuration and credentials | **HIGH** |

### 💻 Development Environment

| Item | Location | Description | Notes |
|------|----------|-------------|-------|
| **Git Config** | `git/gitconfig` | User name, email, signing key, aliases | Required for commits |
| **Tool Versions** | `dev/tool-versions` | asdf managed tool versions | Restore before running asdf |
| **Homebrew Brewfile** | `homebrew/Brewfile` | **Complete list of all installed packages** | Run `brew bundle install` |
| **npm Config** | `dev/npmrc` | npm registry, auth tokens, settings | Contains sensitive data |
| **NPM Packages** | `dev/npm-global-packages.txt` | Global npm packages list | Manual install |
| **Python Packages** | `dev/pip-packages.txt` | Python packages list | Manual install |
| **Projects** | `projects/` | Source code (optional, prompted during backup) | Dependencies excluded |

### 🛠️ Applications & Settings

| Item | Location | What's Included |
|------|----------|-----------------|
| **VSCode** | `vscode/` | Settings, keybindings, snippets, extensions list |
| **Claude Code** | `claude/` | Settings, chat history, file history, shell snapshots |
| **Karabiner** | `app_preferences/karabiner/` | Keyboard customizations and complex modifications |
| **DBeaver** | `app_preferences/DBeaverData/` | Database connections (passwords excluded) |
| **Postman** | `app_preferences/Postman/` | Collections, environments, settings |
| **Alfred** | `app_preferences/Alfred/` | Workflows, preferences, custom searches |
| **Window Managers** | `app_preferences/*.plist` | Rectangle, Magnet, or Spectacle preferences |

### 🐚 Shell & Terminal

| Item | What's Backed Up |
|------|------------------|
| **Zsh History** | Complete command history |
| **Bash History** | Complete command history |
| **Shell Configs** | All shell files from home: .zshrc, .bashrc, .profile, .zshenv, .bash_profile, etc. |
| **Shell Scripts** | Any *.sh, *.bash, *.zsh files in home root directory |

### ☁️ Cloud & Infrastructure

| Item | What's Backed Up |
|------|------------------|
| **Kubernetes** | kubectl config, contexts, cached credentials |
| **Docker** | Docker daemon configuration |
| **AWS SSO** | AWS SSO cached sessions |

### 🖥️ macOS System

| Item | What's Backed Up |
|------|------------------|
| **Dock** | Position, size, auto-hide, icons |
| **Finder** | View preferences, sidebar, defaults |
| **Trackpad** | Tap to click, gestures, speed |
| **Screenshots** | Save location, format, settings |
| **Global** | Keyboard repeat, key mapping, text corrections |

---

## What's NOT Backed Up

❌ **Browser data** - Sign in manually to sync
❌ **Application passwords** - Use 1Password or re-enter
❌ **Time Machine backups** - Company policy dependent
❌ **Large media files** - Use cloud storage
❌ **Downloaded applications** - Use Brewfile to reinstall
❌ **Virtual machines** - Too large, rebuild as needed
❌ **Dependencies** - node_modules, vendor, target, build, dist, etc.
❌ **Build artifacts** - Will be regenerated from source
❌ **Docker images** - Will be re-downloaded
❌ **Python virtual environments** - venv, .venv, env
❌ **Compiled code** - *.pyc, __pycache__, .class, etc.

---

## Restore Order (Recommended)

1. **Install dotfiles** - Run `install_mac.sh`
2. **Restore GPG keys** - Run `restore_gpg_keys.sh`
3. **Restore SSH keys** - Run `restore_ssh_keys.sh`
4. **Restore other configs** - Run `restore_backups.sh`
5. **Configure system** - Run `macos_preferences.sh` (optional)
6. **Manual steps** - Follow `POST_INSTALL.md`

---

## Verification Checklist

After restoring, verify these work:

- [ ] GPG signing: `echo 'test' | gpg --clearsign`
- [ ] SSH to GitHub: `ssh -T git@github.com`
- [ ] AWS CLI: `aws sts get-caller-identity`
- [ ] Git commits: Create test commit with signature
- [ ] VSCode: Settings and extensions loaded
- [ ] Kubernetes: `kubectl get contexts`
- [ ] Homebrew: All packages from Brewfile installed

---

## Backup Size Estimates

Typical backup sizes (varies by usage):

| Component | Typical Size |
|-----------|--------------|
| GPG Keys | < 1 MB |
| SSH Keys | < 1 MB |
| Shell History | 1-10 MB |
| VSCode Settings | 1-5 MB |
| Claude Code | < 1 MB |
| DBeaver Data | 10-50 MB |
| Application Prefs | 10-100 MB |
| Kubernetes Config | 1-10 MB |
| **Subtotal (without projects)** | **50-200 MB** |
| **Projects (optional)** | **100 MB - 10+ GB** |
| **Total (with projects)** | **150 MB - 10+ GB** |

Notes:
- Large applications (Postman collections, Alfred workflows) may increase size
- Projects backup excludes dependencies, so actual size depends on source code only
- 10-20 projects with no dependencies: typically 100-500 MB
- Large monorepos: could be 1-5 GB even without dependencies

---

## Security Considerations

🔒 **Sensitive Data in Backup:**
- GPG private keys (encrypted)
- SSH private keys
- AWS credentials
- Git credentials
- npm auth tokens (in .npmrc)
- Database connection strings (no passwords)
- Shell history (may contain secrets)
- Project source code (may contain hardcoded secrets - review before backup!)

⚠️ **Security Recommendations:**
1. Encrypt the entire backup before uploading to cloud
2. Use private cloud storage with 2FA enabled
3. Delete backup after successful migration
4. Never share backup with others
5. Keep backup on encrypted external drive as alternative

---

## Automation

The backup script automatically:
- ✅ Creates timestamped backups
- ✅ Maintains a `latest` symlink
- ✅ Generates complete Brewfile from installed packages
- ✅ Logs all operations
- ✅ Creates inventory document
- ✅ Sets proper permissions
- ✅ Validates backup integrity

---

## Troubleshooting

**Backup fails partway through:**
- Check log file: `~/Migration_Backup/latest/backup_log.txt`
- Script continues on errors, check warnings

**Backup too large:**
- Check for large files: `du -sh ~/Migration_Backup/latest/*`
- Remove unnecessary files before upload

**Missing items in backup:**
- Check INVENTORY.md in backup directory
- Items marked with ✗ were not found on system

---

**Last updated:** 2025-10-08
