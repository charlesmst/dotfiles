#!/bin/zsh

if [ -d "/opt/homebrew/opt/libpq/bin" ];then
	export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
fi

if [ -d "/usr/local/lib/docker/cli-plugins" ];then
	export PATH="/usr/local/lib/docker/cli-plugins:$PATH"
fi


. /opt/homebrew/opt/asdf/asdf.sh
