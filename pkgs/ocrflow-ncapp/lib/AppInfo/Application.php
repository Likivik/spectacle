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
        // Nothing needed at boot; FileActions are registered client-side (js/ocr-action.js).
    }
}
