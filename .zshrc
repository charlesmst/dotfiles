export ZHOME=$HOME/.config/zsh
. "$HOME/.config/zsh/zsh_functions.zsh"

export HISTFILE=$HOME/.zsh_history
HISTSIZE=1000
SAVEHIST=1000
setopt appendhistory
export FZF_DEFAULT_COMMAND="find . -type f -not -path .git   -not -path \"*/bin/*\" -not -path \"*/build/*\" -not -path \"*/node_modules/*\" -prune"

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

zsh_add_file zsh_alias.zsh

# Plugins
zsh_add_plugin "zsh-users/zsh-autosuggestions"
zsh_add_plugin "zsh-users/zsh-syntax-highlighting"
zsh_add_plugin "unixorn/fzf-zsh-plugin"

compinit

zsh_add_file zsh_completions.zsh
source ~/.secrets.sh

eval $(thefuck --alias)

source ~/.asdf/plugins/java/set-java-home.zsh

export EDITOR=nvim
export AWS_PROFILE=dev

if [[ "$OSTYPE" == "darwin"* ]]; then
	zsh_add_file zsh_path_mac.zsh
else
	zsh_add_file zsh_path_linux.zsh
fi

