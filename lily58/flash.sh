#!/usr/bin/env bash

# PCB project
# git clone https://github.com/kata0510/Lily58.git

# QMK install and compile
# python3 -m pip install qmk
# cd ~/
# qmk setup

sudo cp ~/qmk_firmware/util/udev/50-qmk.rules /etc/udev/rules.d/
mkdir -p ~/qmk_firmware/keyboards/lily58/keymaps/charles
cp charles_keymap.json ~/qmk_firmware/keyboards/lily58/keymaps/charles/
cp rules.mk ~/qmk_firmware/keyboards/lily58/keymaps/charles/
cd ~/qmk_firmware/keyboards/lily58/keymaps/charles
qmk json2c charles_keymap.json > keymap.c
cd -
make clean
# make lily58:marlon
make lily58:charles:flash
