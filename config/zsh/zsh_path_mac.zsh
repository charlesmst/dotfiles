#!/bin/zsh

if [ -d "/opt/homebrew/opt/libpq/bin" ];then
	export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
fi

. "$(brew --prefix asdf)/libexec/asdf.sh"

export IDEA=/Applications/IntelliJ\ IDEA\ CE.app/Contents/MacOS/idea

# rancher desktop
export PATH="$HOME/.rd/bin:$PATH"
