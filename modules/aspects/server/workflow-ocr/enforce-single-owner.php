<?php
declare(strict_types=1);

use OCP\App\IAppManager;
use OCP\Server;

/**
 * Disable any competing OCR app that is still enabled, inside Nextcloud.
 *
 * Runs after nextcloud-setup as the nextcloud user with a full NC bootstrap
 * (called from the nc-ocr-register-webhook oneshot). Idempotent.
 *
 * The nix-level throw only guards what nix configures; this catches an app
 * enabled by hand, or left enabled by a previous generation. Nextcloud
 * itself only disables an app whose files disappeared while it is actually
 * running an upgrade (lib/private/Updater.php checkAppsRequirements ->
 * disableApp), so it cannot be relied on for this. Uses the public OCP API
 * (IAppManager), which is the same call `occ app:disable` makes - the
 * documented CLI alternative - just without shelling out and parsing
 * command output.
 *
 * The leftover-Flow-rule REPORT is deliberately NOT done here. It is done
 * by the calling unit with the documented `occ workflows:list`, so this
 * script reads no table at all. Context for that choice: a rule whose
 * operation class is gone is skipped SILENTLY while the app is disabled
 * (lib/Manager.php:269-272 is a bare `continue`), so the invariant holds
 * without touching it, and every deletion path is closed to a headless
 * service - the workflowengine OCS routes carry
 * #[PasswordConfirmationRequired] on create/update/destroy, there is no occ
 * delete command, and a raw DELETE against the internal flow_operations
 * table is unsanctioned and coupled to a schema we do not own.
 *
 * Logging goes to STDERR (the systemd journal).
 *
 * Usage: php enforce-single-owner.php <nc-root> [app-id]...
 * Exits non-zero if an app could not actually be disabled.
 */

class SingleOwnerEnforcer
{
	/**
	 * @param string[] $apps
	 */
	public function __construct(
		private string $ncRoot,
		private array $apps
	) {
	}

	public static function fromArgv(array $argv): ?self
	{
		$ncRoot = (string) ($argv[1] ?? '');
		if ($ncRoot === '') {
			return null;
		}
		return new self($ncRoot, array_slice($argv, 2));
	}

	public function run(): int
	{
		if (!$this->bootstrap()) {
			return 1;
		}
		$appManager = $this->appManager();

		$failed = false;
		foreach ($this->apps as $app) {
			$app = trim((string) $app);
			if ($app === '') {
				continue;
			}
			$failed = $this->disable($appManager, $app) || $failed;
		}

		$this->log(
			$failed
				? 'Single-owner enforcement finished with errors'
				: 'Single-owner enforcement complete'
		);
		return $failed ? 1 : 0;
	}

	/**
	 * Full Nextcloud bootstrap, the same way occ does it. Must happen
	 * before any OCP class is used. Exposed as `protected` so a test
	 * subclass can stub it - the real one tries to chdir() into $ncRoot
	 * and require $ncRoot/lib/base.php, which fail in unit tests.
	 */
	protected function bootstrap(): bool
	{
		define('OC_CONSOLE', 1);
		chdir($this->ncRoot);
		error_reporting(E_ALL);
		ini_set('display_errors', '1');
		ini_set('log_errors', '1');
		try {
			require_once $this->ncRoot . '/lib/base.php';
		} catch (\Throwable $e) {
			$this->log('Bootstrap failed: ' . $e->getMessage());
			return false;
		}
		return true;
	}

	/**
	 * Resolves the IAppManager the enforcer runs against. Production uses the
	 * real OCP server container; tests subclass this to inject a fake so the
	 * script can be exercised without a Nextcloud bootstrap.
	 */
	protected function appManager(): IAppManager
	{
		return Server::get(IAppManager::class);
	}

	/**
	 * @return bool true when the app could not be disabled
	 */
	private function disable(IAppManager $appManager, string $app): bool
	{
		try {
			if (!$appManager->isEnabledForAnyone($app)) {
				$this->log("Competing OCR app already disabled: $app");
				return false;
			}
			$appManager->disableApp($app);
			// Verify the post-condition: logging "disabled" while the app
			// is still enabled would be worse than not checking at all.
			if ($appManager->isEnabledForAnyone($app)) {
				$this->log("ERROR: $app is STILL enabled after disableApp()");
				return true;
			}
			$this->log("Disabled competing OCR app: $app");
			return false;
		} catch (\Throwable $e) {
			$this->log("ERROR: could not disable $app: " . $e->getMessage());
			return true;
		}
	}

	private function log(string $message): void
	{
		fwrite(STDERR, $message . "\n");
	}
}

$enforcer = SingleOwnerEnforcer::fromArgv($argv ?? []);
if ($enforcer === null) {
	if (defined('WORKFLOW_OCR_TEST_MODE')) {
		// Test bootstrap: class loaded, do not run nor exit.
		return;
	}
	fwrite(STDERR, "ERROR: missing nc-root argument\n");
	exit(1);
}
if (defined('WORKFLOW_OCR_TEST_MODE')) {
	return;
}
exit($enforcer->run());
