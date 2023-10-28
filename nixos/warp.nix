
{ config, lib, pkgs, user, ... }:

{
  # Cloudfare WARP
  # PR: https://github.com/NixOS/nixpkgs/pull/168092
  # Issue: https://discourse.nixos.org/t/cant-start-cloudflare-warp-cli/23267
  imports = [
    ./warp/cloudflare-warp.nix
  ];
  services = {
    cloudflare-warp = {
      enable = true;
      certificate = "/home/charlesstein/Cloudflare_CA.crt";
    };
  };

}
