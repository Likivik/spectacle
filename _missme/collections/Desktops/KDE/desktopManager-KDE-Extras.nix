{
  pkgs,
  lib,
  inputs,
  ...
}:

{
  # Darkly https://github.com/Bali10050/Darkly/issues
  # environment.systemPackages = with pkgs; [
  #   darkly-qt5
  #   darkly
  # ];
  # qt.platformTheme = "qt5ct";

  environment.systemPackages = [

    #### Kwin Effects
    # inputs.kwin-effects-forceblur.packages.${pkgs.system}.default # 
    # kwin-effects-glass https://github.com/4v3ngR/kwin-effects-glass
    
    ##### Widgets
    pkgs.plasma-panel-colorizer
  ];

}
