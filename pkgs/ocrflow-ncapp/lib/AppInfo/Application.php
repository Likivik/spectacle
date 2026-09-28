<?php
/**
 * OCR Flow — Nextcloud app bootstrap.
 *
 * Loads the Files context-menu action JS. We inject it via the
 * LoadAdditionalScriptsEvent (the pattern Nextcloud's own files_reminders /
 * files_lock apps use) pointing at a ROUTE we serve (PageController), because
 * under NixOS services.nextcloud.extraApps the static /apps/<app>/js/* path
 * 404s while routes resolve.
 */
namespace OCA\OcrFlow\AppInfo;

use OCA\Files\Event\LoadAdditionalScriptsEvent;
use OCA\OcrFlow\Listener\LoadAdditionalScriptsListener;
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
        // Load the Files context-menu actions when the Files page renders
        // (same event files_reminders/files_lock listen to).
        $context->registerEventListener(
            LoadAdditionalScriptsEvent::class,
            LoadAdditionalScriptsListener::class
        );
    }

    public function boot(IBootContext $context): void {
        // Nothing needed at boot; the FileActions JS is injected via
        // LoadAdditionalScriptsEvent on the Files page.
    }
}