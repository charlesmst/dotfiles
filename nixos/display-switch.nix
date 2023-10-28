{  pkgs, displaySwitch, system,  ... }:
{

  environment.systemPackages =  [
    displaySwitch.packages.x86_64-linux.display_switch
  ];
systemd.services.foo = {
    enable = true;
    description = "bar";
    unitConfig = {
      Type = "simple";
      # ...
    };
    serviceConfig = {
      ExecStart = "${foo}/bin/foo";
      # ...
    };
    wantedBy = [ "multi-user.target" ];
    # ...
  };
}
