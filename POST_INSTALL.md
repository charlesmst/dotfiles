# Post-Installation Checklist

This checklist covers all the manual steps needed after running the automated installation scripts.

## Prerequisites

- [ ] Corporate MDM (if applicable) has finished configuring your machine
- [ ] You have run `./install_mac.sh` successfully
- [ ] You have access to your `~/Migration_Backup` from cloud storage

---

## 1. Restore Critical Data

### GPG Keys
```bash
cd ~/personal/dotfiles
./restore_gpg_keys.sh ~/Migration_Backup/latest/critical/gnupg_backup.tar.gz
```

**Verify:**
```bash
gpg --list-secret-keys
echo 'test' | gpg --clearsign
```

### SSH Keys
```bash
cd ~/personal/dotfiles
./restore_ssh_keys.sh ~/Migration_Backup/latest/critical/ssh
```

**Verify:**
```bash
ssh -T git@github.com
ssh -T git@gitlab.com  # if you use GitLab
```

### Other Backups
```bash
cd ~/personal/dotfiles
./restore_backups.sh ~/Migration_Backup/latest
```

---

## 2. Configure Git

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
git config --global gpg.program gpg
git config --global commit.gpgsign true
git config --global user.signingkey YOUR_GPG_KEY_ID
```

**Find your GPG key ID:**
```bash
gpg --list-secret-keys --keyid-format LONG
# Use the key ID after 'sec rsa4096/'
```

---

## 3. System Preferences (Optional)

Run the macOS preferences script to optimize system settings:
```bash
cd ~/personal/dotfiles
./macos_preferences.sh
```

Or manually configure these in System Preferences:

### Keyboard
- [ ] **Keyboard > Keyboard**
  - [ ] Key Repeat: Fast
  - [ ] Delay Until Repeat: Short
  - [ ] Press 🌐 key to: Do Nothing (or your preference)

- [ ] **Keyboard > Text**
  - [ ] Disable "Correct spelling automatically"
  - [ ] Disable "Capitalize words automatically"
  - [ ] Disable "Add period with double-space"

- [ ] **Keyboard > Shortcuts**
  - [ ] Review and customize shortcuts
  - [ ] Spotlight: Consider changing to avoid conflicts with IDEs

### Trackpad
- [ ] **Point & Click**
  - [ ] Enable "Tap to click"
  - [ ] Click: Medium
  - [ ] Tracking speed: Fast

- [ ] **More Gestures**
  - [ ] Enable "App Exposé" (swipe down with three/four fingers)

### Dock
- [ ] Position on screen: Bottom (or your preference)
- [ ] Size: Small-Medium
- [ ] Enable "Automatically hide and show the Dock"
- [ ] Disable "Show recent applications in Dock"

### Mission Control
- [ ] Disable "Automatically rearrange Spaces based on most recent use"

### Security & Privacy
- [ ] Review what MDM has configured
- [ ] **FileVault**: Should be enabled by MDM
- [ ] **Firewall**: Should be enabled by MDM

---

## 4. Configure Applications

### 1Password
- [ ] Open 1Password
- [ ] Sign in to your account
- [ ] Enable browser integration
- [ ] Enable SSH agent (if you use this feature)

### Karabiner-Elements
- [ ] Open Karabiner-Elements
- [ ] Go to "Complex Modifications"
- [ ] Enable your custom modifications:
  - [ ] Capslock modifications (capslock_charles.json)
  - [ ] Ctrl enhanced (ctrl_enchanced.json)
  - [ ] Mouse configurations (mouse.json)
- [ ] Grant necessary permissions in System Preferences

### iTerm2
- [ ] Open iTerm2
- [ ] Verify preferences are loaded from `~/personal/dotfiles/macos/iTerm/settings`
- [ ] Check color scheme
- [ ] Check font (should be a Nerd Font)
- [ ] Test terminal functionality

### Google Drive
- [ ] Sign in to Google Drive
- [ ] Wait for initial sync to complete
- [ ] Verify your backup files are accessible

### VSCode (if you use it)
- [ ] Open VSCode
- [ ] Settings should be restored automatically
- [ ] Install extensions:
```bash
cat ~/Migration_Backup/vscode/extensions.txt | xargs -L 1 code --install-extension
```

### DBeaver
- [ ] Open DBeaver
- [ ] Verify connections were restored
- [ ] Test database connections
- [ ] Re-enter passwords if needed (not backed up for security)

### Postman
- [ ] Open Postman
- [ ] Sign in to sync collections
- [ ] Verify local data was restored

### Spotify
- [ ] Sign in
- [ ] Download offline playlists (if needed)

---

## 5. Development Environment Setup

### Verify asdf tools
```bash
asdf list
```

Expected tools:
- [ ] kubectl
- [ ] helm
- [ ] nodejs
- [ ] golang
- [ ] terraform
- [ ] vault
- [ ] rust
- [ ] redis
- [ ] java

### Neovim
- [ ] Open Neovim: `nvim`
- [ ] Install plugins: `:PaqInstall`
- [ ] Check for errors
- [ ] Restart Neovim

### Test your shell
- [ ] Close and reopen terminal
- [ ] Verify zsh plugins are working
- [ ] Test fzf: `Ctrl+R` for history search
- [ ] Test thefuck: `fuck` command
- [ ] Verify PATH includes all necessary directories

---

## 6. AWS & Cloud Setup

### AWS CLI
```bash
# Verify credentials were restored
aws sts get-caller-identity

# If not working, configure saml2aws
saml2aws configure
saml2aws login
```

### Kubernetes
```bash
# If you restored .kube/config, verify:
kubectl config get-contexts

# Update contexts if needed
kubectl config use-context <context-name>
```

---

---

## 8. Optional: Additional Applications

### Applications to configure manually:
- [ ] Slack (download and sign in)
- [ ] Zoom (download and sign in)
- [ ] Chrome/Brave browser (sign in if company policy allows)
- [ ] Docker Desktop (if needed, configure resources)

### Browser Extensions:
- [ ] 1Password browser extension
- [ ] React DevTools (if you do frontend work)
- [ ] Any other development extensions you use

---

## 9. Verification & Testing

### Test Development Workflow
- [ ] Clone a test repository
  ```bash
  git clone git@github.com:your-org/test-repo.git
  ```
- [ ] Verify Git signing works
  ```bash
  cd test-repo
  git commit --allow-empty -m "Test commit"
  git log --show-signature
  ```

### Test Language Environments
- [ ] **Node.js**: `node --version && npm --version`
- [ ] **Go**: `go version`
- [ ] **Rust**: `rustc --version && cargo --version`
- [ ] **Java**: `java -version`

### Test Build Tools
- [ ] Build a project you work on
- [ ] Run tests
- [ ] Verify CI/CD tools work locally

---

## 10. Clean Up

### Old Machine
- [ ] Verify all important files are in Google Drive
- [ ] Take screenshots of any settings you might have missed
- [ ] Prepare for machine return or purchase 

### New Machine
- [ ] Delete `~/Migration_Backup` after verifying everything works
- [ ] Remove any test files created during verification
- [ ] Create a backup using Time Machine (to external drive, not iCloud)

---

## 11. Documentation

### Update Your Personal Docs
- [ ] Document any additional manual steps you had to take
- [ ] Note any issues encountered and solutions
- [ ] Consider contributing improvements back to these dotfiles

---

## Troubleshooting

### Common Issues

**Issue: GPG signing not working**
```bash
# Add to ~/.zshrc or ~/.zprofile
export GPG_TTY=$(tty)

# Restart gpg-agent
gpgconf --kill gpg-agent
```

**Issue: SSH keys not working**
```bash
# Verify permissions
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_rsa
chmod 644 ~/.ssh/id_rsa.pub

# Add to ssh-agent
ssh-add ~/.ssh/id_rsa
```

**Issue: Homebrew command not found**
```bash
# For Apple Silicon
eval "$(/opt/homebrew/bin/brew shellenv)"

# For Intel
eval "$(/usr/local/bin/brew shellenv)"
```

**Issue: asdf command not found**
```bash
# Add to ~/.zshrc
. $(brew --prefix asdf)/libexec/asdf.sh

# Then restart terminal
```

---


## Checklist Summary

Print this checklist and check off items as you complete them:

```
CRITICAL:
[ ] GPG keys restored and working
[ ] SSH keys restored and working
[ ] Git configured and signing commits
[ ] 1Password configured
[ ] VPN configured

IMPORTANT:
[ ] All backups restored
[ ] Development tools tested (node, go, rust, etc.)
[ ] Neovim plugins installed
[ ] Karabiner-Elements configured
[ ] AWS credentials working

NICE TO HAVE:
[ ] System preferences configured
[ ] VSCode extensions installed
[ ] Application preferences restored
[ ] Browser extensions installed
[ ] Old machine cleaned up
```

---

**Estimated time to complete**: 2-4 hours (depending on download speeds and manual configurations)

**Last updated**: 2025-10-08
