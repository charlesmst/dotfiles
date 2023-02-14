#!/bin/bash
DISPLAY_MAIN=2
DISPLAY_MAIN_HDMI=11
DISPLAY_MAIN_DP=0f
DISPLAY_MAIN_MAC=$DISPLAY_MAIN_HDMI
DISPLAY_MAIN_PC=$DISPLAY_MAIN_DP

DISPLAY_SECOND=1
DISPLAY_SECOND_HDMI=11
DISPLAY_SECOND_DP=0f

DISPLAY_SECOND_MAC=$DISPLAY_SECOND_DP
DISPLAY_SECOND_PC=$DISPLAY_SECOND_HDMI


if [ "$1" = "mac" ]; then
  ddcutil setvcp 60 0x$DISPLAY_MAIN_MAC --display $DISPLAY_MAIN
  if [ "$2" = "all" ]; then
    ddcutil setvcp 60 0x$DISPLAY_SECOND_MAC --display $DISPLAY_SECOND
  fi
elif [ "$1" = "pc" ]; then
  ddcutil setvcp 60 0x$DISPLAY_MAIN_PC --display $DISPLAY_MAIN
  if [ "$2" = "all" ]; then
    ddcutil setvcp 60 0x$DISPLAY_SECOND_PC --display $DISPLAY_SECOND
  fi
else
  echo "unrecognized command";
fi

