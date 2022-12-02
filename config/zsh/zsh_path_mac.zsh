#!/bin/zsh

if [ -d "/opt/homebrew/opt/libpq/bin" ];then
	export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
fi

. /opt/homebrew/opt/asdf/asdf.sh

export IDEA=/Applications/IntelliJ\ IDEA\ CE.app/Contents/MacOS/idea
