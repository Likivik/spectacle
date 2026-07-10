I think I want an alternative to mkOutOfStoreSymlink. aka I want ~/.config/... files to link to my flake git repo, so that I can edit ~/.config/... files with gui and have them change in git repo itself


Method 1: The Native nix-maid Solution (Cleanest)If you use nix-maid, you do not need any external plugins. When you pass a string literal (wrapped in quotes) instead of a direct file path to the .source property, nix-maid passes it to systemd as a plain string. It evaluates dynamically to point exactly to your mutable local Git repository rather than copying it to /nix/store.nix# In your nix-maid configuration
file.home = {
  # 1. Links ~/.config/kitty/kitty.conf directly to your Git repository file
  ".config/kitty/kitty.conf".source = "{{home}}/src/my-nix-flake/dotfiles/kitty.conf";

  # 2. You can also link entire directories at once
  ".config/nvim".source = "{{home}}/src/my-nix-flake/dotfiles/nvim";
};

How it works: nix-maid generates a standard symbolic link pointing directly to ~/src/my-nix-flake/....The GUI Experience: You can open your GUI editor to ~/.config/kitty/kitty.conf, hit save, and the physical changes instantly modify your Git repo file, ready to be committed.