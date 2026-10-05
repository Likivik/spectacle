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

use OCA\OcrFlow\BackgroundJob\PollOcrStatus;
use OCA\OcrFlow\Notification\Notifier;
use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;
use OCP\BackgroundJob\IJobList;
use OCP\Util;

class Application extends App implements IBootstrap {
    public const APP_ID = 'ocrflow';

    public function __construct(array $urlParams = []) {
        parent::__construct(self::APP_ID, $urlParams);
    }

    public function register(IRegistrationContext $context): void {
        // Admin + personal settings sections are registered declaratively in
        // appinfo/info.xml (<settings>…</settings>); the action JS is loaded
        // in boot().
        //
        // Notifications for finished/failed OCR jobs (bell + mobile push) are
        // raised by the PollOcrStatus background job and presented by Notifier.
        $context->registerNotifierService(Notifier::class);
    }

    public function boot(IBootContext $context): void {
        // Loads the Files context-menu actions. The JS is a vite bundle
        // (frontend/src -> js/ocrflow-main.mjs, @nextcloud/vite-config):
        // NC 34 file actions register via `import { registerFileAction } from
        // '@nextcloud/files'`, which resolves only inside a bundle — a raw
        // browser ESM throws "Failed to resolve module specifier".
        // addInitScript emits /nix-apps/ocrflow/js/ocrflow-main.mjs (loaded
        // as type=module because of the .mjs extension). The name MUST match
        // the on-disk bundle file (JSResourceLocator resolves static files,
        // not routes).
        Util::addInitScript('ocrflow', 'ocrflow-frontend-main');

        // Schedule the status poller. info.xml <background-jobs> only inserts
        // jobs on app install/update; this guard makes in-place upgrades work.
        /** @var IJobList $jobList */
        $jobList = $context->getServerContainer()->get(IJobList::class);
        if (!$jobList->has(PollOcrStatus::class, null)) {
            $jobList->add(PollOcrStatus::class);
        }
    }
}