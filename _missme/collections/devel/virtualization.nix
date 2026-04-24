{ pkgs, ... }:

{
  virtualisation.libvirtd = {
    enable = true;

    # Enable TPM emulation (for Windows 11)
    qemu = {
      swtpm.enable = true;
      
    };

  };

  # Enable USB redirection
  virtualisation.spiceUSBRedirection.enable = true;

  # Allow VM management
  users.groups.libvirtd.members = [ "likivik" ];
  users.groups.kvm.members = [ "likivik" ];



  environment.systemPackages = with pkgs; [ 
    virt-manager
    gnome-boxes # VM management
    dnsmasq # VM networking
    phodav # (optional) Share files with guest VMs
  ];  
  
# programs = {
#   nix-ld = {
#     enable = true;
#     # put whatever libraries you think you might need
#     # nix-ld includes a strong sane-default as well
#     # in addition to these
#     libraries = with pkgs; [
# stdenv.cc.cc
#     openssl
#     xorg.libXcomposite
#     xorg.libXtst
#     xorg.libXrandr
#     xorg.libXext
#     xorg.libX11
#     xorg.libXfixes
#     libGL
#     libva
#     pipewire
#     xorg.libxcb
#     xorg.libXdamage
#     xorg.libxshmfence
#     xorg.libXxf86vm
#     libelf
    
#     # Required
#     glib
#     gtk2
#     bzip2
    
#     # Without these it silently fails
#     xorg.libXinerama
#     xorg.libXcursor
#     xorg.libXrender
#     xorg.libXScrnSaver
#     xorg.libXi
#     xorg.libSM
#     xorg.libICE
#     gnome2.GConf
#     nspr
#     nss
#     cups
#     libcap
#     SDL2
#     libusb1
#     dbus-glib
#     ffmpeg
#     # Only libraries are needed from those two
#     libudev0-shim
    
#     # Verified games requirements
#     xorg.libXt
#     xorg.libXmu
#     libogg
#     libvorbis
#     SDL
#     SDL2_image
#     glew110
#     libidn
#     tbb
    
#     # Other things from runtime
#     flac
#     freeglut
#     libjpeg
#     libpng
#     libpng12
#     libsamplerate
#     libmikmod
#     libtheora
#     libtiff
#     pixman
#     speex
#     SDL_image
#     #SDL_ttf
#     SDL_mixer
#     SDL2_ttf
#     SDL2_mixer
#     libappindicator-gtk2
#     libdbusmenu-gtk2
#     libindicator-gtk2
#     libcaca
#     libcanberra
#     libgcrypt
#     libvpx
#     librsvg
#     xorg.libXft
#     libvdpau
#     pango
#     cairo
#     atk
#     gdk-pixbuf
#     fontconfig
#     freetype
#     dbus
#     alsa-lib
#     expat
#     # Needed for electron
#     libdrm
#     mesa
#     libxkbcommon
#     ];
#   };
# };

services = {
  envfs = {
    enable = true;
  };
};


 

}