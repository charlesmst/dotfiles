#!/bin/bash

brew bundle install --file "./Brewfile" --verbose

brew tap homebrew/cask-fonts
brew install --cask font-jetbrains-mono-nerd-font
brew install --cask font-dejavu-sans-mono-nerd-font
brew install --cask font-fira-code-nerd-font

# Specify the preferences directory
defaults write com.googlecode.iterm2 PrefsCustomFolder -string "$(pwd)/macos/iTerm/settings"
# Tell iTerm2 to use the custom preferences in the directory
defaults write com.googlecode.iterm2 LoadPrefsFromCustomFolder -bool true

./install_generic.sh
