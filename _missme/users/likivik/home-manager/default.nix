{
  pkgs,
  config,
  inputs,
  system,
  nur,
  ...
}:

{

  home.sessionVariables.NIXOS_OZONE_WL = "1";

  home.packages = with pkgs; [
    #Tastings
    solaar
    # FileSync ---------------------------------------------------------------------------------------
    nextcloud-client

    # Office/basic files manipulation --------------------------------------------------------------------------------
    libreoffice-qt6-fresh # office suite
    hunspell # spellcheck engine
    hyphenDicts.ru_RU
    hunspellDicts.ru_RU # spellcheck library
    hyphenDicts.en_US
    hunspellDicts.en_US

    # PDF viewer
    evince # PDF viewer
    pdfarranger # arrange/combine/extract pages from pdf files
    ghostscript # convert jpg to pdf

    # Browser --------------------------------------------------------------------------------
    typora
    obsidian
    zettlr

    joplin-desktop


    # Browser Add-ons
    firefoxpwa # pwa for firefox based browser (needs extension also)

    # Password Management --------------------------------------------------------------------------------
    #bitwarden-desktop
    bws

    # Communications --------------------------------------------------------------------------------
    # Telegram
    telegram-desktop
    zapzap
    # Whatsapp
    # whatsapp-for-linux
    # Element/Matrix
    #element-desktop

    # Email\
    #snappymail #wtf
    #lumail
    #deltachat-desktop
    #claws-mail
    # bluemail
    # mailspring
    evolution # in evaluation
    # geary
    # thunderbird
    #kdePackages.kmail
    #kdePackages.kmail-account-wizard

    # Media --------------------------------------------------------------------------------
    # Images
    qimgv # main image viewer
    qview # backup image viewer
    # Image Editors
    krita
    inkscape-with-extensions
    # Video
    haruna # video-player (QT)
    celluloid # video-player (GTK)
    # Video Editors
    losslesscut-bin # video editor
    # Music
    pear-desktop

    # System Information and Administration --------------------------------------------------------------------------------
    # Learning this
    netdata

    # GUI
    hardinfo2 # Information on hardware + benchmarking tool, AIDA64 like
    gnome-disk-utility # Disk/Partition Management
    pkgs.gnome-software

    # Command Line
    lshw # Information on hardware
    pciutils # provides `lspci`
    smartmontools # SMART report

    # Dev / Config / Terminal Tools --------------------------------------------------------------------------------
    # Terminal Tools
    git
    git-extras
    wget
    nix-index

    # Code Editors


    micro
    nixfmt
    nil

    # Terminal
    (blackbox-terminal.overrideAttrs { sixelSupport = true; })
    # blackbox-terminal


    # Other
    steam-run
    qbittorrent
    contrast # Colorpicker - only one I found that works with wayland on kde6

    gnome-boxes

    lite-xl

    vscodium

    via

  ];



  programs.ssh.extraConfig =
''
Host *
  AddKeysToAgent yes
  IdentityFile /home/likivik/.ssh/id_ed25519

Host *
  AddKeysToAgent yes
  IdentityFile /home/likivik/.ssh/id_rsa

Host *
  AddKeysToAgent yes
  IdentityFile /home/likivik/.ssh/id_serenityOne2023-09-01

'';



  ### Firefox #####################






  programs.zsh = {
    enable = true;

    enableCompletion = true;
    syntaxHighlighting.enable = true;
    enableVteIntegration = true; # Blackbox and Gnome terminal use it at least, maybe others
    history.extended = true; # Save timestamp into the history file.
    autocd = true; # Automatically enter into a directory if typed directly into shell.

    initContent = ''
      ${builtins.readFile ./zsh/.zshrc}
      ${builtins.readFile ./zsh/.p10k-color.zsh}
    '';

    antidote = {
      enable = true;
      useFriendlyNames = true;
      plugins = [
        ''
          ${builtins.readFile ./zsh/.zsh_plugins.txt}
        ''
      ];
    };

  };

  programs.bash = {
    enable = true;
    enableCompletion = true;
    enableVteIntegration = true;
    shellAliases = {
      ll = "ls -l";
      ".." = "cd ..";
    };
    # initExtra = ''
    #   ssh-add /home/likivik/.ssh/id_rsa
    #   cdl ()
    #   {
    #     cd "$(dirname "$(readlink "$1")")";
    #   }
    #   eval "$(starship init bash)"
    # '';
  };

  # programs.zellij =
  # {
  #   enable = true;
  #   enableZshIntegration = true;
  #   enableBashIntegration = true;
  #   settings =
  #   {
  #     #theme = "custom";
  #     #themes.custom.fg = "#ffffff"; ###
  #   };
  # };





}
