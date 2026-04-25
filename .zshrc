export ZHOME=$HOME/.config/zsh
. "$HOME/.config/zsh/zsh_functions.zsh"

export HISTFILE=$HOME/.zsh_history
HISTSIZE=1000
SAVEHIST=1000
setopt appendhistory
export FZF_DEFAULT_COMMAND="find . -type f -not -path .git   -not -path \"\*/bin/\*\" -not -path \"\*/build/\*\" -not -path \"\*/node_modules/\*\" -prune"

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

# Plugins (zsh-syntax-highlighting must be loaded last; see below)
zsh_add_plugin "zsh-users/zsh-autosuggestions"
zsh_add_plugin "unixorn/fzf-zsh-plugin"

# Fix vi mode copy not using system clipboard
zsh_add_plugin "kutsan/zsh-system-clipboard"
typeset -g ZSH_SYSTEM_CLIPBOARD_TMUX_SUPPORT='true'

# -C: skip compaudit for speed; still use a dump file. Delete ~/.zcompdump if completion acts stale.
compinit -C -d "${ZDOTDIR:-$HOME}/.zcompdump"

zsh_add_file zsh_completions.zsh
source ~/.secrets.sh

# Optional: work / machine zsh: $DOTFILES_ROOT/private/init.zsh (e.g. private submodule). Template: config/zsh/private.init.zsh.example
: "${DOTFILES_ROOT:=$HOME/personal/dotfiles}"
[[ -f "$DOTFILES_ROOT/private/init.zsh" ]] && . "$DOTFILES_ROOT/private/init.zsh"

export EDITOR=nvim
# Do not clobber AWS_PROFILE from secrets / private; default only if unset
export AWS_PROFILE="${AWS_PROFILE:-dev}"

if [[ "$OSTYPE" == "darwin"* ]]; then
	zsh_add_file zsh_path_mac.zsh
else
	zsh_add_file zsh_path_linux.zsh
fi

if [[ -f /proc/version ]] && grep -qEi "(Microsoft|WSL)" /proc/version &> /dev/null ; then
	zsh_add_file zsh_wsl.zsh
fi

[[ -f "$HOME/.local/bin/env" ]] && . "$HOME/.local/bin/env"
export PATH="${HOME}/.opencode/bin:${PATH}"

#THIS MUST BE AT THE END OF THE FILE FOR SDKMAN TO WORK!!!
export SDKMAN_DIR="$HOME/.sdkman"
[[ -s "$HOME/.sdkman/bin/sdkman-init.sh" ]] && source "$HOME/.sdkman/bin/sdkman-init.sh"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

zsh_add_plugin "zsh-users/zsh-syntax-highlighting"
