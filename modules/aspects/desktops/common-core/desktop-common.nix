{ den, ... }:
{
  # user aspect
  den.aspects.desktop-core = {
    includes = [

    ];

    homeManager =
      { pkgs, ... }:
      {
        home.sessionVariables.NIXOS_OZONE_WL = "1";
        programs.ssh.extraConfig = ''
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
      };

    # user can provide NixOS configurations
    # to any host it is included on
    nixos =
      { pkgs, ... }:
      {
        fonts.enableDefaultPackages = true; # Enable a basic set of fonts providing several styles and families and reasonable coverage of Unicode.
        services.tarsnap.enable = true;
        programs.thunderbird.enable = true;

        environment.systemPackages = with pkgs; [

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

        ];

      };
  };
}
