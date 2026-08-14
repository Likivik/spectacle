<?php
declare(strict_types=1);

define('OC_CONSOLE', 1);

$logFile = '/tmp/ocr-flow-setup.log';
file_put_contents($logFile, "Starting OCR flow setup\n");

// NC root path is passed as $argv[1]
$ncRoot = $argv[1] ?? '/nix/store/00jxvqsfckx9wr3b3bi1km2kfqikah2i-nextcloud-34.0.2-with-apps';
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

file_put_contents($logFile, "Bootstrap OK\n", FILE_APPEND);

use OCP\WorkflowEngine\IManager as IWorkflowManager;
use OCP\App\IAppManager;
use OCP\Server;

$appManager = Server::get(IAppManager::class);
if (!$appManager->isEnabledForUser('workflow_ocr')) {
    file_put_contents($logFile, "workflow_ocr not enabled, skipping\n");
    return;
}

file_put_contents($logFile, "workflow_ocr enabled\n", FILE_APPEND);

// The workflow engine Manager implementation lives in the workflowengine app.
// OCP\WorkflowEngine\IManager is an interface — can't be resolved directly.
try {
    $manager = Server::get(\OCA\WorkflowEngine\Manager::class);
    file_put_contents($logFile, "Got Manager: " . get_class($manager) . "\n", FILE_APPEND);
} catch (\Throwable $e) {
    file_put_contents($logFile, "Server::get(Manager) failed: " . $e->getMessage() . "\n" . $e->getTraceAsString() . "\n", FILE_APPEND);
    exit(1);
}

try {
    $scope = new \OCA\WorkflowEngine\Helper\ScopeContext(IWorkflowManager::SCOPE_ADMIN, '');
    file_put_contents($logFile, "Got ScopeContext\n", FILE_APPEND);
} catch (\Throwable $e) {
    file_put_contents($logFile, "ScopeContext failed: " . $e->getMessage() . "\n" . $e->getTraceAsString() . "\n", FILE_APPEND);
    exit(1);
}

// Check if OCR flow rule already exists
try {
    $existing = $manager->getOperations('OCA\WorkflowOcr\Operation', $scope);
    file_put_contents($logFile, "getOperations returned " . count($existing) . " results\n", FILE_APPEND);
} catch (\Throwable $e) {
    file_put_contents($logFile, "getOperations failed: " . $e->getMessage() . "\n", FILE_APPEND);
    $existing = [];
}
if (!empty($existing)) {
    file_put_contents($logFile, "OCR workflow rule already exists (id=" . $existing[0]['id'] . "), skipping\n", FILE_APPEND);
    return;
}

file_put_contents($logFile, "No existing rule found, creating...\n", FILE_APPEND);

$checks = [
    [
        'class' => 'OCA\WorkflowEngine\Check\FileMimeType',
        'operator' => 'is',
        'value' => 'application/pdf',
    ],
];

$operation = json_encode([
    'languages' => ['rus', 'eng'],
    'removeBackground' => false,
    'ocrMode' => 0,
    'keepOriginalFileVersion' => false,
    'keepOriginalFileDate' => false,
    'sendSuccessNotification' => false,
    'createSidecarFile' => false,
    'customCliArgs' => '',
    'tagsToRemoveAfterOcr' => [],
    'tagsToAddAfterOcr' => [],
    'skipNotificationsOnInvalidPdf' => false,
    'skipNotificationsOnEncryptedPdf' => false,
]);

$events = [
    '\OCP\Files::postCreate',
    '\OCP\Files::postWrite',
];

try {
    $manager->addOperation(
        'OCA\WorkflowOcr\Operation',
        'Auto OCR (rus+eng)',
        $checks,
        $operation,
        $scope,
        \OCA\WorkflowEngine\Entity\File::class,
        $events
    );
    file_put_contents($logFile, "OCR workflow rule created successfully\n", FILE_APPEND);
} catch (\Throwable $e) {
    file_put_contents($logFile, "ERROR creating rule: " . $e->getMessage() . "\n" . $e->getTraceAsString() . "\n", FILE_APPEND);
    exit(1);
}
