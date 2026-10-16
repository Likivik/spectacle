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
    // Look up an existing listener for this uri+event+user (idempotent)
    $qb = $db->getQueryBuilder();
    $qb->select('id', 'headers')
        ->from('webhook_listeners')
        ->where($qb->expr()->eq('uri', $qb->createNamedParameter($webhookUri)))
        ->andWhere($qb->expr()->eq('event', $qb->createNamedParameter($listener['event'])))
        ->andWhere($qb->expr()->eq('user_id', $qb->createNamedParameter($userId)))
        ->setMaxResults(1);
    $result = $qb->executeQuery();
    $row = $result->fetch();
    $result->closeCursor();

    if ($row !== false) {
        // The listener exists. Its stored headers are a SNAPSHOT of the secret
        // taken when it was first created — so a rotated secret would keep
        // 401-ing forever unless we refresh it here. Compare semantically
        // (json_decode) so key order / formatting cannot cause a false refresh.
        $id = (int) $row['id'];
        $stored = json_decode((string) $row['headers'], true);
        $want = json_decode($headers, true);

        if ($stored !== $want) {
            $qb = $db->getQueryBuilder();
            $qb->update('webhook_listeners')
                ->set('headers', $qb->createNamedParameter($headers))
                ->where($qb->expr()->eq('id', $qb->createNamedParameter($id)));
            $qb->executeStatement();
            file_put_contents(
                $logFile,
                "Refreshed stale headers for {$listener['event']} (id=$id) — secret rotated\n",
                FILE_APPEND
            );
        } else {
            file_put_contents(
                $logFile,
                "Webhook listener for {$listener['event']} already up to date (id=$id)\n",
                FILE_APPEND
            );
        }
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
            'user_id_filter' => $qb->createNamedParameter(''),
            'headers' => $qb->createNamedParameter($headers),
            'auth_method' => $qb->createNamedParameter('none'),
            'auth_data' => $qb->createNamedParameter(''),
            'token_needed' => $qb->createNamedParameter('[]'),
        ]);
    $qb->executeStatement();

    file_put_contents($logFile, "Created webhook listener for {$listener['event']}\n", FILE_APPEND);
}

file_put_contents($logFile, "Webhook registration complete\n", FILE_APPEND);
