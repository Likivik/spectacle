<?php
/**
 * Personal settings section for OCR Flow — the sidebar entry in
 * Settings → Personal. Registered via <settings><personal-section> in
 * appinfo/info.xml and referenced by Personal::getSection() ('ocrflow').
 */
declare(strict_types=1);

namespace OCA\OcrFlow\Settings;

use OCP\IL10N;
use OCP\IURLGenerator;
use OCP\Settings\IIconSection;

class PersonalSection implements IIconSection {
    public function __construct(
        private readonly IL10N $l,
        private readonly IURLGenerator $url,
    ) {}

    public function getID(): string {
        return 'ocrflow';
    }

    public function getName(): string {
        return $this->l->t('OCR Flow');
    }

    public function getPriority(): int {
        return 75;
    }

    public function getIcon(): string {
        // Core icon (app static assets are not served under /apps/<app>/ in
        // this NixOS extraApps layout, so we borrow a core filetype icon).
        return $this->url->imagePath('core', 'filetypes/text.svg');
    }
}
