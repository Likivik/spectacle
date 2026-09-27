<?php
/**
 * OCR Flow — Nextcloud app bootstrap.
 *
 * Injects the Files context-menu action JS. We serve the script from a
 * ROUTE (see PageController::actionScript / GET /apps/ocrflow/action-script)
 * rather than a static file, because NixOS `services.nextcloud.extraApps`
 * mounts apps under the `/nix-apps` URL namespace: a static `/apps/<app>/js`
 * URL 404s for extraApps apps while a registered route resolves fine. Serving
 * via a route is hosting-agnostic (works on any NC install, not just NixOS).
 */
namespace OCA\OcrFlow\AppInfo;

use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;

class Application extends App implements IBootstrap {
    public const APP_ID = 'ocrflow';

    public function __construct(array $urlParams = []) {
        parent::__construct(self::APP_ID, $urlParams);
    }

    public function register(IRegistrationContext $context): void {
        // Admin settings section is registered declaratively in
        // appinfo/info.xml (<settings><admin>...</admin></settings>).
    }

    public function boot(IBootContext $context): void {
        // Load the Files context-menu action JS from a route-served script.
        \OCP\Util::addScript('ocrflow', 'action-script');
    }
}