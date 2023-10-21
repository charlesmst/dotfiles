
{  pkgs, home, inputs,   ... }:
{
  home.file = {
    ".zshrc" = {
    	source = inputs.dotfiles + "/.zshrc";
    };
    ".config/zsh" = {
    	source = inputs.dotfiles + "/config/zsh";
    };
  };

  programs.zsh = {
    enable = true; 
    # pluginsDir = ".config/zsh/plugins";
    plugins = [
      {
	# will source zsh-autosuggestions.plugin.zsh
	name = "zsh-autosuggestions";
	src = pkgs.fetchFromGitHub {
	  owner = "zsh-users";
	  repo = "zsh-autosuggestions";
	  rev = "v0.4.0";
	  sha256 = "0z6i9wjjklb4lvr7zjhbphibsyx51psv50gm07mbb0kj9058j6kc";
	};
      }
      {
	name = "zsh-syntax-highlighting";
	src = pkgs.fetchFromGitHub {
	  owner = "zsh-users";
	  repo = "zsh-syntax-highlighting";
	  rev = "v0.7.1";
	  sha256 = "0z6i9wjjklb4lvr7zjhbphibsyx51psv50gm07mbb0kj9058j6kc";
	};
      }

      {
	name = "fzf-zsh-plugin";
	src = pkgs.fetchFromGitHub {
	  owner = "unixorn";
	  repo = "fzf-zsh-plugin";
	  rev = "43f0e1b7686113e9b0dcc108b120593f992dad4a";
	  sha256 = "TfTIPwF2DaJKmsj3QGG1tXoRJxM3If5yMEP2WAfQvhE=";
	};
      }

      {
	name = "zsh-system-clipboard";
	src = pkgs.fetchFromGitHub {
	  owner = "kutsan";
	  repo = "zsh-system-clipboard";
	  rev = "v0.8.0";
	  sha256 = "VWTEJGudlQlNwLOUfpo0fvh0MyA2DqV+aieNPx/WzSI=";
	};
      }
    ];
  };
}
