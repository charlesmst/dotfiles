#!/bin/bash
initial_path=$(pwd)
cd ~/

# Install yay
sudo pacman -S --needed base-devel git

if [ ! -d "$HOME/yay-git/" ]; then
	git clone https://aur.archlinux.org/yay-git.git
	cd yay-git/
	makepkg -si
fi

pacman_software="git make typescript xclip a52dec faac faad2 flac jasper lame libdca libdv libmad libmpeg2 libtheora libvorbis libxv wavpack x264 xvidcore"
yay_sofware="tmux google-chrome slack-desktop asdf-vm zsh lazygit neovim thefuck fzf intellij-idea-community-edition gnome-terminal-transparency extension-manager pgcli"

echo "installing $pacman_software with pacman"
sudo pacman -Sy $pacman_software
echo "installing $yay_software with yay"
yay -Sy $yay_software

echo "installing flatpacks"
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

flatpak install flathub com.spotify.Client

echo "installing fonts"
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/JetBrains/JetBrainsMono/master/install_manual.sh)"

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


# pop os shell
if [ ! -d "$HOME/shell/" ]; then
	cd ~/
	git clone https://github.com/pop-os/shell.git
	cd shell
	make local-install
	cd ~/
	gnome-extensions enable pop-shell@system76.com
fi

# change default shell
chsh -s $(which zsh)

# Docker desktop
wget "https://desktop.docker.com/linux/main/amd64/docker-desktop-4.10.1-x86_64.pkg.tar.zst"
sudo pacman -U "docker-desktop-4.10.1-x86_64.pkg.tar.zst"

cd $initial_path
./install_generic.sh
