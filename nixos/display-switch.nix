{  pkgs, displaySwitch, system,  ... }:
{

  environment.systemPackages =  [
    displaySwitch.packages.x86_64-linux.display_switch
  ];
  systemd.user.services.display_switch = {
    enable = true;
    description = "Display switch via USB switch";
    unitConfig = {
      Type = "simple";
    };
    serviceConfig = {
      ExecStart = "${displaySwitch.packages.x86_64-linux.display_switch}/bin/display_switch";
    };
    wantedBy = [ "default.target" ];
  };
}
