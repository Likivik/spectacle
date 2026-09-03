<?php
/**
 * OCR Flow — Nextcloud app bootstrap.
 */
namespace OCA\OcrFlow\AppInfo;

use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;
use OCA\OcrFlow\Settings\Admin;

class Application extends App implements IBootstrap {
    public const APP_ID = 'ocrflow';

    public function __construct(array $urlParams = []) {
        parent::__construct(self::APP_ID, $urlParams);
    }

    public function register(IRegistrationContext $context): void {
        $context->registerSetting(Admin::class);
    }

    public function boot(IBootContext $context): void {
        // Nothing needed at boot; FileActions are registered client-side (js/ocr-action.js).
    }
}
