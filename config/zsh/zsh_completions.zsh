#!/bin/zsh

# kubectl: cache completion; rebuild when kubectl binary is newer than the cache.
ZSH_KUBECTL_COMP_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/kubectl-completion.zsh"
if (( $+commands[kubectl] )); then
  _kubectl_path="$(command -v kubectl)"
  if [[ ! -f "$ZSH_KUBECTL_COMP_CACHE" || "$ZSH_KUBECTL_COMP_CACHE" -ot "$_kubectl_path" ]]; then
    mkdir -p "${ZSH_KUBECTL_COMP_CACHE:h}"
    command kubectl completion zsh >| "$ZSH_KUBECTL_COMP_CACHE" 2>/dev/null
  fi
  [[ -f "$ZSH_KUBECTL_COMP_CACHE" && -s "$ZSH_KUBECTL_COMP_CACHE" ]] && source "$ZSH_KUBECTL_COMP_CACHE"
  unset _kubectl_path
fi
unset ZSH_KUBECTL_COMP_CACHE
