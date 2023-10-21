{
  description = "Home Manager configuration of charlesstein";

  inputs = {
    # Specify the source of Home Manager and Nixpkgs.
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    ohMyTmux = {
      url = "github:gpakosz/.tmux";
      flake = false;
    };
    dotfiles = {
      url = "path:///home/charlesstein/personal/dotfiles";
      flake = false;
    };

    zshautosuggestions = {
      url = "github:zsh-users/zsh-autosuggestions";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, home-manager,  ... }@inputs: let
      inherit (self) outputs;
    in {
      nixosConfigurations = {
	      ubuntu = nixpkgs.lib.nixosSystem {
		specialArgs = {inherit inputs outputs;};
		# > Our main nixos configuration file <
		modules = [./ubuntu/configuration.nix];
	      };

	      nixos = nixpkgs.lib.nixosSystem {
		specialArgs = {inherit inputs outputs;};
		# > Our main nixos configuration file <
		modules = [
		  ./nixos/configuration.nix
		];
	      };
	    };
      homeConfigurations."charlesstein" = home-manager.lib.homeManagerConfiguration {

	pkgs = nixpkgs.legacyPackages.x86_64-linux; # Home-manager requires 'pkgs' instance
        extraSpecialArgs = {inherit inputs outputs;};
        # Specify your home configuration modules here, for example,
        # the path to your home.nix.
        modules = [
          ./home.nix
          ./de.nix
	  ./zsh.nix
	];

      };
      environment.shells = with nixpkgs; [ zsh ];
      users.defaultUserShell = nixpkgs.zsh;
      users.users.charlesstein.shell = nixpkgs.zsh;
    };
}
