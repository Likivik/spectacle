<?php
/**
 * PHPUnit bootstrap for the workflow-ocr PHP scripts.
 *
 * Defines WORKFLOW_OCR_TEST_MODE so the trailing top-level code in each
 * production script (which would otherwise call exit() during require_once)
 * becomes a no-op. The production class definitions are still loaded
 * normally.
 *
 * Also loads minimal stand-ins for the OCP interfaces the scripts type-hint
 * against. Without Nextcloud's autoloader, those references would otherwise be
 * unresolved; the stubs carry only the methods the scripts actually call.
 */
declare(strict_types=1);

if (!defined('WORKFLOW_OCR_TEST_MODE')) {
    define('WORKFLOW_OCR_TEST_MODE', 1);
}

require_once __DIR__ . '/_stubs/IAppManager.php';