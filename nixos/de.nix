{  pkgs,   ... }:
{


  home.packages = with pkgs; [
    gnomeExtensions.appindicator 
    gnomeExtensions.focus-follows-workspace 
    gnomeExtensions.vitals 
    gnomeExtensions.caffeine 
  ];
   dconf.settings = {
      "org/gnome/desktop/interface" = {
        color-scheme = "prefer-dark";
      };

      "org/gnome/desktop/wm/keybindings" = {
        move-to-workspace-9 = [ "<Control><Shift><Alt>9" ];
        move-to-workspace-8 = [ "<Control><Shift><Alt>8" ];
        move-to-workspace-7 = [ "<Control><Shift><Alt>7" ];
        move-to-workspace-6 = [ "<Control><Shift><Alt>6" ];
        move-to-workspace-5 = [ "<Control><Shift><Alt>5" ];
        move-to-workspace-4 = [ "<Control><Shift><Alt>4" ];
        move-to-workspace-3 = [ "<Control><Shift><Alt>3" ];
        move-to-workspace-2 = [ "<Control><Shift><Alt>2" ];
        move-to-workspace-1 = [ "<Control><Shift><Alt>1" ];

        switch-to-workspace-9 = [ "<Shift><Alt>9" ];
        switch-to-workspace-8 = [ "<Shift><Alt>8" ];
        switch-to-workspace-7 = [ "<Shift><Alt>7" ];
        switch-to-workspace-6 = [ "<Shift><Alt>6" ];
        switch-to-workspace-5 = [ "<Shift><Alt>5" ];
        switch-to-workspace-4 = [ "<Shift><Alt>4" ];
        switch-to-workspace-3 = [ "<Shift><Alt>3" ];
        switch-to-workspace-2 = [ "<Shift><Alt>2" ];
        switch-to-workspace-1 = [ "<Shift><Alt>1" ];
      };

      "org/gnome/desktop/wm/preferences" = {
        num-workspaces = 9;
      };


      "org/gnome/desktop/wm/keybindings" = {
        switch-input-source = [ "f2,XF86Keyboard" ];
      };
      "org/gnome/mutter" = {
        dynamic-workspaces = "false";
        workspaces-only-on-primary = true;
      };
      "org/gnome/shell/app-switcher" = {
        current-workspace-only = true;
      };
   };
}
