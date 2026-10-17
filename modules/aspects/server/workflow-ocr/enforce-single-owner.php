<?php
declare(strict_types=1);

/**
 * Enforce the single-OCR-owner invariant inside Nextcloud.
 *
 * Runs after nextcloud-setup as the nextcloud user with a full NC bootstrap
 * (called from the nc-ocr-register-webhook oneshot). Idempotent, best-effort.
 *
 * 1. Disable any competing OCR app that is still enabled. The nix-level throw
 *    only guards what nix configures; this catches an app enabled by hand, or
 *    left enabled by a previous generation. Nextcloud itself only disables an
 *    app whose files disappeared while it is actually running an upgrade
 *    (lib/private/Updater.php checkAppsRequirements -> disableApp, line 372),
 *    so it cannot be relied on for this. Uses the public OCP API (IAppManager),
 *    the same call `occ app:disable` makes.
 *
 * 2. REPORT — never delete — leftover Flow operations belonging to a competing
 *    OCR app. A leftover rule is inert AND silent while the app is disabled:
 *    the workflowengine catches the container exception when the operation
 *    class cannot be loaded and skips the rule
 *    (lib/Manager.php:269-272 is a bare `continue`, no logging;
 *    lib/RuleMatcher.php:204-207 for checks). So the invariant holds without
 *    touching the rule, and we deliberately do not delete it:
 *      - every deletion path is closed to a headless service. The
 *        workflowengine OCS route exists, but its create/update/destroy all
 *        carry #[PasswordConfirmationRequired], which only an interactive
 *        browser session can satisfy. Manager::deleteOperation() is the
 *        app-internal class, not public API. There is no occ delete command
 *        (only `occ workflows:list`).
 *      - a raw DELETE against the internal flow_operations table is
 *        unsanctioned and coupled to a schema we do not own.
 *    The check below is a read-only SELECT whose only job is to surface the
 *    leftover rule in the log, so an operator can remove it deliberately in
 *    the Nextcloud admin UI if they want it gone.
 *
 * Usage: php enforce-single-owner.php <nc-root> [app-id]...
 */

define('OC_CONSOLE', 1);

$logFile = '/tmp/ocr-single-owner-enforce.log';
file_put_contents($logFile, "Starting single-owner enforcement\n");

$ncRoot = $argv[1] ?? '';
$apps = array_slice($argv, 2);

if ($ncRoot === '') {
    file_put_contents($logFile, "ERROR: missing nc-root argument\n", FILE_APPEND);
    exit(1);
}

chdir($ncRoot);
error_reporting(E_ALL);
ini_set('display_errors', '1');
ini_set('log_errors', '1');

try {
    require_once $ncRoot . '/lib/base.php';
} catch (\Throwable $e) {
    file_put_contents($logFile, "Bootstrap failed: " . $e->getMessage() . "\n", FILE_APPEND);
    exit(1);
}

use OCP\App\IAppManager;
use OCP\IDBConnection;

$appManager = \OCP\Server::get(IAppManager::class);
$db = \OCP\Server::get(IDBConnection::class);

// --- 1. disable competing apps that are still enabled ----------------------
foreach ($apps as $app) {
    $app = trim((string) $app);
    if ($app === '') {
        continue;
    }
    try {
        if ($appManager->isEnabledForAnyone($app)) {
            $appManager->disableApp($app);
            file_put_contents($logFile, "Disabled competing OCR app: $app\n", FILE_APPEND);
        } else {
            file_put_contents($logFile, "Competing OCR app already disabled: $app\n", FILE_APPEND);
        }
    } catch (\Throwable $e) {
        file_put_contents($logFile, "WARN: could not disable $app: " . $e->getMessage() . "\n", FILE_APPEND);
    }
}

// --- 2. report (do not delete) leftover Flow rules for those apps ----------
// The operation class lives in the app's namespace: workflow_ocr ->
// OCA\WorkflowOcr\Operation. READ ONLY.
foreach ($apps as $app) {
    $app = trim((string) $app);
    if ($app === '') {
        continue;
    }
    $camel = str_replace(' ', '', ucwords(str_replace('_', ' ', $app)));
    $class = 'OCA\\' . $camel . '\\Operation';

    try {
        $qb = $db->getQueryBuilder();
        $qb->select('id')
            ->from('flow_operations')
            ->where($qb->expr()->eq('class', $qb->createNamedParameter($class)));
        $result = $qb->executeQuery();
        $ids = array_map('intval', array_column($result->fetchAll(), 'id'));
        $result->closeCursor();
    } catch (\Throwable $e) {
        file_put_contents($logFile, "WARN: could not read flow rules for $class: " . $e->getMessage() . "\n", FILE_APPEND);
        continue;
    }

    if ($ids !== []) {
        file_put_contents(
            $logFile,
            "NOTE: $class still has " . count($ids) . " leftover Flow rule(s) (id "
            . implode(', ', $ids) . "). Harmless and silent while $app stays disabled; "
            . "remove it in the Nextcloud admin UI if you want it gone "
            . "(there is no occ or headless API for it).\n",
            FILE_APPEND
        );
    }
}

file_put_contents($logFile, "Single-owner enforcement complete\n", FILE_APPEND);
