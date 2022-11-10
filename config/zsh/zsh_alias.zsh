#!/bin/zsh

alias kc=kubectl
alias vim=nvim
alias idea="\$IDEA"
alias psql="pgcli"
alias lg="lazygit"
alias ld="lazydocker"
alias ls="ls --color"
alias ts="~/personal/dotfiles/tmux/tmux-sessionizer.sh"
alias history="history 1"
alias fdocker="docker kill $(docker ps -qa) ; docker rm $(docker ps -qa)"

function kclogs(){
    if [[ -z "$1" ]]; then
        selected=`kubectl get pods --no-headers | fzf | awk '{print $1}'`
    else
        selected=`kubectl get po -l app=$1 -o name `
    fi
    echo "selected pod $selected"

    kubectl logs $selected -f --tail=500
}


function kcbash(){
    if [[ -z "$1" ]]; then
        selected=`kubectl get pods --no-headers | fzf | awk '{print $1}'`
    else
        selected=`kubectl get po -l app=$1 -o name `
    fi
    echo "selected pod $selected"

    kubectl exec -it $selected bash
}
