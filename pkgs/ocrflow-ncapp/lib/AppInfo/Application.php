<?php
/**
 * OCR Flow — Nextcloud app bootstrap.
 *
 * Loads the Files context-menu action JS via Util::addInitScript — the
 * documented NC 28+ method for file-action scripts, which runs right after
 * the core scripts and immediately before the Files app mounts. Per bug
 * nextcloud/server#56020 + the upgrade guide, file actions registered
 * outside an init script are loaded unreliably (randomly missing on first
 * page load). We serve the script from a ROUTE (see PageController), because
 * under NixOS services.nextcloud.extraApps the static /apps/<app>/js/* path
 * 404s while routes resolve.
 */
namespace OCA\OcrFlow\AppInfo;

use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;
use OCP\Util;

class Application extends App implements IBootstrap {
    public const APP_ID = 'ocrflow';

    public function __construct(array $urlParams = []) {
        parent::__construct(self::APP_ID, $urlParams);
    }

    public function register(IRegistrationContext $context): void {
        // Admin settings section is registered declaratively in
        // appinfo/info.xml (<settings><admin>...</admin></settings>).
        // Nothing else to register here — the action JS is loaded in boot().
    }

    public function boot(IBootContext $context): void {
        // Loads the Files context-menu action JS. addInitScript runs the
        // script in the front-end init phase, before the Files app mounts —
        // the reliable path for file-action registration (avoids the random
        // missing-action race of addScript-loaded scripts, nextcloud/server#56020).
        // The file js/ocr-action.js is shipped with the app and served from
        // the extraApps store path. (JSResourceLocator resolves init scripts
        // to static files under the app's js/ dir, so the name here MUST match
        // the on-disk file — there is no route indirection.)
        Util::addInitScript('ocrflow', 'ocr-action');
    }
}