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
        close = [ "<Super>q" "<Alt>F4" ];
        maximize = [];
        minimize = [ "<Super>comma" ];
        move-to-monitor-down = [];
        move-to-monitor-left = [ "<Shift><Control><Alt>e" ];
        move-to-monitor-right = [ "<Shift><Control><Alt>r" ];
        move-to-monitor-up = [];
        move-to-workspace-1 = [ "<Control><Shift><Alt>1" ];
        move-to-workspace-2 = [ "<Control><Shift><Alt>2" ];
        move-to-workspace-3 = [ "<Control><Shift><Alt>3" ];
        move-to-workspace-4 = [ "<Control><Shift><Alt>4" ];
        move-to-workspace-5 = [ "<Control><Shift><Alt>5" ];
        move-to-workspace-6 = [ "<Control><Shift><Alt>6" ];
        move-to-workspace-7 = [ "<Control><Shift><Alt>7" ];
        move-to-workspace-8 = [ "<Control><Shift><Alt>8" ];
        move-to-workspace-9 = [ "<Control><Shift><Alt>9" ];
        move-to-workspace-down = [];
        move-to-workspace-up = [];
        switch-applications = [ "<Shift><Alt>w" ];
        switch-applications-backward = [ "<Alt>w" ];
        switch-input-source = [ "F2" ];
        switch-input-source-backward = [ "<Shift>F2" ];
        switch-to-workspace-1 = [ "<Shift><Alt>1" ];
        switch-to-workspace-2 = [ "<Shift><Alt>2" ];
        switch-to-workspace-3 = [ "<Shift><Alt>3" ];
        switch-to-workspace-4 = [ "<Shift><Alt>4" ];
        switch-to-workspace-5 = [ "<Shift><Alt>5" ];
        switch-to-workspace-6 = [ "<Shift><Alt>6" ];
        switch-to-workspace-7 = [ "<Shift><Alt>7" ];
        switch-to-workspace-8 = [ "<Shift><Alt>8" ];
        switch-to-workspace-9 = [ "<Shift><Alt>9" ];
        switch-to-workspace-down = [ "<Primary><Super>Down" "<Primary><Super>j" ];
        switch-to-workspace-left = [];
        switch-to-workspace-right = [];
        switch-to-workspace-up = [ "<Primary><Super>Up" "<Primary><Super>k" ];
        switch-windows = [ "<Alt>Tab" ];
        switch-windows-backward = [ "<Shift><Alt>Tab" ];
        toggle-maximized = [ "<Super>m" ];
        unmaximize = [];
      };

      "org/gnome/desktop/wm/preferences" = {
        auto-raise = false;
        button-layout = "appmenu:close";
        disable-workarounds = true;
        focus-mode = "sloppy";
        focus-new-windows = "strict";
        num-workspaces = 9;
      };


      # "org/gnome/desktop/wm/keybindings" = {
      #   switch-input-source = [ "f2,XF86Keyboard" ];
      # };
      "org/gnome/mutter" = {
        dynamic-workspaces = "false";
        workspaces-only-on-primary = true;
      };
      "org/gnome/shell/app-switcher" = {
        current-workspace-only = true;
      };

      "org/gnome/settings-daemon/plugins/media-keys" = {
        screensaver = [ "<Super>Escape" ];
        search = [ "<Super>space" ];
        terminal = [ "<Super>t" ];
      };

      "org/gnome/shell" = {
        command-history = [ "r" "lg" ];
        disable-user-extensions = false;
        enabled-extensions = [ "noannoyance@daase.net" "caffeine@patapon.info" "focusprimaryscreen@charles" "auto-move-windows@gnome-shell-extensions.gcampax.github.com" "user-theme@gnome-shell-extensions.gcampax.github.com" "trayIconsReloaded@selfmade.pl" "native-window-placement@gnome-shell-extensions.gcampax.github.com" "focus-follows-workspace@christopher.luebbemeier.gmail.com" "Vitals@CoreCoding.com" ];
        # looking-glass-history = [ "wmclass" "r" "r(1)" "r(1).wmclass" "exit" "a = r(7)" "awindow" "a.window" "a.windows" "lg" "a" "a.wmclass" ];
        # welcome-dialog-last-shown-version = "42.3.1";
      };

      "org/gnome/shell/extensions/auto-move-windows" = {
        application-list = [ "brave-browser.desktop:1" "slack.desktop:2" "postman.desktop:3" "jetbrains-idea.desktop:3" "org.gnome.Terminal.desktop:4" "spotify.desktop:6" "docker-desktop.desktop:6" "Alacritty.desktop:4" "1password.desktop:6" "bitwarden.desktop:6" "com.google.Chrome.desktop:5" ];
      };

      "org/gnome/shell/extensions/caffeine" = {
        indicator-position = 0;
        indicator-position-index = 0;
        indicator-position-max = 2;
        restore-state = true;
        show-indicator = "always";
        toggle-state = true;
        user-enabled = true;
      };

      "org/gnome/shell/extensions/trayIconsReloaded" = {
        icon-margin-horizontal = 5;
        icon-margin-vertical = 0;
        icon-padding-horizontal = 1;
        icon-padding-vertical = 0;
        icon-size = 16;
        icons-limit = 8;
        invoke-to-workspace = false;
        tray-margin-left = 0;
      };

      "org/gnome/shell/extensions/vitals" = {
        hot-sensors = [ "_memory_usage_" "_temperature_amdgpu_junction_" "_temperature_k10temp_tctl_" "_processor_usage_" ];
      };
   };
}
