#!/bin/bash
read -p "Are you sure you want to restart on windows? (y/n)?" CONT
if [ "$CONT" = "y" ]; then
  systemctl reboot --boot-loader-entry=auto-windows
else
  echo "operation canceled";
fi
