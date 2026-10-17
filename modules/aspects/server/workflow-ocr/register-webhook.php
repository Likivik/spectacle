<?php
declare(strict_types=1);

/**
 * Idempotently register this service's webhook listeners through the
 * documented Nextcloud OCS API (webhook_listeners app).
 *
 * A class rather than a pile of top-level functions, because Nextcloud's
 * coding standard says "No global variables or functions" and the whole
 * ecosystem is class + dependency-injection shaped. It also gives the OCS
 * call a protected seam (`ocsRequest`) that a test can override, which is
 * how the create / rotate / verify branches get exercised without a live
 * Nextcloud.
 *
 * Usage:
 *   php register-webhook.php <base-url> <user> <app-password-file> <secret>
 *
 * Logging goes to STDERR, i.e. the systemd journal
 * (`journalctl -u nc-ocr-register-webhook`). Deliberately not a file: a
 * /tmp log is not rotated, is world-readable unless the unit sets a umask,
 * and - worst - a manual root-run leaves a root-owned file the unit
 * (running as `nextcloud`) can no longer write, so it fails with a warning
 * only while the log you are reading is stale.
 *
 * <base-url> MUST be an address Nextcloud's admin-action IP policy accepts
 * (config.php `allowed_admin_ranges`). On this host that list is the
 * Tailscale ranges, so the host's own Tailscale name works while 127.0.0.1
 * and the LAN address are rejected with "Your current IP address doesn't
 * allow you to perform admin actions". That check runs AFTER authorisation
 * and applies even to ExApps (SecurityMiddleware).
 *
 * Credential: a dedicated service account whose group holds ONLY
 * OCA\WebhookListeners\Settings\Admin, granted with
 *   occ admin-delegation:add 'OCA\WebhookListeners\Settings\Admin' <group>
 * authenticating with a REAL app password
 *   occ user:auth-tokens:add <user> --name=... --password-from-env
 * A passwordless app password is NOT enough: it authenticates, but is not
 * treated as an admin session, and AuthorizedAdminSetting then rejects it.
 * Note also that resetting that account's password invalidates its app
 * passwords, so a token must be minted AFTER any password change.
 *
 * Why the OCS API rather than the database: the admin manual documents
 * webhook management as the OCS API / CLI, and oc_webhook_listeners is an
 * internal table owned by that app. Two fields the API decides for us:
 *   - user_id becomes the authenticated service user. Delivery does not
 *     depend on it: the app matches on user_id_filter (empty here = every
 *     user) - WebhookListenerMapper::getByEvent().
 *   - app_id can only be set for an AppAPI/ExApp session, so these rows
 *     carry app_id NULL. Harmless: app_id is used only by the by-appid
 *     delete route.
 *
 * Exit code is meaningful: 0 only when BOTH listeners are confirmed to
 * carry the current webhook secret. A listener whose stored header snapshot
 * is stale 401s every dispatch, and that failure is invisible everywhere
 * else - the service stays healthy and only uploads silently stop.
 */

final class WebhookRegistrar
{
	private const WEBHOOK_URI = 'http://127.0.0.1:8095/webhook';
	private const EVENT_FILTER = ['event.node.path' => '/^\/.*\/files\//'];
	private const EVENTS = [
		'OCP\\Files\\Events\\Node\\NodeCreatedEvent',
		'OCP\\Files\\Events\\Node\\NodeWrittenEvent',
	];
	private const TIMEOUT = 30;
	private const USAGE = 'usage: register-webhook.php <base-url> <user>'
		. ' <app-password-file> <webhook-secret-file>';

	private string $endpoint;
	private array $headers;

	public function __construct(
		private string $baseUrl,
		private string $serviceUser,
		private string $appPassword,
		private string $webhookSecret
	) {
		$this->endpoint = $baseUrl
			. '/ocs/v2.php/apps/webhook_listeners/api/v1/webhooks';
		$this->headers = [
			'OCS-APIRequest: true',
			'Accept: application/json',
			'Authorization: Basic '
				. base64_encode($serviceUser . ':' . $appPassword),
		];
	}

	/**
	 * Build from CLI arguments, or null when any input is missing/empty.
	 */
	public static function fromArgv(array $argv): ?self
	{
		$baseUrl = rtrim((string) ($argv[1] ?? ''), '/');
		$serviceUser = (string) ($argv[2] ?? '');
		$appPassword = trim(
			(string) @file_get_contents((string) ($argv[3] ?? ''))
		);
		$webhookSecret = trim(
			(string) @file_get_contents((string) ($argv[4] ?? ''))
		);
		if ($baseUrl === '' || $serviceUser === '' || $appPassword === ''
			|| $webhookSecret === ''
		) {
			return null;
		}
		return new self($baseUrl, $serviceUser, $appPassword, $webhookSecret);
	}

	public static function usage(): void
	{
		fwrite(STDERR, 'ERROR: ' . self::USAGE . "\n");
	}

	public function run(): int
	{
		$this->log('Starting webhook registration (OCS API)');

		$existing = $this->listListeners();
		if ($existing === null) {
			return 1;
		}
		$this->log(
			'Listed ' . count($existing) . ' existing listener(s) for '
			. self::WEBHOOK_URI
		);

		$failed = $this->apply($existing);
		return $this->verify($failed) ? 0 : 1;
	}

	/**
	 * Create the missing listeners and refresh any stale ones.
	 *
	 * @param array<string,array<string,mixed>> $existing
	 * @return bool whether anything failed
	 */
	private function apply(array $existing): bool
	{
		$failed = false;
		foreach (self::EVENTS as $event) {
			$failed = isset($existing[$event])
				? ($this->update($event, $existing[$event]) || $failed)
				: ($this->create($event) || $failed);
		}
		return $failed;
	}

	private function create(string $event): bool
	{
		[$code, $raw] = $this->ocsRequest(
			'POST',
			$this->endpoint,
			$this->payload($event)
		);
		if ($code === 200) {
			$this->log("Created listener for $event");
			return false;
		}
		$this->log(
			"ERROR: create failed for $event (HTTP $code): "
			. $this->redact($raw)
		);
		return true;
	}

	/**
	 * @param array<string,mixed> $row
	 */
	private function update(string $event, array $row): bool
	{
		$id = (int) ($row['id'] ?? 0);
		$stored = $this->storedSecret($row);
		// The stored headers are a SNAPSHOT of the secret taken when the
		// listener was last written, so a rotated secret would 401 forever
		// unless we refresh it here.
		if ($stored === $this->webhookSecret
			&& ($row['uri'] ?? null) === self::WEBHOOK_URI
			&& ($row['httpMethod'] ?? null) === 'POST'
			&& ($row['eventFilter'] ?? null) == self::EVENT_FILTER
		) {
			$this->log("Listener for $event already up to date (id=$id)");
			return false;
		}

		[$code, $raw] = $this->ocsRequest(
			'POST',
			$this->endpoint . '/' . $id,
			$this->payload($event)
		);
		if ($code === 200) {
			$suffix = $stored !== $this->webhookSecret
				? ' - webhook secret rotated'
				: '';
			$this->log("Updated listener for $event (id=$id)$suffix");
			return false;
		}
		$this->log(
			"ERROR: update failed for $event (id=$id, HTTP $code): "
			. $this->redact($raw)
		);
		return true;
	}

	/**
	 * Re-read and confirm both rows carry the CURRENT secret. A 200 is not
	 * proof the row is right, and a stale snapshot silently stops all
	 * automatic OCR.
	 */
	private function verify(bool $failed): bool
	{
		$after = $this->listListeners();
		if ($after === null) {
			return false;
		}
		foreach (self::EVENTS as $event) {
			if ($this->storedSecret($after[$event] ?? [])
				!== $this->webhookSecret
			) {
				$this->log(
					"ERROR: listener for $event does not carry the current"
					. ' webhook secret after registration'
				);
				$failed = true;
			}
		}
		if (!$failed) {
			$this->log(
				'Verified: ' . count(self::EVENTS)
				. ' listener(s) carry the current webhook secret'
			);
		} else {
			$this->log('Webhook registration finished with errors');
		}
		return !$failed;
	}

	/**
	 * @return array<string,mixed>
	 */
	private function payload(string $event): array
	{
		return [
			'httpMethod' => 'POST',
			'uri' => self::WEBHOOK_URI,
			'event' => $event,
			'eventFilter' => self::EVENT_FILTER,
			'userIdFilter' => '',
			'headers' => ['X-Webhook-Secret' => $this->webhookSecret],
			'authMethod' => 'none',
			'authData' => null,
		];
	}

	/**
	 * @param array<string,mixed> $row
	 */
	private function storedSecret(array $row): string
	{
		$headers = is_array($row['headers'] ?? null) ? $row['headers'] : [];
		return (string) ($headers['X-Webhook-Secret'] ?? '');
	}

	/**
	 * This service's listeners, keyed by event class.
	 *
	 * @return array<string,array<string,mixed>>|null null on failure
	 */
	private function listListeners(): ?array
	{
		$url = $this->endpoint . '?uri=' . rawurlencode(self::WEBHOOK_URI);
		[$code, $raw] = $this->ocsRequest('GET', $url);
		if ($code !== 200) {
			$this->log(
				"ERROR: could not list listeners (HTTP $code): "
				. $this->redact($raw)
			);
			return null;
		}
		$decoded = json_decode($raw, true);
		$found = [];
		foreach (($decoded['ocs']['data'] ?? []) as $row) {
			if (!is_array($row) || ($row['uri'] ?? null) !== self::WEBHOOK_URI) {
				continue;
			}
			if (isset($row['event'])) {
				$found[(string) $row['event']] = $row;
			}
		}
		return $found;
	}

	/**
	 * One OCS request. Protected so a test can stub it.
	 *
	 * @return array{0:int,1:string} HTTP status and raw response body
	 */
	protected function ocsRequest(
		string $method,
		string $url,
		?array $body = null
	): array {
		$http = [
			'method' => $method,
			'header' => implode("\r\n", $this->headers),
			// Read 4xx/5xx bodies instead of getting `false` back.
			'ignore_errors' => true,
			'timeout' => self::TIMEOUT,
		];
		if ($body !== null) {
			$http['header'] .= "\r\nContent-Type: application/json";
			$http['content'] = json_encode($body);
		}
		$raw = @file_get_contents(
			$url,
			false,
			stream_context_create(['http' => $http])
		);

		$code = 0;
		if (isset($http_response_header[0])
			&& preg_match(
				'#^HTTP/\S+\s+(\d{3})#',
				$http_response_header[0],
				$m
			)
		) {
			$code = (int) $m[1];
		}
		return [$code, $raw === false ? '' : $raw];
	}

	/**
	 * Strip the secret out of anything about to be logged: an OCS error
	 * body can echo the submitted payload.
	 */
	private function redact(string $text): string
	{
		if ($this->webhookSecret === '') {
			return substr(trim($text), 0, 300);
		}
		return str_replace(
			$this->webhookSecret,
			'[REDACTED]',
			substr(trim($text), 0, 300)
		);
	}

	private function log(string $message): void
	{
		fwrite(STDERR, $message . "\n");
	}
}

$registrar = WebhookRegistrar::fromArgv($argv);
if ($registrar === null) {
	WebhookRegistrar::usage();
	exit(1);
}
exit($registrar->run());
