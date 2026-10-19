<?php
declare(strict_types=1);

if (!defined('WORKFLOW_OCR_TEST_MODE')) {
    define('WORKFLOW_OCR_TEST_MODE', 1);
}

// Wrap the production script in a try/catch so the trailing top-level
// `SingleOwnerEnforcer::fromArgv($argv)` cannot abort PHPUnit. In production
// $argv[1] is the nc-root and $argv[2..] are app ids; here they are unset,
// but fromArgv handles missing arguments by returning null.
try {
    require_once dirname(__DIR__) . '/enforce-single-owner.php';
} catch (\Throwable $e) {
    // Test bootstrap; ignore any incidental production-only exceptions.
}

use OCP\App\IAppManager;

/**
 * Test stub for IAppManager. We DO claim the interface so PHP's type
 * checker on SingleOwnerEnforcer::disable() is happy. The methods we don't
 * model throw if anything accidentally touches them - the script's narrow
 * contract means that is a real bug, not a missing feature.
 *
 * IAppManager's exact surface drifts across Nextcloud majors; we declare
 * only the methods we have to, with the signatures the current Nextcloud
 * (28+) uses. If this file stops loading against a newer Nextcloud, the
 * breakage is local: it is a test stub, not production code.
 */
final class FakeAppManager implements IAppManager
{
    /** @var array<string,bool> whether each app is enabled */
    public array $enabled = [];

    /** @var list<string> apps passed to disableApp() in order */
    public array $disableCalls = [];

    /**
     * If true, isEnabledForAnyone() returns false even when the entry in
     * $enabled is true - i.e. pretend disableApp() silently failed.
     */
    public bool $postDisableStaysEnabled = false;

    public function isEnabledForAnyone(string $appId): bool
    {
        if ($this->postDisableStaysEnabled
            && in_array($appId, $this->disableCalls, true)
        ) {
            return true;
        }
        return $this->enabled[$appId] ?? false;
    }

    public function disableApp(string $appId): bool
    {
        $this->disableCalls[] = $appId;
        $this->enabled[$appId] = false;
        return true;
    }
}

/**
 * Subclass that skips the Nextcloud bootstrap and substitutes the fake
 * manager. The production class calls Server::get(IAppManager::class) and
 * require_once's Nextcloud's own base.php - neither is wanted in unit tests,
 * so the test seams are the protected appManager() factory and a `bootstrap()`
 * override (production's bootstrap tries to chdir() into $ncRoot and load
 * $ncRoot/lib/base.php, both of which would fail without a Nextcloud install).
 */
final class TestableEnforcer extends SingleOwnerEnforcer
{
    public FakeAppManager $manager;

    public function __construct(string $ncRoot, array $apps, FakeAppManager $manager)
    {
        parent::__construct($ncRoot, $apps);
        $this->manager = $manager;
    }

    protected function bootstrap(): bool
    {
        // Tests do not need a Nextcloud bootstrap; pretend it succeeded.
        return true;
    }

    protected function appManager(): IAppManager
    {
        return $this->manager;
    }
}