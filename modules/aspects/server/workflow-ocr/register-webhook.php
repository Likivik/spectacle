<?php
declare(strict_types=1);

/**
 * Idempotently register OCR webhook listeners in Nextcloud.
 * Runs as the nextcloud user with full NC bootstrap — no OCS API auth needed.
 *
 * Usage: php register-webhook.php <nc-root> <webhook-secret-file>
 */

define('OC_CONSOLE', 1);

$logFile = '/tmp/ocr-webhook-register.log';
file_put_contents($logFile, "Starting webhook registration\n");

$ncRoot = $argv[1] ?? '';
$secretFile = $argv[2] ?? '';

if ($ncRoot === '' || $secretFile === '') {
    file_put_contents($logFile, "ERROR: missing arguments\n", FILE_APPEND);
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

file_put_contents($logFile, "Bootstrap OK\n", FILE_APPEND);

// Read the webhook secret
$webhookSecret = trim(file_get_contents($secretFile));
if ($webhookSecret === '') {
    file_put_contents($logFile, "ERROR: webhook secret is empty\n", FILE_APPEND);
    exit(1);
}

use OCP\IDBConnection;

/** @var IDBConnection $db */
$db = \OCP\Server::get(IDBConnection::class);

$webhookUri = 'http://127.0.0.1:8095/webhook';
$userId = 'admin';
$appId = 'workflow_ocr';
$headers = json_encode(['X-Webhook-Secret' => $webhookSecret]);
$eventFilter = json_encode(['event.node.path' => '/^\/.*\/files\//']);

$listeners = [
    [
        'event' => 'OCP\\Files\\Events\\Node\\NodeCreatedEvent',
    ],
    [
        'event' => 'OCP\\Files\\Events\\Node\\NodeWrittenEvent',
    ],
];

foreach ($listeners as $listener) {
    // Check if this listener already exists (idempotent)
    $qb = $db->getQueryBuilder();
    $qb->select($qb->createFunction('COUNT(*)'))
        ->from('webhook_listeners')
        ->where($qb->expr()->eq('uri', $qb->createNamedParameter($webhookUri)))
        ->andWhere($qb->expr()->eq('event', $qb->createNamedParameter($listener['event'])))
        ->andWhere($qb->expr()->eq('user_id', $qb->createNamedParameter($userId)));
    $result = $qb->executeQuery();
    $count = (int) $result->fetchOne();
    $result->closeCursor();

    if ($count > 0) {
        file_put_contents($logFile, "Webhook listener for {$listener['event']} already exists (count=$count), skipping\n", FILE_APPEND);
        continue;
    }

    // Insert the listener
    $qb = $db->getQueryBuilder();
    $qb->insert('webhook_listeners')
        ->values([
            'app_id' => $qb->createNamedParameter($appId),
            'user_id' => $qb->createNamedParameter($userId),
            'http_method' => $qb->createNamedParameter('POST'),
            'uri' => $qb->createNamedParameter($webhookUri),
            'event' => $qb->createNamedParameter($listener['event']),
            'event_filter' => $qb->createNamedParameter($eventFilter),
            'headers' => $qb->createNamedParameter($headers),
            'auth_method' => $qb->createNamedParameter('none'),
            'auth_data' => $qb->createNamedParameter(''),
        ]);
    $qb->executeStatement();

    file_put_contents($logFile, "Created webhook listener for {$listener['event']}\n", FILE_APPEND);
}

file_put_contents($logFile, "Webhook registration complete\n", FILE_APPEND);
