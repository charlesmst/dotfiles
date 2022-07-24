export ZSH="$HOME/.oh-my-zsh"
SH_THEME="robbyrussell"
plugins=(git fzf-zsh-plugin)
source $ZSH/oh-my-zsh.sh



eval $(thefuck --alias)
source <(kubectl completion zsh)
export PATH="/opt/homebrew/opt/libpq/bin:$PATH"

source ~/.secrets.sh

source ~/.asdf/plugins/java/set-java-home.zsh



alias kc=kubectl

 export PATH="/usr/local/lib/docker/cli-plugins:$PATH"
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
