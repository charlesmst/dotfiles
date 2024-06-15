#!/bin/bash

initial_path=$(pwd)

# Install required packages
sudo add-apt-repository ppa:neovim-ppa/unstable -y
sudo apt update
sudo apt install -y build-essential git


# Install packages using apt
apt_software="git make node-typescript xclip liba52-0.7.4 libfaac0 libfaad2 libflac8 libmp3lame0 libdca0 libdv4 libmad0 libmpeg2-4 libtheora0 libvorbis0a libvorbisenc2 libvorbisfile3 libxv1 wavpack x264 fzf tmux zsh bat unzip xdg-utils jq neovim thefuck pgcli gh ripgrep  docker-compose fonts-firacode "

git clone https://github.com/asdf-vm/asdf.git ~/.asdf --branch v0.14.0

LAZYGIT_VERSION=$(curl -s "https://api.github.com/repos/jesseduffield/lazygit/releases/latest" | grep -Po '"tag_name": "v\K[^"]*')
curl -Lo lazygit.tar.gz "https://github.com/jesseduffield/lazygit/releases/latest/download/lazygit_${LAZYGIT_VERSION}_Linux_x86_64.tar.gz"
tar xf lazygit.tar.gz lazygit
sudo install lazygit /usr/local/bin
# Install packages using apt
echo "Installing $apt_software with apt"
sudo apt install -y $apt_software

# Change default shell
chsh -s $(which zsh)

# If desktop session is active, configure additional settings
if [ -n "$DESKTOP_SESSION" ]; then

    # Enable Docker
    sudo systemctl enable docker.service
    sudo usermod -a -G docker $USER

    # Install flatpak
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

    # Change GNOME settings for multiple workspaces
    gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-9 "['<Control><Shift><Alt>9']"
    gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-8 "['<Control><Shift><Alt>8']"
    gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-7 "['<Control><Shift><Alt>7']"
    gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-6 "['<Control><Shift><Alt>6']"
    gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-5 "['<Control><Shift><Alt>5']"
    gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-4 "['<Control><Shift><Alt>4']"
    gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-3 "['<Control><Shift><Alt>3']"
    gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-2 "['<Control><Shift><Alt>2']"
    gsettings set org.gnome.desktop.wm.keybindings move-to-workspace-1 "['<Control><Shift><Alt>1']"

    gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-9 "['<Shift><Alt>9']"
    gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-8 "['<Shift><Alt>8']"
    gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-7 "['<Shift><Alt>7']"
    gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-6 "['<Shift><Alt>6']"
    gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-5 "['<Shift><Alt>5']"
    gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-4 "['<Shift><Alt>4']"
    gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-3 "['<Shift><Alt>3']"
    gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-2 "['<Shift><Alt>2']"
    gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-1 "['<Shift><Alt>1']"

    gsettings set org.gnome.desktop.wm.preferences num-workspaces 9

    gsettings set org.gnome.desktop.wm.keybindings switch-input-source "['f2', 'XF86Keyboard']"
fi

#@TODO
# install go 
# install rust

cd $initial_path
./install_generic.sh

