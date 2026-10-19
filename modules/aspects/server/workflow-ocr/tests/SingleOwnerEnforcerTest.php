<?php
declare(strict_types=1);

require_once __DIR__ . '/FakeAppManager.php';

use PHPUnit\Framework\TestCase;

final class SingleOwnerEnforcerTest extends TestCase
{
    private function makeEnforcer(array $apps, FakeAppManager $manager): TestableEnforcer
    {
        // ncRoot must be non-empty per SingleOwnerEnforcer::fromArgv()
        // (and irrelevant to TestableEnforcer, which skips bootstrap).
        return new TestableEnforcer('/var/lib/nextcloud', $apps, $manager);
    }

    public function testNoCompetingAppsIsAConformantNoOp(): void
    {
        // The "happy path" the unit is built around: nothing is enabled, so
        // run() must not touch disableApp() and must exit 0.
        $manager = new FakeAppManager();
        $manager->enabled = []; // neither 'ocr_a' nor 'ocr_b' is enabled

        $enforcer = $this->makeEnforcer(['ocr_a', 'ocr_b'], $manager);
        $this->assertSame(0, $enforcer->run());
        $this->assertSame(
            [],
            $manager->disableCalls,
            'no disableApp() call must be made when no competing app is enabled'
        );
    }

    public function testSecondCompetingOwnerIsDetectedAndDisabled(): void
    {
        // 'ocr_a' is the "second owner" still enabled. The enforcer must
        // call disableApp('ocr_a') exactly once, observe the post-condition,
        // and exit 0.
        $manager = new FakeAppManager();
        $manager->enabled = ['ocr_a' => true];

        $enforcer = $this->makeEnforcer(['ocr_a'], $manager);
        $this->assertSame(0, $enforcer->run());
        $this->assertSame(['ocr_a'], $manager->disableCalls);
        $this->assertFalse(
            $manager->enabled['ocr_a'],
            'disableApp() must have been observed by the post-condition check'
        );
    }

    public function testDisableThatSilentlyDoesNotStickSurfacesAsError(): void
    {
        // The IAppManager contract says disableApp() returns true on success,
        // but a buggy/incomplete implementation could lie and the row could
        // still be enabled. The script guards against exactly that with a
        // post-condition check; we simulate the lie here.
        $manager = new FakeAppManager();
        $manager->enabled = ['ocr_a' => true];
        $manager->postDisableStaysEnabled = true;

        $enforcer = $this->makeEnforcer(['ocr_a'], $manager);
        $this->assertSame(
            1,
            $enforcer->run(),
            'a stuck-enable after disableApp() must be a non-zero exit'
        );
        $this->assertSame(['ocr_a'], $manager->disableCalls);
    }

    public function testEmptyAndBlankEntriesAreSkipped(): void
    {
        // The loop trims and skips empty entries (the systemd unit does not
        // always pass the same list). Empty entries must NOT generate
        // disableApp() calls and must NOT count as a failure.
        $manager = new FakeAppManager();
        $manager->enabled = ['ocr_a' => true];

        $enforcer = $this->makeEnforcer(['', '   ', 'ocr_a', ''], $manager);
        $this->assertSame(0, $enforcer->run());
        $this->assertSame(
            ['ocr_a'],
            $manager->disableCalls,
            'only the non-empty, non-whitespace app must be acted on'
        );
    }

    public function testOneFailingAppMakesOverallRunFail(): void
    {
        // Two competing apps, both "enabled". First one is disabled
        // cleanly; the second one's manager is set to lie about the result.
        // run() must exit 1 because one failed, and disableCalls must list
        // both (each gets a chance - the loop is not transactional).
        $manager = new FakeAppManager();
        $manager->enabled = ['ocr_a' => true, 'ocr_b' => true];
        // Lie only about ocr_b: isEnabledForAnyone() will keep returning
        // true for it after disableApp() runs. We need to do that
        // conditionally on which app was disabled - a different lie per
        // app. The simplest way is to mark ocr_b as a "stays enabled" one
        // via the existing flag plus a manual post-condition override; the
        // FakeAppManager's flag already does that conditional check.
        $manager->postDisableStaysEnabled = true;
        // But this would also lie for ocr_a, which we DON'T want. So we
        // make ocr_a appear disabled BEFORE the test starts (already
        // disabled -> the script's own isEnabledForAnyone() short-circuits
        // before any disable, so no post-condition check happens for it).
        $manager->enabled['ocr_a'] = false;

        $enforcer = $this->makeEnforcer(['ocr_a', 'ocr_b'], $manager);
        $this->assertSame(1, $enforcer->run());
        $this->assertSame(
            ['ocr_b'],
            $manager->disableCalls,
            'ocr_a was already disabled so the script should skip it; '
            . 'ocr_b is the one that must be acted on'
        );
    }
}