<?php
/**
 * Stand-in for OCP\App\IAppManager, defined only when Nextcloud is not in
 * the picture (i.e. unit tests). Same fully-qualified name so the type hint
 * in enforce-single-owner.php resolves; same method signatures as the methods
 * the script actually calls.
 *
 * If the script's IAppManager usage grows, this stub must follow - it is
 * intentionally NOT a complete mirror of the real interface, only what the
 * test exercises.
 */
declare(strict_types=1);

namespace OCP\App;

interface IAppManager
{
    public function isEnabledForAnyone(string $appId): bool;
    public function disableApp(string $appId): bool;
}