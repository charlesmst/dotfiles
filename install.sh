#!/bin/bash


# Install yay
sudo pacman -S --needed base-devel git
git clone https://aur.archlinux.org/yay-git.git
cd yay-git/
makepkg -si


sofwares=tmux google-chrome slack-desktop asdf-vm gnome-shell-extension-pop-shell zsh lazygit neovim thefuck kubectl

yay -Sy $softwares

# Docker desktop
wget "https://desktop.docker.com/linux/main/amd64/docker-desktop-4.10.1-x86_64.pkg.tar.zst"
sudo pacman -U "docker-desktop-4.10.1-x86_64.pkg.tar.zst"

# pop os shell
sudo pacman -Sy git typescript make
git clone https://github.com/pop-os/shell.git
cd shell
make local-install
cd ~/

# enable dark theme chrome
bash -c "$(curl -fsSL "https://raw.githubusercontent.com/felipecassiors/dotfiles/master/scripts/enable_chrome_dark_mode.sh")"



# change gnome settings for multiple workspaces
gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-6 '["<Control><Super>6"]'
gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-5 '["<Control><Super>5"]'
gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-4 '["<Control><Super>4"]'
gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-3 '["<Control><Super>3"]'
gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-2 '["<Control><Super>2"]'
gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-1 '["<Control><Super>1"]'

gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-6 '["<Super>6"]'
gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-5 '["<Super>5"]'
gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-4 '["<Super>4"]'
gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-3 '["<Super>3"]'
gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-2 '["<Super>2"]'
gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-1 '["<Super>1"]'

# change default shell
chsh -s $(which zsh)

# oh my zsh
git clone https://github.com/ohmyzsh/ohmyzsh ~/.oh-my-zsh
# vim plug
curl -fLo ~/.vim/autoload/plug.vim --create-dirs \
    https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
