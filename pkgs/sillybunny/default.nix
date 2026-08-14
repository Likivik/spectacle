{ pkgs, ... }:

pkgs.buildNpmPackage (finalAttrs: {
  pname = "sillybunny";
  version = "1.7.0";

  src = pkgs.fetchFromGitHub {
    owner = "SillyBunnyTeam";
    repo = "SillyBunny";
    tag = finalAttrs.version;
    hash = "sha256-SC/h8xjHyincX1E+KjBaZSCd4EqOOLP1epw6WnXPbxo=";
  };
  npmDepsHash = "sha256-3DU7NLllSDQpvu4qrGaVW6KKLNNK6FwGwD/MBxNnoVk=";

  dontNpmBuild = true;

  postInstall = ''
    mkdir -p $out/lib/node_modules/sillybunny/{backups,public/scripts/extensions/third-party}
  '';

  meta = {
    description = "Mobile-friendly SillyTavern fork (Bun runtime, custom navigation shell, mobile-first layout)";
    longDescription = ''
      SillyBunny is a community-driven fork of SillyTavern focused on mobile
      experience. Built on Bun for fast startup, ships with a custom navigation
      shell, mobile-first responsive layout, and bundled mobile-friendly
      extensions.
    '';
    homepage = "https://github.com/SillyBunnyTeam/SillyBunny";
    downloadPage = "https://github.com/SillyBunnyTeam/SillyBunny/releases";
    license = pkgs.lib.licenses.agpl3Only;
    mainProgram = "sillybunny";
  };
})
