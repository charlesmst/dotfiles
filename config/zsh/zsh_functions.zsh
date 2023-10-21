#!/bin/zsh
ZHOMECUSTOM="$HOME/.zsh"
# Function to source files if they exist
function zsh_add_file() {
    [ -f "$ZHOME/$1" ] && source "$ZHOME/$1"
}

function zsh_add_file_plugin() {
    [ -f "$ZHOMECUSTOM/$1" ] && source "$ZHOMECUSTOM/$1"
}

function zsh_add_plugin() {
    PLUGIN_NAME=$(echo $1 | cut -d "/" -f 2)
    if [ -d "$ZHOMECUSTOM/plugins/$PLUGIN_NAME" ]; then 
        # For plugins
        zsh_add_file_plugin "plugins/$PLUGIN_NAME/$PLUGIN_NAME.plugin.zsh" || \
        zsh_add_file_plugin "plugins/$PLUGIN_NAME/$PLUGIN_NAME.zsh"
    else
        git clone "https://github.com/$1.git" "$ZHOMECUSTOM/plugins/$PLUGIN_NAME"
    fi
}

function zsh_add_completion() {
    PLUGIN_NAME=$(echo $1 | cut -d "/" -f 2)
    if [ -d "$ZHOMECUSTOM/plugins/$PLUGIN_NAME" ]; then 
        # For completions
		completion_file_path=$(ls $ZHOMECUSTOM/plugins/$PLUGIN_NAME/_*)
		fpath+="$(dirname "${completion_file_path}")"
        zsh_add_file "plugins/$PLUGIN_NAME/$PLUGIN_NAME.plugin.zsh"
    else
        git clone "https://github.com/$1.git" "$ZHOMECUSTOM/plugins/$PLUGIN_NAME"
		fpath+=$(ls $ZHOMECUSTOM/plugins/$PLUGIN_NAME/_*)
        [ -f $ZHOMECUSTOM/.zccompdump ] && $ZHOMECUSTOM/.zccompdump
    fi
	completion_file="$(basename "${completion_file_path}")"
	if [ "$2" = true ] && compinit "${completion_file:1}"
}

function mach_java_mode() {
    #THIS MUST BE AT THE END OF THE FILE FOR SDKMAN TO WORK!!!
    export SDKMAN_DIR="$HOME/.sdkman"
    [[ -s "$HOME/.sdkman/bin/sdkman-init.sh" ]] && source "$HOME/.sdkman/bin/sdkman-init.sh"
}
