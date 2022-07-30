export ZDOTDIR=$HOME/.config/zsh
. "$HOME/.config/zsh/zsh_functions.zsh"

setopt autocd extendedglob nomatch menucomplete
setopt interactive_comments
stty stop undef		# Disable ctrl-s to freeze terminal.
zle_highlight=('paste:none')

# beeping is annoying
unsetopt BEEP

# completions
autoload -Uz compinit
zstyle ':completion:*' menu select
# zstyle ':completion::complete:lsof:*' menu yes select
zmodload zsh/complist
# compinit
_comp_options+=(globdots)		# Include hidden files.

autoload -U up-line-or-beginning-search
autoload -U down-line-or-beginning-search
zle -N up-line-or-beginning-search
zle -N down-line-or-beginning-search

# Colors
autoload -Uz colors && colors
zsh_add_file zsh_prompt.zsh
zsh_add_file zsh_vi_mode.zsh

# Plugins
zsh_add_plugin "zsh-users/zsh-autosuggestions"
zsh_add_plugin "zsh-users/zsh-syntax-highlighting"
zsh_add_plugin "unixorn/fzf-zsh-plugin"

compinit

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

