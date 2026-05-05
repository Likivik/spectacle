# dynamically exposes a testing VM for every defined host.
# enables `nix run .#hostname` (e.g. nix run .#spectacle).
# instead of having to reboot each time.

{ inputs, den, ... }:
{
  # Dynamically configure tty-autologin for all hosts, but ONLY when running as a VM.
  # This prevents your real hardware from automatically logging in without a password!
  den.default.nixos = { config, lib, ... }: {
    virtualisation.vmVariant = {
      # We log into root first, then dynamically pivot to the requested user at runtime!
      services.getty.autologinUser = lib.mkForce "root";

      programs.bash.loginShellInit = ''
        if [ "$USER" = "root" ]; then
          for arg in $(cat /proc/cmdline 2>/dev/null || true); do
            if [[ "$arg" == autologin=* ]]; then
              target_user="''${arg#*=}"
              if [ -n "$target_user" ] && [ "$target_user" != "root" ]; then
                echo "🚀 Auto-switching to requested user: $target_user..."
                exec su - "$target_user"
              fi
            fi
          done
        fi
      '';
    };
  };

  perSystem =
    { pkgs, lib, system, ... }:
    let
      # Filter NixOS configurations that match the current system architecture
      hostsForSystem = lib.filterAttrs (_: conf: conf.pkgs.system == system) (inputs.self.nixosConfigurations or { });
    in
    {
      # Create a VM runner package for each matching host
      packages = lib.mapAttrs (name: conf:
        let
          normalUsers = lib.filterAttrs (n: v: v.isNormalUser) conf.config.users.users;
          userNames = lib.attrNames normalUsers;
          userNamesStr = lib.concatStringsSep ", " userNames;
          # Format string for bash array ("likivik" "salem")
          userNamesBashArray = lib.concatMapStringsSep " " (u: ''"${u}"'') userNames;
          defaultUser = if (lib.length userNames > 0) then lib.head userNames else "root";
        in
        pkgs.writeShellApplication {
          name = name;
          text = ''
            TARGET_USER="${defaultUser}"
            EXTRA_QEMU_ARGS=()

            # Parse command line arguments
            while [[ $# -gt 0 ]]; do
              case "$1" in
                -u|--user)
                  TARGET_USER="$2"
                  shift 2
                  ;;
                -l|--list|--list-users)
                  echo "Available users on ${name}: ${userNamesStr}, root"
                  exit 0
                  ;;
                -h|--help)
                  echo "Usage: nix run .#${name} -- [options]"
                  echo ""
                  echo "Options:"
                  echo "  -u, --user <user>   Log in as specific user (default: ${defaultUser})"
                  echo "  -l, --list          List available users for this host"
                  echo "  -h, --help          Show this help message"
                  echo ""
                  echo "Any other arguments will be passed directly to QEMU."
                  exit 0
                  ;;
                *)
                  EXTRA_QEMU_ARGS+=("$1")
                  shift
                  ;;
              esac
            done

            # Validate the user
            VALID_USERS=(${userNamesBashArray} "root")
            USER_IS_VALID=false
            for u in "''${VALID_USERS[@]}"; do
              if [ "$u" = "$TARGET_USER" ]; then
                USER_IS_VALID=true
                break
              fi
            done

            if [ "$USER_IS_VALID" = false ]; then
              echo "❌ Error: User '$TARGET_USER' not found on host '${name}'."
              echo "Available users: ${userNamesStr}, root"
              exit 1
            fi

            # Pass the target user to the VM via kernel arguments
            export QEMU_KERNEL_CMDLINE="''${QEMU_KERNEL_CMDLINE:-} autologin=$TARGET_USER"
            export QEMU_OPTS="-m 8192 ''${QEMU_OPTS:-}"

            echo "💻 Starting VM for ${name} (autologin: $TARGET_USER)..."

            # Launch the VM safely handling any extra QEMU arguments
            if [ ''${#EXTRA_QEMU_ARGS[@]} -gt 0 ]; then
              ${conf.config.system.build.vm}/bin/run-${conf.config.networking.hostName}-vm "''${EXTRA_QEMU_ARGS[@]}"
            else
              ${conf.config.system.build.vm}/bin/run-${conf.config.networking.hostName}-vm
            fi
          '';
        }
      ) hostsForSystem;
    };
}

/* ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

  How to use your new command:
  To see the help menu:
  
  nix run .#spectacle -- --help
  To discover which users are available for a specific host:

  nix run .#spectacle -- --list
  To log in as a specific user:

  nix run .#spectacle -- --user salem
  To run normally (logs into the primary user by default):

  nix run .#spectacle

  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ */