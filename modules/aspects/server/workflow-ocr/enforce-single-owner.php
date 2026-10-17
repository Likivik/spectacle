<?php
declare(strict_types=1);

/**
 * Disable any competing OCR app that is still enabled, inside Nextcloud.
 *
 * Runs after nextcloud-setup as the nextcloud user with a full NC bootstrap
 * (called from the nc-ocr-register-webhook oneshot). Idempotent, best-effort.
 *
 * The nix-level throw only guards what nix configures; this catches an app
 * enabled by hand, or left enabled by a previous generation. Nextcloud itself
 * only disables an app whose files disappeared while it is actually running an
 * upgrade (lib/private/Updater.php checkAppsRequirements -> disableApp), so it
 * cannot be relied on for this. Uses the public OCP API (IAppManager), which is
 * the same call `occ app:disable` makes — the documented CLI alternative — just
 * without shelling out and parsing command output.
 *
 * The leftover-Flow-rule REPORT is deliberately NOT done here. It is done by
 * the calling unit with the documented `occ workflows:list`, so this script
 * reads no table at all. Context for that choice: a rule whose operation class
 * is gone is skipped SILENTLY while the app is disabled (lib/Manager.php:269-272
 * is a bare `continue`, no logging; lib/RuleMatcher.php:204-207 for checks), so
 * the invariant holds without touching it, and every deletion path is closed to
 * a headless service — the workflowengine OCS routes carry
 * #[PasswordConfirmationRequired] on create/update/destroy, there is no occ
 * delete command, and a raw DELETE against the internal flow_operations table is
 * unsanctioned and coupled to a schema we do not own.
 *
 * Logging goes to STDERR (the systemd journal).
 *
 * Usage: php enforce-single-owner.php <nc-root> [app-id]...
 * Exits non-zero if an app could not actually be disabled.
 */

define('OC_CONSOLE', 1);

function log_line(string $message): void
{
    fwrite(STDERR, $message . "\n");
}

$ncRoot = $argv[1] ?? '';
$apps = array_slice($argv, 2);

if ($ncRoot === '') {
    log_line('ERROR: missing nc-root argument');
    exit(1);
}

chdir($ncRoot);
error_reporting(E_ALL);
ini_set('display_errors', '1');
ini_set('log_errors', '1');

try {
    require_once $ncRoot . '/lib/base.php';
} catch (\Throwable $e) {
    log_line('Bootstrap failed: ' . $e->getMessage());
    exit(1);
}

use OCP\App\IAppManager;

$appManager = \OCP\Server::get(IAppManager::class);
$failed = false;

foreach ($apps as $app) {
    $app = trim((string) $app);
    if ($app === '') {
        continue;
    }
    try {
        if (!$appManager->isEnabledForAnyone($app)) {
            log_line("Competing OCR app already disabled: $app");
            continue;
        }
        $appManager->disableApp($app);
        // Verify the post-condition: logging "disabled" while the app is still
        // enabled would be worse than not checking at all.
        if ($appManager->isEnabledForAnyone($app)) {
            log_line("ERROR: $app is STILL enabled after disableApp()");
            $failed = true;
        } else {
            log_line("Disabled competing OCR app: $app");
        }
    } catch (\Throwable $e) {
        log_line("ERROR: could not disable $app: " . $e->getMessage());
        $failed = true;
    }
}

log_line($failed ? 'Single-owner enforcement finished with errors' : 'Single-owner enforcement complete');
exit($failed ? 1 : 0);
