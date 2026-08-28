{
  buildFeatures ? [ ],
  buildNoDefaultFeatures ? false,
  buildPackages,
  fetchFromGitHub,
  installManPages ? stdenv.buildPlatform.canExecute stdenv.hostPlatform,
  installShellCompletions ? stdenv.buildPlatform.canExecute stdenv.hostPlatform,
  installShellFiles,
  lib,
  openssl,
  pkg-config,
  rustPlatform,
  stdenv,
}:

# Same as nixpkgs pkgs/by-name/hi/himalaya/package.nix, pinned to 2.1.0 (nixpkgs
# ships 2.0.0, which dies mid-exchange with `Resource temporarily unavailable`
# / EAGAIN on slow ops — large APPEND / slow AUTH — himalaya #731/#732).
# 2.1.0 ships the pimalaya-stream transport retry.
let
  version = "2.1.0";
  hash = "sha256-m+eJqHJ9tTHP6dqHyjDxe/fexoEX736Qs8KcrnCqku8=";
  cargoHash = "sha256-aBNgXnAjyNYe3FHQ5GhHek5OMWyc3+6h/CIg9qXejYU=";

  withOpenssl = stdenv.hostPlatform.isLinux && builtins.elem "native-tls" buildFeatures;
  emulator = stdenv.hostPlatform.emulator buildPackages;
  exe = stdenv.hostPlatform.extensions.executable;

in
rustPlatform.buildRustPackage {
  inherit
    version
    cargoHash
    buildFeatures
    buildNoDefaultFeatures
    ;

  pname = "himalaya";

  src = fetchFromGitHub {
    inherit hash;
    owner = "pimalaya";
    repo = "himalaya";
    rev = "v${version}";
  };

  env.OPENSSL_NO_VENDOR = 1;

  nativeBuildInputs = [
    pkg-config
    installShellFiles
  ];

  buildInputs = lib.optional withOpenssl openssl;

  postInstall =
    lib.optionalString (lib.hasInfix "wine" emulator) ''
      export WINEPREFIX="''${WINEPREFIX:-$(mktemp -d)}"
      mkdir -p $WINEPREFIX
    ''
    + ''
      mkdir -p $out/share/{completions,man,schemas}
      ${emulator} "$out"/bin/himalaya${exe} completion -d "$out"/share/completions bash elvish fish powershell zsh
      ${emulator} "$out"/bin/himalaya${exe} manual "$out"/share/man
      ${emulator} "$out"/bin/himalaya${exe} json-schema "$out"/share/schemas
    ''
    + lib.optionalString installManPages ''
      installManPage "$out"/share/man/*
    ''
    + lib.optionalString installShellCompletions ''
      installShellCompletion --cmd himalaya \
        --bash "$out"/share/completions/himalaya.bash \
        --fish "$out"/share/completions/himalaya.fish \
        --zsh "$out"/share/completions/_himalaya
    '';

  meta = {
    description = "CLI to manage emails";
    mainProgram = "himalaya";
    homepage = "https://github.com/pimalaya/himalaya";
    changelog = "https://github.com/pimalaya/himalaya/blob/v${version}/CHANGELOG.md";
    license = with lib.licenses; [
      asl20
      mit
    ];
    maintainers = with lib.maintainers; [
      soywod
      yanganto
    ];
  };
}
