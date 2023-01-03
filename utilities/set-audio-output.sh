#!/bin/bash
device=`wpctl status | grep -A 10 "Sinks:" |grep "$1" | awk '{print $2}'  | sed  's/.$//'`
echo "setting device to $device"
wpctl set-default $device
