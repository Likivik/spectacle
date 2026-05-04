{ inputs, den, ... }:
{
  den.aspects.virtualization = {
    nixos = { config, pkgs, ... }: {
      virtualisation.libvirtd = {
        enable = true;
        qemu = {
          swtpm.enable = true;
        };
      };

      virtualisation.spiceUSBRedirection.enable = true;

      users.groups.libvirtd.members = [ "likivik" ];
      users.groups.kvm.members = [ "likivik" ];

      environment.systemPackages = with pkgs; [
        virt-manager
        gnome-boxes
        dnsmasq
        phodav
      ];

      services.envfs.enable = true;
    };
  };
}