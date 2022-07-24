export ZSH="$HOME/.oh-my-zsh"
SH_THEME="robbyrussell"
plugins=(git fzf-zsh-plugin)
source $ZSH/oh-my-zsh.sh


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

alias z="zoxide"
eval "$(zoxide init zsh)"

export AWS_PROFILE=dev
. /opt/homebrew/opt/asdf/asdf.sh

#THIS MUST BE AT THE END OF THE FILE FOR SDKMAN TO WORK!!!
export SDKMAN_DIR="$HOME/.sdkman"
[[ -s "$HOME/.sdkman/bin/sdkman-init.sh" ]] && source "$HOME/.sdkman/bin/sdkman-init.sh"
