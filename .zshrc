export ZDOTDIR=$HOME/.config/zsh
. "$HOME/.config/zsh/zsh_functions.zsh"

zsh_add_file zsh_prompt.zsh
zsh_add_file zsh_vi_mode.zsh

# Plugins
zsh_add_plugin "zsh-users/zsh-autosuggestions"
zsh_add_plugin "zsh-users/zsh-syntax-highlighting"
zsh_add_plugin "hlissner/zsh-autopair"
zsh_add_completion "esc/conda-zsh-completion" false

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

