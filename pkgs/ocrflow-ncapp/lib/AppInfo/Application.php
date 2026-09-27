<?php
/**
 * OCR Flow — Nextcloud app bootstrap.
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
        // IRegistrationContext has NO registerSetting() — calling it throws
        // "Call to undefined method" at bootstrap, spamming error.log on
        // every request. Nothing to do here.
    }

    public function boot(IBootContext $context): void {
        // Load the Files context-menu actions JS. Modern NC (28+) injects
        // app scripts server-side via Util::addScript — the <scripts> block
        // in info.xml is NOT honored for the Files Vue app (verified on
        // NC 34: actions silently never registered).
        \OCP\Util::addScript('ocrflow', 'ocr-action');
    }
}
