<?php
/**
 * Admin settings: OCR service URL + shared secret (stored in system config).
 */
namespace OCA\OcrFlow\Settings;

use OCP\AppFramework\Http\TemplateResponse;
use OCP\IConfig;
use OCP\Settings\ISettings;

class Admin implements ISettings {
    private IConfig $config;

    public function __construct(IConfig $config) {
        $this->config = $config;
    }

    public function getForm(): TemplateResponse {
        $parameters = [
            'ocrflow_url' => $this->config->getSystemValue('ocrflow_url', 'http://127.0.0.1:8095'),
            // Secret is never rendered back to the form — write-only.
        ];
        return new TemplateResponse('ocrflow', 'admin', $parameters, '');
    }

    public function getSection(): string {
        return 'server';
    }

    public function getPriority(): int {
        return 80;
    }
}
