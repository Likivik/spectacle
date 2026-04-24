{ pkgs, lib, ... }:

{

  # KDE PLASMA
  services.desktopManager.plasma6 = {
    enable = true;
  };

  # KDE Software
  # Exclude optional
  environment.plasma6.excludePackages = with pkgs.kdePackages; [
    # exclude Optional packages
    konsole # you know
    elisa # music player
    gwenview # i hate this image viewer
    kate # never use it
    khelpcenter # never used help in kde
  ];

  # Include for proper desktop experience
  environment.systemPackages =
    (with pkgs; [
      ocs-url # to install kde plugins from the site
      plasma-panel-spacer-extended # extension picks up kwin6 properly this way
      easyeffects #equalizer
    ])
    ++ (with pkgs.kdePackages; [
      filelight # Quickly visualize your disk space usage
      ksystemlog # KDE SystemLog Application
      sddm-kcm # sddm settings gui - only background setting works, nothing else.
      qtmultimedia # needed for some widgets
      # qtstyleplugin-kvantum
      kcharselect
    ]);

  programs.kdeconnect.enable = true;

}
