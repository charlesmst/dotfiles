

{  pkgs, home, inputs,   ... }:
{
  home.file = {
    ".config/display-switch/display-switch.ini".text = ''
        usb_device = "046d:0843"
        on_usb_connect = "DisplayPort1"
        on_usb_disconnect = "Hdmi1"
    '';
  };

}
