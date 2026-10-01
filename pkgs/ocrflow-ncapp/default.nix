# Package the OCR Flow Nextcloud app.
# services.nextcloud.extraApps expects a package whose store path IS the app
# directory (containing appinfo/info.xml), same shape as fetchNextcloudApp's
# applyPatches output.
#
# The Files context-menu action JS is BUNDLED with vite (frontend/,
# @nextcloud/vite-config): NC 34 file actions register via
# `import { registerFileAction } from '@nextcloud/files'`, which only resolves
# inside a bundler — a raw browser ESM throws "Failed to resolve module
# specifier". The bundle is emitted as js/ocrflow-main.mjs and loaded by
# Util::addInitScript('ocrflow', 'ocrflow-main') in lib/AppInfo/Application.php.
{
  lib,
  buildNpmPackage,
  runCommand,
  copyPathToStore ? null,
}:

let
  frontend = buildNpmPackage {
    pname = "ocrflow-frontend";
    version = "0.3.0";
    src = ./frontend;
    npmDepsHash = "sha256-TX+Zn1gNj/gzaHFCcvWsabK5We3tIS1NQCrph9LKkLU=";
    installPhase = ''
      runHook preInstall
      mkdir -p $out/js
      cp -r js $out/
      runHook postInstall
    '';
  };
in
runCommand "nextcloud-app-ocrflow-0.3.0" { } ''
  mkdir -p $out
  cp -r ${./appinfo} $out/appinfo
  cp -r ${./lib} $out/lib
  cp -r ${./l10n} $out/l10n
  cp -r ${frontend}/js $out/js
''