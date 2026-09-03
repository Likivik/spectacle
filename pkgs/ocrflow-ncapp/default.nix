# Package the OCR Flow Nextcloud app.
# services.nextcloud.extraApps expects a package whose store path IS the app
# directory (containing appinfo/info.xml), same shape as fetchNextcloudApp's
# applyPatches output.
{
  lib,
  runCommand,
  copyPathToStore ? null,
}:
runCommand "nextcloud-app-ocrflow-0.1.0" { } ''
  mkdir -p $out
  cp -r ${./appinfo} $out/appinfo
  cp -r ${./lib} $out/lib
  cp -r ${./js} $out/js
''
