. "$HOME/.config/zsh/zsh_prompt.zsh"
. "$HOME/.config/zsh/zsh_functions.zsh"
. "$HOME/.config/zsh/zsh_vi_mode.zsh"
source ~/.secrets.sh

eval $(thefuck --alias)
source <(kubectl completion zsh)

if [ -d "/opt/homebrew/opt/libpq/bin" ];then
	export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
fi

if [ -d "/usr/local/lib/docker/cli-plugins" ];then
	export PATH="/usr/local/lib/docker/cli-plugins:$PATH"
fi

source ~/.asdf/plugins/java/set-java-home.zsh



alias kc=kubectl

# export PATH="$HOME/.asdf/shims:$PATH"



set -o vi
export EDITOR=nvim
alias vim=nvim

export AWS_PROFILE=dev

if [[ "$OSTYPE" == "darwin"* ]]; then
	. /opt/homebrew/opt/asdf/asdf.sh
fi

