#!/bin/bash

brew bundle install --file "./Brewfile" --verbose

brew tap homebrew/cask-fonts
brew install --cask font-aurulent-sans-mono-nerd-font 

./create_links.sh
./asdf.sh
