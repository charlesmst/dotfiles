{  pkgs,   ... }:
{


  home.packages = with pkgs; [
    gnomeExtensions.appindicator 
    gnomeExtensions.focus-follows-workspace 
    gnomeExtensions.vitals 
    gnomeExtensions.caffeine 
  ];
}
