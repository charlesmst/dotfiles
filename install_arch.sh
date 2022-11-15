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

pacman_software="git make typescript xclip a52dec faac faad2 flac jasper lame libdca libdv libmad libmpeg2 libtheora libvorbis libxv wavpack x264 xvidcore fzf tmux zsh bat unzip"
yay_sofware="asdf-vm lazygit lazydocker neovim thefuck pgcli  github-cli k9s"
yay_noncli="google-chrome slack-desktop intellij-idea-community-edition gnome-terminal-transparency extension-manager spotify authy docker docker-compose"

echo "installing $pacman_software with pacman"
sudo pacman -Sy $pacman_software
echo "installing $yay_software with yay"
yay -Sy $yay_software



# change default shell
chsh -s $(which zsh)

if [ -n "$DESKTOP_SESSION" ]; then
	echo "INSTALLING CLI PACKAGES"
	echo "installing fonts"
	/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/JetBrains/JetBrainsMono/master/install_manual.sh)"

	echo "installing $yay_noncli"
	yay -Sy $yay_noncli

	# enable docker
	systemctl enable docker.service
	sudo usermod -a -G docker $USER

	echo "installing flatpacks"
	flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

	# enable dark theme chrome
	bash -c "$(curl -fsSL "https://raw.githubusercontent.com/felipecassiors/dotfiles/master/scripts/enable_chrome_dark_mode.sh")"

	# change gnome settings for multiple workspaces
	gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-6 '["<Control><Shift><Alt>6"]'
	gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-5 '["<Control><Shift><Alt>5"]'
	gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-4 '["<Control><Shift><Alt>4"]'
	gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-3 '["<Control><Shift><Alt>3"]'
	gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-2 '["<Control><Shift><Alt>2"]'
	gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-1 '["<Control><Shift><Alt>1"]'

	gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-6 '["<Shift><Alt>6"]'
	gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-5 '["<Shift><Alt>5"]'
	gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-4 '["<Shift><Alt>4"]'
	gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-3 '["<Shift><Alt>3"]'
	gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-2 '["<Shift><Alt>2"]'
	gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-1 '["<Shift><Alt>1"]'

	# pop os shell
	if [ ! -d "$HOME/shell/" ]; then
		cd ~/
		git clone https://github.com/pop-os/shell.git
		cd shell
		make local-install
		cd ~/
		gnome-extensions enable pop-shell@system76.com
	fi
fi




cd $initial_path
./install_generic.sh
