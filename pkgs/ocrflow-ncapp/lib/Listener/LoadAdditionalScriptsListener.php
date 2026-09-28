<?php
/**
 * Injects the OCR Flow Files context-menu action JS when the Files page
 * renders. Copied from files_reminders' Listener/LoadAdditionalScriptsListener.
 */
namespace OCA\OcrFlow\Listener;

use OCA\Files\Event\LoadAdditionalScriptsEvent;
use OCP\App\IAppManager;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\Util;

/** @template-implements IEventListener<LoadAdditionalScriptsEvent> */
final class LoadAdditionalScriptsListener implements IEventListener {
    public function __construct(
        private IAppManager $appManager,
    ) {
    }

    public function handle(Event $event): void {
        if (!($event instanceof LoadAdditionalScriptsEvent)) {
            return;
        }
        if (!$this->appManager->isEnabledForUser('ocrflow')) {
            return;
        }
        // Loads /apps/ocrflow/js/action-script (a route we serve) — under
        // NixOS extraApps the static file path under /apps 404s.
        Util::addInitScript('ocrflow', 'action-script');
    }
}