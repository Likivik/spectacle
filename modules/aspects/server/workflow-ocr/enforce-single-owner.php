<?php
declare(strict_types=1);

/**
 * Enforce the single-OCR-owner invariant inside Nextcloud.
 *
 * Runs after nextcloud-setup as the nextcloud user with a full NC bootstrap
 * (called from the nc-ocr-register-webhook oneshot). Two jobs, both idempotent
 * and best-effort:
 *
 *   1. Disable any competing OCR app that is still enabled. The nix-level
 *      throw only guards what nix configures; this catches an app enabled by
 *      hand, or left enabled by a previous generation. Nextcloud itself only
 *      disables an app whose files disappeared while it is actually running an
 *      upgrade (lib/private/Updater.php checkAppsRequirements -> disableApp,
 *      line 372), so it cannot be relied on for this.
 *
 *   2. Delete leftover Flow operations belonging to a competing OCR app. The
 *      workflowengine silently skips an operation whose class cannot be loaded
 *      (lib/Manager.php:269-271 and lib/RuleMatcher.php:204-207 catch the
 *      container exception), so an orphan row is harmless — but it is dead
 *      config that would come back to life if the app were ever re-installed,
 *      and there is no occ command to delete a rule, so it is removed here.
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

use OCA\WorkflowEngine\Helper\ScopeContext;
use OCA\WorkflowEngine\Manager as WorkflowManager;
use OCP\App\IAppManager;
use OCP\DB\IQueryBuilder;
use OCP\IDBConnection;

$appManager = \OCP\Server::get(IAppManager::class);
$db = \OCP\Server::get(IDBConnection::class);

// The workflowengine app's own Manager. It is an app class rather than public
// OCP API, but there is no public API and no occ command for deleting a Flow
// rule, and this is the exact code path the admin UI's delete endpoint takes
// (apps/workflowengine/lib/Controller/AWorkflowOCSController.php:180), so it is
// the sanctioned route. Resolved through the container the same way the app's
// own bootstrap does (apps/workflowengine/lib/AppInfo/Application.php:57).
$workflowManager = null;
try {
    $workflowManager = \OCP\Server::get(WorkflowManager::class);
} catch (\Throwable $e) {
    file_put_contents(
        $logFile,
        "WARN: workflowengine Manager unavailable, skipping Flow-rule cleanup: "
        . $e->getMessage() . "\n",
        FILE_APPEND
    );
}

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

// --- 2. delete leftover Flow operations owned by those apps ---------------
// The operation class lives in the app's namespace: workflow_ocr ->
// OCA\WorkflowOcr\Operation.
//
// Done through WorkflowManager::deleteOperation(), NOT a raw SQL DELETE: the
// supported method removes the flow_operations row and its flow_operations_scope
// row in a single transaction AND invalidates the distributed 'flow' cache. A
// raw delete leaves that cache warm, so the removed rule can keep firing until
// the entry expires.
foreach ($apps as $app) {
    $app = trim((string) $app);
    if ($app === '' || $workflowManager === null) {
        continue;
    }
    $camel = str_replace(' ', '', ucwords(str_replace('_', ' ', $app)));
    $class = 'OCA\\' . $camel . '\\Operation';

    // Look up the rules (and their scope) for that class first: deleteOperation
    // is keyed by operation id + ScopeContext, not by class name.
    try {
        $qb = $db->getQueryBuilder();
        $qb->select('o.id', 's.type', 's.value')
            ->from('flow_operations', 'o')
            ->leftJoin(
                'o',
                'flow_operations_scope',
                's',
                $qb->expr()->eq('o.id', 's.operation_id')
            )
            ->where($qb->expr()->eq('o.class', $qb->createNamedParameter($class)));
        $result = $qb->executeQuery();
        $rules = $result->fetchAll();
        $result->closeCursor();
    } catch (\Throwable $e) {
        file_put_contents($logFile, "WARN: could not look up flow rules for $class: " . $e->getMessage() . "\n", FILE_APPEND);
        continue;
    }

    foreach ($rules as $rule) {
        // ScopeContext(int $scope, ?string $scopeId); the scope row is what the
        // engine groups rules by (0 = admin scope).
        $scope = new ScopeContext((int) ($rule['type'] ?? 0), (string) ($rule['value'] ?? ''));
        try {
            $deleted = $workflowManager->deleteOperation((int) $rule['id'], $scope);
            file_put_contents(
                $logFile,
                ($deleted ? "Deleted" : "Could not delete")
                . " leftover flow rule id={$rule['id']} class=$class (scope "
                . $scope->getScope() . ")\n",
                FILE_APPEND
            );
        } catch (\Throwable $e) {
            file_put_contents($logFile, "WARN: deleteOperation failed for rule id={$rule['id']} ($class): " . $e->getMessage() . "\n", FILE_APPEND);
        }
    }
}

// --- 3. drop scope rows that now point at no operation --------------------
try {
    $qb = $db->getQueryBuilder();
    $qb->select('id')->from('flow_operations');
    $result = $qb->executeQuery();
    $ids = array_map('intval', array_column($result->fetchAll(), 'id'));
    $result->closeCursor();

    $qb = $db->getQueryBuilder();
    $qb->delete('flow_operations_scope');
    if ($ids !== []) {
        $qb->where($qb->expr()->notIn(
            'operation_id',
            $qb->createNamedParameter($ids, IQueryBuilder::PARAM_INT_ARRAY)
        ));
    }
    $deleted = $qb->executeStatement();
    if ($deleted > 0) {
        file_put_contents($logFile, "Deleted $deleted orphaned flow scope row(s)\n", FILE_APPEND);
    }
} catch (\Throwable $e) {
    file_put_contents($logFile, "WARN: flow scope cleanup failed: " . $e->getMessage() . "\n", FILE_APPEND);
}

file_put_contents($logFile, "Single-owner enforcement complete\n", FILE_APPEND);
