<?php
declare(strict_types=1);

/**
 * Idempotently register this service's webhook listeners through the
 * documented Nextcloud OCS API (webhook_listeners app).
 *
 * Usage:
 *   php register-webhook.php <ocs-base-url> <service-user> <app-password-file> <webhook-secret-file>
 *
 * <ocs-base-url> MUST be an address Nextcloud's admin-action IP policy accepts
 * (config.php `allowed_admin_ranges`). On this host that list is
 * ["100.64.0.0/10", "fd7a:115c:a1e0::/48"] — the Tailscale ranges — so the
 * host's own Tailscale name works, while 127.0.0.1 and the LAN address are
 * rejected with "Your current IP address doesn't allow you to perform admin
 * actions". That check runs AFTER authorisation and applies even to ExApps
 * (lib/private/AppFramework/Middleware/Security/SecurityMiddleware.php).
 *
 * Credential: a dedicated service account whose group holds ONLY
 * OCA\WebhookListeners\Settings\Admin, granted with
 *   occ admin-delegation:add 'OCA\WebhookListeners\Settings\Admin' <group>
 * authenticating with a REAL app password
 *   occ user:auth-tokens:add <user> --name=... --password-from-env
 * A passwordless app password (created without the login password) is NOT
 * enough: it authenticates, but is not treated as an admin session, and
 * AuthorizedAdminSetting then rejects it with "must be an admin, a sub admin
 * or gotten special right to access this setting".
 *
 * Why the OCS API rather than the database: the admin manual documents webhook
 * management as the OCS API / CLI ("Management and configuration of webhook
 * listeners are handled via the Nextcloud OCS API and command-line tools"),
 * and oc_webhook_listeners is an internal table owned by that app. Two fields
 * the API decides for us:
 *   - user_id becomes the authenticated service user. This does NOT affect
 *     delivery: the app matches listeners on user_id_filter (empty here =
 *     every user) — WebhookListenerMapper::getByEvent().
 *   - app_id can only be set for an AppAPI/ExApp session (WebhooksController
 *     reads the ex-app-id header only when session 'app_api' is true), so these
 *     rows carry app_id NULL. Harmless: app_id is used only by the by-appid
 *     delete route.
 */

$logFile = '/tmp/ocr-webhook-register.log';

function log_line(string $message): void
{
    global $logFile;
    file_put_contents($logFile, $message . "\n", FILE_APPEND);
}

file_put_contents($logFile, "Starting webhook registration (OCS API)\n");

$baseUrl = rtrim((string) ($argv[1] ?? ''), '/');
$serviceUser = (string) ($argv[2] ?? '');
$appPasswordFile = (string) ($argv[3] ?? '');
$secretFile = (string) ($argv[4] ?? '');

if ($baseUrl === '' || $serviceUser === '' || $appPasswordFile === '' || $secretFile === '') {
    log_line('ERROR: usage: register-webhook.php <ocs-base-url> <service-user> <app-password-file> <webhook-secret-file>');
    exit(1);
}

$appPassword = trim((string) @file_get_contents($appPasswordFile));
$webhookSecret = trim((string) @file_get_contents($secretFile));
if ($appPassword === '' || $webhookSecret === '') {
    log_line('ERROR: empty app password or webhook secret');
    exit(1);
}

const WEBHOOK_URI = 'http://127.0.0.1:8095/webhook';
const EVENT_FILTER = ['event.node.path' => '/^\/.*\/files\//'];
const EVENTS = [
    'OCP\\Files\\Events\\Node\\NodeCreatedEvent',
    'OCP\\Files\\Events\\Node\\NodeWrittenEvent',
];

$endpoint = $baseUrl . '/ocs/v2.php/apps/webhook_listeners/api/v1/webhooks';
$requestHeaders = [
    'OCS-APIRequest: true',
    'Accept: application/json',
    'Authorization: Basic ' . base64_encode($serviceUser . ':' . $appPassword),
];

/**
 * Perform one OCS request.
 *
 * @return array{0:int,1:string} HTTP status code and raw response body
 */
function ocs_request(string $method, string $url, array $headers, ?array $body = null): array
{
    $http = [
        'method' => $method,
        'header' => implode("\r\n", $headers),
        // Read 4xx/5xx bodies instead of getting `false` back.
        'ignore_errors' => true,
        'timeout' => 30,
    ];
    if ($body !== null) {
        $http['header'] .= "\r\nContent-Type: application/json";
        $http['content'] = json_encode($body);
    }

    $raw = @file_get_contents($url, false, stream_context_create(['http' => $http]));
    $code = 0;
    if (isset($http_response_header[0])
        && preg_match('#^HTTP/\S+\s+(\d{3})#', $http_response_header[0], $m)) {
        $code = (int) $m[1];
    }

    return [$code, $raw === false ? '' : $raw];
}

[$code, $raw] = ocs_request('GET', $endpoint . '?uri=' . rawurlencode(WEBHOOK_URI), $requestHeaders);
if ($code !== 200) {
    log_line("ERROR: could not list listeners (HTTP $code): " . substr(trim($raw), 0, 300));
    exit(1);
}

$decoded = json_decode($raw, true);
$existing = [];
foreach (($decoded['ocs']['data'] ?? []) as $row) {
    if (is_array($row) && ($row['uri'] ?? null) === WEBHOOK_URI && isset($row['event'])) {
        $existing[(string) $row['event']] = $row;
    }
}
log_line('Listed ' . count($existing) . ' existing listener(s) for ' . WEBHOOK_URI);

$failed = false;
foreach (EVENTS as $event) {
    $payload = [
        'httpMethod' => 'POST',
        'uri' => WEBHOOK_URI,
        'event' => $event,
        'eventFilter' => EVENT_FILTER,
        'userIdFilter' => '',
        'headers' => ['X-Webhook-Secret' => $webhookSecret],
        'authMethod' => 'none',
        'authData' => null,
    ];

    if (isset($existing[$event])) {
        $row = $existing[$event];
        $id = (int) ($row['id'] ?? 0);
        $storedHeaders = is_array($row['headers'] ?? null) ? $row['headers'] : [];
        // The stored headers are a SNAPSHOT of the secret taken when the
        // listener was last written, so a rotated secret would 401 forever
        // unless we refresh it here.
        $storedSecret = (string) ($storedHeaders['X-Webhook-Secret'] ?? '');

        $upToDate = $storedSecret === $webhookSecret
            && ($row['uri'] ?? null) === WEBHOOK_URI
            && ($row['httpMethod'] ?? null) === 'POST'
            && ($row['eventFilter'] ?? null) == EVENT_FILTER;

        if ($upToDate) {
            log_line("Listener for $event already up to date (id=$id)");
            continue;
        }

        [$code, $raw] = ocs_request('POST', "$endpoint/$id", $requestHeaders, $payload);
        if ($code === 200) {
            log_line(
                "Updated listener for $event (id=$id)"
                . ($storedSecret !== $webhookSecret ? ' - webhook secret rotated' : '')
            );
        } else {
            log_line("ERROR: update failed for $event (id=$id, HTTP $code): " . substr(trim($raw), 0, 300));
            $failed = true;
        }
        continue;
    }

    [$code, $raw] = ocs_request('POST', $endpoint, $requestHeaders, $payload);
    if ($code === 200) {
        log_line("Created listener for $event");
    } else {
        log_line("ERROR: create failed for $event (HTTP $code): " . substr(trim($raw), 0, 300));
        $failed = true;
    }
}

log_line($failed ? 'Webhook registration finished with errors' : 'Webhook registration complete');
exit($failed ? 1 : 0);
